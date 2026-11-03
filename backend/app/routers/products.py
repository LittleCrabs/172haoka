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


COLLAPSE_MIN = 5        # 同批次、同字段、同「旧值→新值」达到这么多条才折叠
COLLAPSE_SCAN_MAX = 20000  # 折叠要看全量才能算准条数，给个上限兜底


def _collapse_changes(rows):
    """把一次同步里的大批量同质变更折叠成一行。

    背景：更新日志本该回答「昨天改了什么」，但一次代码升级把 869 个商品的
    commission_type 从 '0' 纠正成 '秒返'，占满整页，真正那条「在售→下架」
    反而被埋掉。这类同批次、同字段、同变化的记录对人是没有信息量的，
    折成一条「本批 N 个商品」摘要即可，需要看具体是哪些再点开。

    判定条件全部为真才折叠：有 batch_id、字段相同、旧值相同、新值相同、条数达阈值。
    """
    groups = {}
    for r in rows:
        b = r["batch_id"]
        if not b:
            continue  # 没有批次号的（早期数据）保持逐条显示
        key = (b, r["field"], r["old_value"], r["new_value"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"count": 0, "samples": []}
        g["count"] += 1
        if len(g["samples"]) < 3 and r["product_name"]:
            g["samples"].append(r["product_name"])

    out, emitted = [], set()
    for r in rows:
        d = dict(r)
        b = r["batch_id"]
        key = (b, r["field"], r["old_value"], r["new_value"]) if b else None
        g = groups.get(key) if key else None
        if g and g["count"] >= COLLAPSE_MIN:
            if key in emitted:
                continue
            emitted.add(key)
            d.update({"kind": "summary", "count": g["count"],
                      "samples": g["samples"], "product_name": None,
                      "product_id": None})
        else:
            d["kind"] = "detail"
        out.append(d)
    return out


@router.get("/changes")
def list_changes(
    category: str = None,
    q: str = None,
    limit: int = 200,
    page: int = 1,
    collapse: int = 1,
):
    """更新日志：返回最近的字段级变更（join products 取商品名/品类）。

    collapse=1（默认）时把同批次的批量同质变更折叠成摘要行，
    避免一次批量修正把真正的业务变更挤出视野；传 0 看逐条明细。
    """
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
        order = "ORDER BY c.changed_at DESC, c.id DESC"

        if not collapse:
            total = conn.execute("SELECT count(*) " + base + wsql, args).fetchone()[0]
            rows = conn.execute(
                "SELECT c.id, c.product_id, c.field, c.old_value, c.new_value, c.changed_at, "
                "c.batch_id, p.product_name, p.category " + base + wsql + order +
                " LIMIT ? OFFSET ?",
                args + [limit, (page - 1) * limit]).fetchall()
            return {"total": total, "items": [dict(r) for r in rows],
                    "page": page, "page_size": limit, "collapsed": False}

        # 折叠必须基于全量：先按明细 limit 再折叠，条目数会和 total 对不上
        rows = conn.execute(
            "SELECT c.id, c.product_id, c.field, c.old_value, c.new_value, c.changed_at, "
            "c.batch_id, p.product_name, p.category " + base + wsql + order + " LIMIT ?",
            args + [COLLAPSE_SCAN_MAX]).fetchall()
        items = _collapse_changes(rows)
        total = len(items)
        start = (page - 1) * limit
        return {"total": total, "items": items[start:start + limit],
                "page": page, "page_size": limit, "collapsed": True,
                "truncated": len(rows) >= COLLAPSE_SCAN_MAX}
    finally:
        conn.close()


@router.get("/changes/expand")
def expand_change(batch_id: str, field: str,
                  old_value: str = None, new_value: str = None, limit: int = 500):
    """展开一条被折叠的批量变更，列出它包含的具体商品。"""
    conn = database.get_conn()
    try:
        where = ["c.batch_id = ?", "c.field = ?"]
        args = [batch_id, field]
        if old_value is not None:
            where.append("c.old_value IS ?")
            args.append(old_value)
        if new_value is not None:
            where.append("c.new_value IS ?")
            args.append(new_value)
        wsql = "WHERE " + " AND ".join(where)
        base = "FROM product_changes c LEFT JOIN products p ON p.product_id=c.product_id "
        total = conn.execute("SELECT count(*) " + base + wsql, args).fetchone()[0]
        rows = conn.execute(
            "SELECT c.id, c.product_id, c.field, c.old_value, c.new_value, c.changed_at, "
            "c.batch_id, p.product_name, p.category, p.on_sale " + base + wsql +
            " ORDER BY p.product_name LIMIT ?", args + [limit]).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
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
