"""商品库 API：列表（筛选+分页）、同步、流量覆盖统计。"""
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from .. import database
from ..services import products as prod_svc, common

router = APIRouter(prefix="/api", tags=["products"])


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@router.get("/products")
def list_products(
    q: str = None, operator: str = None, category: str = None, max_fee: int = None, min_data: int = None,
    min_general: float = None, night: int = None, region: str = None, zhutui: int = None,
    sort: str = None, order: str = "desc",
    page: int = 1, page_size: int = 50,
):
    conn = database.get_conn()
    try:
        where, args = [], []
        if q:
            kw = "%" + q.strip() + "%"
            where.append("(p.product_name LIKE ? OR p.keywords LIKE ? OR p.remark LIKE ? "
                         "OR p.area LIKE ? OR p.disable_area LIKE ? OR p.operator LIKE ?)")
            args += [kw] * 6
        if operator:
            where.append("p.operator = ?"); args.append(operator)
        if category:
            where.append("p.category = ?"); args.append(category)
        if max_fee is not None:
            where.append("p.monthly_fee <= ?"); args.append(max_fee)
        if min_data is not None:
            where.append("p.data_gb >= ?"); args.append(min_data)
        if min_general is not None:
            where.append("EXISTS(SELECT 1 FROM product_specs s WHERE s.product_id=p.product_id AND s.general_gb>=?)")
            args.append(min_general)
        if night:
            where.append("EXISTS(SELECT 1 FROM product_specs s WHERE s.product_id=p.product_id AND s.night_gb>0)")
        if region:
            where.append("(p.product_name LIKE ? OR p.area LIKE ? OR p.area_read LIKE ?)")
            args += ["%" + region + "%"] * 3
        if zhutui:
            where.append("p.is_zhutui = 1")
        where.append("p.on_sale = 1")
        sql = "SELECT p.* FROM products p WHERE " + " AND ".join(where)
        total = conn.execute("SELECT count(*) FROM (" + sql + ")", args).fetchone()[0]

        SORT_COLS = {"monthly_fee", "commission", "data_gb", "voice_min",
                     "product_name", "area", "category", "operator", "create_time"}
        if sort in SORT_COLS:
            direction = "ASC" if (order or "").lower() == "asc" else "DESC"
            # NULL 排到最后
            order_by = "ORDER BY (p.%s IS NULL), p.%s %s, p.product_id" % (sort, sort, direction)
        else:
            order_by = "ORDER BY (p.category='手机卡') DESC, p.on_sale DESC, p.commission DESC, p.product_id"
        rows = conn.execute(
            sql + " " + order_by + " LIMIT ? OFFSET ?",
            args + [page_size, (page - 1) * page_size]).fetchall()

        items = []
        for r in rows:
            d = {k: r[k] for k in r.keys() if k != "raw_json"}  # 不返回 raw_json（太大）
            sp = conn.execute(
                "SELECT total_gb,general_gb,directional_gb,night_gb,night_window,source,evidence "
                "FROM product_specs WHERE product_id=?", (r["product_id"],)).fetchone()
            if sp:
                d["specs"] = dict(sp)
            items.append(d)
        return {"total": total, "items": items, "page": page, "page_size": page_size}
    finally:
        conn.close()


@router.get("/products/facets")
def product_facets():
    """筛选项候选值（运营商 / 分类 / 地区），供前端下拉使用。"""
    conn = database.get_conn()
    try:
        def distinct(col):
            return [r[0] for r in conn.execute(
                "SELECT DISTINCT %s FROM products WHERE on_sale=1 AND %s IS NOT NULL AND %s<>'' "
                "ORDER BY %s" % (col, col, col, col))]

        raw_areas = distinct("area")
        return {
            "operators": distinct("operator"),
            "categories": distinct("category"),
            "areas": _clean_areas(raw_areas),
        }
    finally:
        conn.close()


_AREA_JUNK = ("当地", "收货地", "随机", "归属地", "全国", "不限")


def _clean_areas(areas):
    """把脏的地区值洗成干净的省级候选：剔除垃圾词、拆分「省-市」、去省市后缀、去重。"""
    out = []
    for a in areas:
        a = (a or "").strip()
        if not a or any(j in a for j in _AREA_JUNK):
            continue
        if "-" in a:  # 「山东-东营」这类取省
            a = a.split("-")[0].strip()
        for suf in ("市", "省"):
            if a.endswith(suf) and len(a) > 2:
                a = a[:-1]
        # 过长的基本是「郑州新密中牟…」这类城市串，丢弃
        if not a or len(a) > 6:
            continue
        out.append(a)
    return sorted(set(out))


@router.get("/spec-stats")
def spec_stats():
    conn = database.get_conn()
    try:
        def c(sql):
            return conn.execute(sql).fetchone()[0]
        return {
            "total": c("SELECT count(*) FROM product_specs"),
            "has_total": c("SELECT count(*) FROM product_specs WHERE total_gb IS NOT NULL"),
            "has_general": c("SELECT count(*) FROM product_specs WHERE general_gb IS NOT NULL"),
            "has_directional": c("SELECT count(*) FROM product_specs WHERE directional_gb > 0"),
            "has_night": c("SELECT count(*) FROM product_specs WHERE night_gb > 0"),
        }
    finally:
        conn.close()


@router.get("/changes")
def list_changes(
    category: str = None,
    q: str = None,
    limit: int = 200,
    page: int = 1,
):
    """更新日志：返回最近的字段级变更（join products 取商品名/品类）。"""
    conn = database.get_conn()
    try:
        where, args = [], []
        if category:
            where.append("p.category = ?")
            args.append(category)
        if q:
            kw = "%" + q.strip() + "%"
            where.append("(p.product_name LIKE ? OR c.field LIKE ?)")
            args += [kw, kw]
        wsql = ("WHERE " + " AND ".join(where)) if where else ""
        base = "FROM product_changes c LEFT JOIN products p ON p.product_id=c.product_id "
        total = conn.execute("SELECT count(*) " + base + wsql, args).fetchone()[0]
        rows = conn.execute(
            "SELECT c.id, c.product_id, c.field, c.old_value, c.new_value, c.changed_at, c.batch_id, "
            "p.product_name, p.category " + base + wsql +
            "ORDER BY c.changed_at DESC, c.id DESC LIMIT ? OFFSET ?",
            args + [limit, (page - 1) * limit]).fetchall()
        return {"total": total, "items": [dict(r) for r in rows],
                "page": page, "page_size": limit}
    finally:
        conn.close()


@router.post("/sync")
def sync():
    try:
        return {"ok": True, **prod_svc.sync()}
    except common.TokenExpired as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/stream")
def sync_stream():
    """手机卡商品同步：SSE 流式返回进度。"""
    def gen():
        for ev in prod_svc.sync_stream():
            yield _sse(ev)
        yield "data: [DONE]\n\n"
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
