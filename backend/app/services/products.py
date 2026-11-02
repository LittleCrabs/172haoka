"""商品同步：全量拉取 → 解析 → upsert → 字段变更流水 → 下架标记。"""
import datetime as dt
import json
import re
from .. import database
from . import common

PAGE_SIZE = 20  # 服务端把 limit 截断到 20，不要改大

DIFF_FIELDS = ["product_name", "category", "monthly_fee", "data_gb", "voice_min", "commission",
               "commission_type", "on_sale", "area", "disable_area", "remark", "rule", "keywords"]


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_all():
    first = common.api("api/Products/Query?page=1&limit=%d" % PAGE_SIZE)
    total = first.get("count") or 0
    rows = list(first.get("data") or [])
    page = 2
    while len(rows) < total:
        res = common.api("api/Products/Query?page=%d&limit=%d" % (page, PAGE_SIZE))
        batch = res.get("data") or []
        if not batch:
            break
        rows.extend(batch)
        page += 1
    return rows, total


BROADBAND_KW = ("宽带", "单宽", "包年", "宽融", "融合", "FTTR", "安装费", "一年",
                "包2年", "包1年", "包三年", "光猫")
BANDWIDTH_RE = re.compile(r"\d{3,4}M(?![a-zA-Z])")  # 500M / 1000M 这类带宽标识


def parse_name(name):
    """从商品名解析 月租/流量/通话。名称是这套系统里最可靠的套餐信息源。
    优先解析【】内的卖点串，没有方括号再用整个名称。"""
    seg = name
    m = re.search(r"【([^】]+)】", name)
    if m:
        seg = m.group(1)
    fee = data = voice = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*元", seg)
    if m:
        fee = float(m.group(1))
        if fee.is_integer():
            fee = int(fee)
    m = re.search(r"(\d+)\s*(?:G|GB)(?![a-zA-Z])", seg)
    if m:
        data = int(m.group(1))
    m = re.search(r"(\d+)\s*分钟", seg)
    if m:
        voice = int(m.group(1))
    return fee, data, voice


def classify(name, operator):
    if operator == "宽带" or any(k in name for k in BROADBAND_KW) or BANDWIDTH_RE.search(name):
        return "宽带"
    if operator == "靓号" or "靓号" in name:
        return "靓号"
    return "手机卡"


def to_record(raw, h5=""):
    name = raw.get("productName") or ""
    cat = classify(name, raw.get("operator"))
    fee, gb, voice = parse_name(name)
    if cat == "宽带":
        fee = None  # 宽带名称里的"N元"多为年费/套餐价，不能当月租
    sn = raw.get("productIDStr") or ""
    return {
        "product_id": raw["productID"],
        "product_name": name,
        "operator": raw.get("operator"),
        "category": cat,
        "monthly_fee": fee,
        "data_gb": gb,
        "voice_min": voice,
        "commission": raw.get("sPrice"),
        "commission_type": raw.get("backMoneyType"),
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
        "on_sale": 1 if raw.get("flag") else 0,
        "is_zhutui": 1 if raw.get("zhutui") else 0,
        "main_pic": raw.get("mainPic"),
        "sn": raw.get("sn"),
        "product_str": raw.get("productStr"),
        "detail_url": ("%s/PackInfo/Detail/%s" % (h5, sn)) if (h5 and sn) else None,
        "exclusive_url": ("%s/pdetails?tk=%s&pro=%s" % (h5, raw.get("userSn"), sn))
                         if (h5 and raw.get("userSn") and sn) else None,
        "create_time": raw.get("createTime"),  # 原网站商品的添加时间
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def sync(dry_run=False):
    conn = database.get_conn()
    started = now()
    log_id = None
    if not dry_run:
        cur = conn.execute("INSERT INTO crawl_log(started_at, status) VALUES (?, 'running')", (started,))
        log_id = cur.lastrowid
        conn.commit()

    try:
        raws, total = fetch_all()
    except common.TokenExpired as e:
        if log_id:
            conn.execute("UPDATE crawl_log SET finished_at=?, status='token_expired', message=? WHERE id=?",
                         (now(), str(e), log_id))
            conn.commit()
        conn.close()
        raise

    # H5 域名按账号下发且会变，每次同步顺手刷新一次
    try:
        h5 = common.h5_base(conn, refresh=True)
    except Exception as e:
        h5 = database.get_meta(conn, "h5_base") or ""
        print("（H5 域名刷新失败，沿用缓存 %s：%s）" % (h5 or "空", e))

    recs = [to_record(r, h5) for r in raws]
    seen = {r["product_id"] for r in recs}
    ts = now()
    inserted = updated = unchanged = 0
    changes = []

    for r in recs:
        old = conn.execute("SELECT * FROM products WHERE product_id=?", (r["product_id"],)).fetchone()
        if old is None:
            inserted += 1
            if not dry_run:
                cols = list(r.keys()) + ["first_seen", "last_seen", "updated_at"]
                vals = list(r.values()) + [ts, ts, ts]
                conn.execute("INSERT INTO products(%s) VALUES (%s)" % (
                    ",".join(cols), ",".join("?" * len(cols))), vals)
        else:
            diff = {f: (old[f], r[f]) for f in DIFF_FIELDS if str(old[f]) != str(r[f])}
            if diff:
                updated += 1
                for f, (o, n) in diff.items():
                    changes.append((r["product_id"], f, o, n, ts))
                if not dry_run:
                    sets = ",".join("%s=?" % f for f in r.keys())
                    conn.execute("UPDATE products SET %s, last_seen=?, updated_at=? WHERE product_id=?" % sets,
                                 list(r.values()) + [ts, ts, r["product_id"]])
            else:
                unchanged += 1
                if not dry_run:
                    conn.execute("UPDATE products SET last_seen=? WHERE product_id=?", (ts, r["product_id"]))

    # detail_url 依赖 H5 域名，域名会变，但不值得记进变更流水（纯噪音），单独无条件刷新
    if not dry_run and h5:
        conn.executemany("UPDATE products SET detail_url=? WHERE product_id=?",
                         [(r["detail_url"], r["product_id"]) for r in recs if r["detail_url"]])

    # 本次没出现的 → 下架（仅限本批同步覆盖的 category，避免误伤另一路同步的品类）
    offsale = 0
    synced_cats = {r["category"] for r in recs}
    if synced_cats:
        placeholders = ", ".join("?" * len(synced_cats))
        olds = conn.execute(
            "SELECT product_id, on_sale FROM products WHERE category IN (%s)" % placeholders,
            tuple(synced_cats)).fetchall()
        for o in olds:
            if o["product_id"] not in seen and o["on_sale"] == 1:
                offsale += 1
                changes.append((o["product_id"], "on_sale", 1, 0, ts))
                if not dry_run:
                    conn.execute("UPDATE products SET on_sale=0, updated_at=? WHERE product_id=?",
                                 (ts, o["product_id"]))

    if not dry_run:
        conn.executemany(
            "INSERT INTO product_changes(product_id, field, old_value, new_value, changed_at) VALUES (?,?,?,?,?)",
            changes)
        conn.execute("UPDATE crawl_log SET finished_at=?, total=?, inserted=?, updated=?, unchanged=?, "
                     "offsale=?, status='ok' WHERE id=?",
                     (now(), len(recs), inserted, updated, unchanged, offsale, log_id))
        conn.commit()
    conn.close()

    return {
        "total": len(recs), "inserted": inserted, "updated": updated,
        "unchanged": unchanged, "offsale": offsale, "changes": len(changes),
    }


def sync_stream():
    """生成器：yield 进度事件 dict（start/progress/done/error）。"""
    import uuid
    conn = database.get_conn()
    ts = now()
    batch_id = "%s_%s" % (ts, uuid.uuid4().hex[:8])
    try:
        raws, total = fetch_all()
        yield {"type": "start", "total": total}

        try:
            h5 = common.h5_base(conn, refresh=True)
        except Exception:
            h5 = database.get_meta(conn, "h5_base") or ""

        recs = [to_record(r, h5) for r in raws]
        seen = {r["product_id"] for r in recs}
        inserted = updated = unchanged = 0
        changes = []  # 字段级变更流水，最后写入 product_changes

        for i, r in enumerate(recs):
            old = conn.execute("SELECT * FROM products WHERE product_id=?", (r["product_id"],)).fetchone()
            if old is None:
                inserted += 1
                cols = list(r.keys()) + ["first_seen", "last_seen", "updated_at"]
                vals = list(r.values()) + [ts, ts, ts]
                conn.execute("INSERT INTO products(%s) VALUES (%s)" % (
                    ",".join(cols), ",".join("?" * len(cols))), vals)
            else:
                diff = {f: (old[f], r[f]) for f in DIFF_FIELDS if str(old[f]) != str(r[f])}
                if diff:
                    updated += 1
                    for f, (o, n) in diff.items():
                        changes.append((r["product_id"], f, o, n, ts, batch_id))
                    sets = ",".join("%s=?" % f for f in r.keys())
                    conn.execute("UPDATE products SET %s, last_seen=?, updated_at=? WHERE product_id=?" % sets,
                                 list(r.values()) + [ts, ts, r["product_id"]])
                else:
                    unchanged += 1
                    conn.execute("UPDATE products SET last_seen=? WHERE product_id=?", (ts, r["product_id"]))
            if (i + 1) % 20 == 0:
                yield {"type": "progress", "current": i + 1, "total": len(recs)}

        # 下架（仅限本批同步覆盖的 category，避免误伤另一路同步的品类）
        offsale = 0
        synced_cats = {r["category"] for r in recs}
        if synced_cats:
            placeholders = ", ".join("?" * len(synced_cats))
            olds = conn.execute(
                "SELECT product_id, on_sale FROM products WHERE category IN (%s)" % placeholders,
                tuple(synced_cats)).fetchall()
            for o in olds:
                if o["product_id"] not in seen and o["on_sale"] == 1:
                    offsale += 1
                    changes.append((o["product_id"], "on_sale", 1, 0, ts, batch_id))
                    conn.execute("UPDATE products SET on_sale=0, updated_at=? WHERE product_id=?",
                                 (ts, o["product_id"]))

        if changes:
            conn.executemany(
                "INSERT INTO product_changes(product_id, field, old_value, new_value, changed_at, batch_id) "
                "VALUES (?,?,?,?,?,?)", changes)
        conn.commit()
        conn.close()
        yield {"type": "done", "total": len(recs), "inserted": inserted,
               "updated": updated, "unchanged": unchanged, "offsale": offsale}
    except common.TokenExpired as e:
        conn.close()
        yield {"type": "error", "error": "token_expired", "message": str(e)}
    except Exception as e:
        conn.close()
        yield {"type": "error", "error": "exception", "message": str(e)}
