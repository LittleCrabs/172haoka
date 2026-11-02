"""宽带选品广场 API（数据全部读本地 products 表，靠一键同步入库）：
- /api/kuanpro/list   列表（本地，支持多条件筛选 + 分页）
- /api/kuanpro/facets 筛选项候选（运营商 / 地区 / 带宽，读本地）
- /api/kuanpro/toggle 上架 / 下架（代理后台 api/ProKuan/Delete 开关，远程）
"""
import json
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import database
from ..services import common, kuanpro_sync

router = APIRouter(prefix="/api", tags=["kuanpro"])

_SPEED_RE = re.compile(r"(\d{3,4})\s*M", re.I)


def parse_speed(name):
    """从商品名解析带宽（如 500M / 1000M），返回整数或 None。"""
    m = _SPEED_RE.search(name or "")
    return int(m.group(1)) if m else None


_FEE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*元\s*(?:/|包)?\s*(年|月|年\)|/年|/月)?", re.I)


def parse_fee(name):
    """从商品名解析年费 / 月费数值（如 399元/年、59/月），返回数值或 None。"""
    m = _FEE_RE.search(name or "")
    return float(m.group(1)) if m else None


def _build_item(r, h5):
    """由本地行 + raw_json 拼出与远端一致的全字段（详情对话框直接复用）。"""
    raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
    name = raw.get("productName") or r["product_name"] or ""
    pid_str = raw.get("productIDStr")
    return {
        "product_id": r["product_id"],
        "product_id_str": pid_str,
        "product_name": name,
        "operator": raw.get("operator") or r["operator"],
        "flag": bool(r["on_sale"]),            # 本地上架状态（= 已同步的 flag）
        "low_flag": bool(raw.get("lowFlag")),
        "speed": parse_speed(name),
        "price": raw.get("price"),
        "price_read": raw.get("priceRead"),
        "s_price": raw.get("sPrice"),
        "s_price_read": raw.get("sPriceRead"),
        "commission_type": raw.get("commissionType"),
        "area": raw.get("area") or r["area"],
        "area_read": raw.get("areaRead"),
        "disable_area": raw.get("disableArea"),
        "rule": raw.get("rule"),
        "remark": raw.get("remark"),
        "beizhu": raw.get("beizhu"),
        "taocan": raw.get("taocan"),
        "zhutui": bool(raw.get("zhutui")),
        "create_time": raw.get("createTime"),
        "main_pic": raw.get("mainPic"),
        "little_picture": raw.get("littlepicture"),
        "sn": raw.get("sn"),
        "user_sn": raw.get("userSn"),
        "detail_url": ("%s/PackInfo/Detail/%s" % (h5, pid_str)) if (h5 and pid_str) else None,
    }


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@router.get("/kuanpro/list")
def list_kuanpro(
    page: int = 1,
    page_size: int = 50,
    operator: str = None,
    area: str = None,
    speed: int = None,
    price_min: float = None,
    price_max: float = None,
    flag: str = None,          # all / 0 / 1（上架状态）
    zhutui: int = None,        # 1 = 仅主推
    q: str = None,
):
    """选品广场列表：读本地 products 表（category='宽带'），按条件筛选 + 分页。"""
    conn = database.get_conn()
    try:
        where, args = ["category='宽带'"], []
        if operator:
            where.append("operator = ?"); args.append(operator)
        if area:
            where.append("area = ?"); args.append(area)
        if flag in ("0", "1"):
            where.append("on_sale = ?"); args.append(1 if flag == "1" else 0)
        if zhutui == 1:
            where.append("is_zhutui = 1")
        if q:
            kw = "%" + q.strip() + "%"
            where.append("(product_name LIKE ? OR area LIKE ? OR remark LIKE ? "
                         "OR rule LIKE ? OR keywords LIKE ?)")
            args += [kw] * 5

        rows = conn.execute(
            "SELECT * FROM products WHERE " + " AND ".join(where), args).fetchall()
        h5 = common.h5_base(conn, refresh=False)

        # 带宽 / 价格需解析商品名，无法用 SQL，拉出候选后在 Python 过滤
        out = []
        for r in rows:
            raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
            name = raw.get("productName") or r["product_name"] or ""
            if speed is not None and parse_speed(name) != speed:
                continue
            if price_min is not None or price_max is not None:
                fee = parse_fee(name)
                if fee is None:
                    continue
                if price_min is not None and fee < price_min:
                    continue
                if price_max is not None and fee > price_max:
                    continue
            out.append(r)

        total = len(out)
        start = (page - 1) * page_size
        page_rows = out[start:start + page_size]
        items = [_build_item(r, h5) for r in page_rows]
        return {"total": total, "items": items, "page": page, "page_size": page_size}
    except common.TokenExpired as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/kuanpro/facets")
def kuanpro_facets():
    """筛选项候选值（读本地）：运营商 / 地区 / 带宽。"""
    conn = database.get_conn()
    try:
        ops = [r[0] for r in conn.execute(
            "SELECT DISTINCT operator FROM products WHERE category='宽带' "
            "AND operator IS NOT NULL AND operator<>'' ORDER BY operator")]
        areas = [r[0] for r in conn.execute(
            "SELECT DISTINCT area FROM products WHERE category='宽带' "
            "AND area IS NOT NULL AND area<>'' ORDER BY area")]
        speeds = set()
        for (rj,) in conn.execute("SELECT raw_json FROM products WHERE category='宽带'"):
            if not rj:
                continue
            try:
                raw = json.loads(rj)
            except Exception:
                continue
            sp = parse_speed(raw.get("productName") or "")
            if sp:
                speeds.add(sp)
        return {"operators": ops, "areas": areas, "speeds": sorted(speeds)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/kuanpro/toggle")
def toggle_kuanpro(body: dict):
    """上架 / 下架：代理后台 api/ProKuan/Delete（远程）。
    注意：后台上架是异步处理（返回"系统处理中"），flag 不会立即翻转；
    本地库 on_sale 由你后续「一键同步」对齐。
    body: { product_id: int }
    """
    pid = body.get("product_id")
    if pid is None:
        raise HTTPException(status_code=400, detail="缺少 product_id")
    try:
        res = common.api("api/ProKuan/Delete", data={"ProductID": pid}, method="POST")
        if res.get("code") != 0:
            raise HTTPException(status_code=502, detail=res.get("msg") or "后台返回错误")
        return {"ok": True, "message": res.get("message") or "操作成功"}
    except common.TokenExpired as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kuanpro/sync")
def do_kuanpro_sync():
    """一键同步宽带选品到本地：SSE 流式返回进度。"""
    def gen():
        for ev in kuanpro_sync.sync_stream():
            yield _sse(ev)
        yield "data: [DONE]\n\n"
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
