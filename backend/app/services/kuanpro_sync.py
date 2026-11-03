"""宽带选品同步：从 api/ProKuan/GroundProQuery 拉取，upsert 到 products 表。

与商品库 products.sync 保持一致：已存在记录先做字段级 diff，只有真正变化的才
计入「更新」并整行重写；未变化的只刷新 last_seen 与 H5 链接（域名可能轮换），
避免每次同步都把全量判成「更新」。
"""
import datetime as dt
import json
from .. import database
from . import common

PAGE_SIZE = 50


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_record(raw, h5=""):
    sn = raw.get("sn") or ""
    return {
        "product_id": raw["productID"],
        "product_name": raw.get("productName") or "",
        "operator": raw.get("operator"),
        "category": "宽带",
        "monthly_fee": None,
        "data_gb": None,
        "voice_min": None,
        "commission": raw.get("sPrice"),
        "commission_type": raw.get("backMoneyType"),  # 用文字版（与 products 通道一致）；
        # 不用 commissionType（数字码），否则两通道对同一商品各写各的格式，永远乒乓更新
        "commission_read": raw.get("sPriceRead"),
        "area": raw.get("area"),
        "area_read": raw.get("areaRead"),
        "disable_area": raw.get("disableArea"),
        "age_min": raw.get("age1"),
        "age_max": raw.get("age2"),
        "rule": raw.get("rule"),
        "remark": raw.get("remark"),
        "keywords": raw.get("keyWords"),
        "third_api": raw.get("thirdApi"),
        "on_sale": 1 if raw.get("flag") else 0,  # flag = 上架状态（lowFlag 是下级状态）
        "is_zhutui": 1 if raw.get("zhutui") else 0,
        "main_pic": raw.get("mainPic"),
        "sn": sn,
        "product_str": raw.get("productStr"),
        "detail_url": ("%s/PackInfo/Detail/%s" % (h5, sn)) if (h5 and sn) else None,
        "exclusive_url": ("%s/pdetails?tk=%s&pro=%s" % (h5, raw.get("userSn"), sn))
                         if (h5 and raw.get("userSn") and sn) else None,
        "create_time": raw.get("createTime"),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "sync_source": "kuanpro",  # 来源标记：下架判定只认"最后一次由本通道见过的商品"
    }


# 参与 diff 的业务字段（与 products.py 思路一致）。
# 不在此列的：monthly_fee/data_gb/voice_min（宽带恒为 None）、category（恒为 宽带）；
# disable_area（两个接口给的格式不同：'济南市' vs 全量长串，做 diff 必然乒乓，更新时沿用库内值）；
# detail_url/exclusive_url（H5 域名轮换，纯噪音，单独静默刷新）；raw_json（全量原文）。
DIFF_FIELDS = [
    "product_name", "commission", "commission_type", "commission_read", "on_sale",
    "is_zhutui", "area", "area_read", "age_min", "age_max",
    "rule", "remark", "keywords", "third_api", "main_pic", "sn",
    "product_str", "create_time",
]

_COLUMNS = [
    "product_id", "product_name", "operator", "category", "monthly_fee", "data_gb",
    "voice_min", "commission", "commission_type", "commission_read", "area",
    "area_read", "disable_area", "age_min", "age_max", "rule", "remark",
    "keywords", "third_api", "on_sale", "is_zhutui", "main_pic", "sn",
    "product_str", "detail_url", "exclusive_url", "create_time", "raw_json",
    "sync_source",
    "first_seen", "last_seen", "updated_at",
]


def fetch_all():
    """拉取后台全部宽带选品（不分页聚合），返回原始 dict 列表。"""
    first = common.api("api/ProKuan/GroundProQuery?page=1&limit=%d" % PAGE_SIZE)
    total = first.get("count") or 0
    rows = list(first.get("data") or [])
    page = 2
    while len(rows) < total:
        res = common.api("api/ProKuan/GroundProQuery?page=%d&limit=%d" % (page, PAGE_SIZE))
        batch = res.get("data") or []
        if not batch:
            break
        rows.extend(batch)
        page += 1
    return rows


def sync_stream():
    """生成器： yield 进度事件 dict。
    事件类型：start / progress / done / error
    注：progress 事件已不再被前端进度条使用（前端已移除进度条），此处仍可按需 yield。
    """
    import uuid
    conn = database.get_conn()
    ts = now()
    batch_id = "%s_%s" % (ts, uuid.uuid4().hex[:8])

    # 宽带通道原来完全不写 crawl_log，导致「上次同步」只能看到手机卡那条。
    log_id = None
    try:
        cur = conn.execute("INSERT INTO crawl_log(started_at, kind, status) VALUES (?, '宽带', 'running')",
                           (ts,))
        log_id = cur.lastrowid
        conn.commit()
    except Exception:
        log_id = None

    try:
        rows = fetch_all()
        total = len(rows)
        yield {"type": "start", "total": total, "page": 1}

        # H5 域名
        try:
            h5 = common.h5_base(conn, refresh=True)
        except Exception:
            h5 = database.get_meta(conn, "h5_base") or ""

        recs = [to_record(r, h5) for r in rows]
        seen = {r["product_id"] for r in recs}

        # 获取现有 first_seen
        existing = {}
        for r in conn.execute("SELECT product_id, first_seen FROM products WHERE category='宽带'"):
            existing[r["product_id"]] = r["first_seen"]

        inserted = updated = unchanged = 0
        changes = []  # 字段级变更流水，最后写入 product_changes
        for rec in recs:
            pid = rec["product_id"]
            rec["first_seen"] = existing.get(pid) or ts
            rec["last_seen"] = ts
            rec["updated_at"] = ts

            old = conn.execute("SELECT * FROM products WHERE product_id=?", (pid,)).fetchone()
            if old is None:
                cols = ", ".join(_COLUMNS)
                placeholders = ", ".join("?" * len(_COLUMNS))
                conn.execute("INSERT INTO products(%s) VALUES(%s)" % (cols, placeholders),
                             [rec[c] for c in _COLUMNS])
                inserted += 1
            else:
                # disable_area 两个接口格式不同（'济南市' vs 全量长串），更新时沿用库内值，
                # 避免 products 通道写的权威值被本通道冲掉；库内为空才采用本通道的值。
                if old["disable_area"]:
                    rec["disable_area"] = old["disable_area"]
                diff = {f: (old[f], rec[f]) for f in DIFF_FIELDS if str(old[f]) != str(rec[f])}
                if diff:
                    for f, (o, n) in diff.items():
                        changes.append((pid, f, o, n, ts, batch_id))
                    sets = ", ".join("%s=?" % c for c in _COLUMNS if c != "product_id")
                    vals = [rec[c] for c in _COLUMNS if c != "product_id"] + [pid]
                    conn.execute("UPDATE products SET %s WHERE product_id=?" % sets, vals)
                    updated += 1
                else:
                    # 数据未变：仍刷新 last_seen、H5 链接（域名可能轮换）与 raw_json（详情源），
                    # 并把来源标记归到本通道（下架判定依据：只杀自己见过的商品）
                    conn.execute(
                        "UPDATE products SET last_seen=?, detail_url=?, exclusive_url=?, raw_json=?, "
                        "sync_source='kuanpro' WHERE product_id=?",
                        (ts, rec["detail_url"], rec["exclusive_url"], rec["raw_json"], pid))
                    unchanged += 1

        # 下架本次没拉到的宽带（平台目录已下线的）。
        # 只处理 sync_source='kuanpro' 的商品：products 通道也在管部分宽带商品，
        # 若不区分来源，本通道会把对方拉到、而本接口没返回的商品误判成下架（互杀乒乓）。
        offsale = 0
        off_rows = conn.execute(
            "SELECT product_id, on_sale FROM products "
            "WHERE category='宽带' AND sync_source='kuanpro' AND last_seen != ?",
            (ts,)).fetchall()
        for o in off_rows:
            if o["on_sale"] == 1:
                offsale += 1
                changes.append((o["product_id"], "on_sale", 1, 0, ts, batch_id))
        conn.execute(
            "UPDATE products SET on_sale=0 WHERE category='宽带' AND sync_source='kuanpro' AND last_seen != ?",
            (ts,))

        if changes:
            conn.executemany(
                "INSERT INTO product_changes(product_id, field, old_value, new_value, changed_at, batch_id) "
                "VALUES (?,?,?,?,?,?)", changes)
        if log_id:
            conn.execute(
                "UPDATE crawl_log SET finished_at=?, total=?, inserted=?, updated=?, unchanged=?, "
                "offsale=?, status='ok' WHERE id=?",
                (now(), len(recs), inserted, updated, unchanged, offsale, log_id))
        conn.commit()
        conn.close()
        yield {"type": "done", "total": len(recs), "inserted": inserted,
               "updated": updated, "unchanged": unchanged, "offsale": offsale}

    except common.TokenExpired as e:
        _mark_log(conn, log_id, "token_expired", str(e))
        conn.close()
        yield {"type": "error", "error": "token_expired", "message": str(e)}
    except Exception as e:
        _mark_log(conn, log_id, "failed", str(e))
        conn.close()
        yield {"type": "error", "error": "exception", "message": str(e)}


def _mark_log(conn, log_id, status, message):
    if not log_id:
        return
    try:
        conn.execute("UPDATE crawl_log SET finished_at=?, status=?, message=? WHERE id=?",
                     (now(), status, message, log_id))
        conn.commit()
    except Exception:
        pass
