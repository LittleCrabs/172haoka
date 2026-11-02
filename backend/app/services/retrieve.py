"""混合检索：结构化过滤（SQL） + 中文二元组 TF-IDF 文本召回 + 向量召回。

为什么不用 FTS5 做主力：trigram 要求 token ≥3 字，而「佣金」「激活」「广电」这些
2 字词必然 0 命中。改用二元组 TF-IDF 全表扫描，205 块一次 <10ms 足够。
kb_fts 表保留，语料涨到几万块再切 BM25。

单用户（代理商）场景：不再按受众隔离，全部可见。
"""
import math
import re
from .. import database
from . import embed

OPERATORS = ("移动", "联通", "电信", "广电")
PROVINCES = ("北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海",
             "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
             "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西",
             "甘肃", "青海", "宁夏", "新疆")
CITIES = ("济南", "青岛", "苏州", "无锡", "常州", "东营", "沈阳", "西安", "成都",
          "武汉", "南京", "昆明", "南宁", "合肥", "石家庄", "郑州", "长沙", "杭州",
          "广州", "深圳", "重庆", "南昌", "太原", "哈尔滨", "长春", "大连", "福州",
          "厦门", "贵阳", "兰州", "乌鲁木齐", "呼和浩特", "海口", "银川", "西宁")

# 城市 → 省份（判断禁发时省份也要一起排除）
CITY_PROVINCE = {
    "济南": "山东", "青岛": "山东", "东营": "山东", "苏州": "江苏", "无锡": "江苏",
    "常州": "江苏", "南京": "江苏", "沈阳": "辽宁", "大连": "辽宁", "西安": "陕西",
    "成都": "四川", "武汉": "湖北", "昆明": "云南", "南宁": "广西", "合肥": "安徽",
    "石家庄": "河北", "郑州": "河南", "长沙": "湖南", "杭州": "浙江", "广州": "广东",
    "深圳": "广东", "南昌": "江西", "太原": "山西", "哈尔滨": "黑龙江", "长春": "吉林",
    "福州": "福建", "厦门": "福建", "贵阳": "贵州", "兰州": "甘肃", "乌鲁木齐": "新疆",
    "呼和浩特": "内蒙古", "海口": "海南", "银川": "宁夏", "西宁": "青海",
}


def parse_constraints(q):
    """从自然语言里抽硬约束。宁可漏抽，不要错抽。"""
    c = {}
    for op in OPERATORS:
        if op in q:
            c["operator"] = op
            break
    m = re.search(r"(\d+)\s*(?:元|块)(?:以内|以下|之内|内)?", q)
    if m:
        c["max_fee"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:G|GB)\s*(?:以上|起|\+)?", q)
    if m:
        c["min_data"] = int(m.group(1))
    # 「大流量」但没给具体数字 → 设温和下限（80G 这类能通过，排除 5G 小卡）
    if "min_data" not in c and re.search(r"大流量|流量多|流量大", q):
        c["min_data"] = 50
    # 「越低越好 / 便宜 / 最省」→ 按月租升序
    if re.search(r"越低越好|越便宜越好|便宜|最低|最省|省钱|实惠|划算", q):
        c["sort"] = "fee_asc"
    if "宽带" in q:
        c["category"] = "宽带"
    elif re.search(r"[卡号]|手机|流量", q):
        c["category"] = "手机卡"
    for city in CITIES:
        if city in q:
            c["region"] = city
            break
    else:
        for prov in PROVINCES:
            if prov in q:
                c["region"] = prov
                break
    return c


def product_rows(c, limit=10):
    where, args = ["p.category = ?"], [c.get("category", "手机卡")]
    if c.get("operator"):
        where.append("p.operator = ?")
        args.append(c["operator"])
    if c.get("max_fee"):
        where.append("p.monthly_fee <= ?")
        args.append(c["max_fee"])
    if c.get("min_data"):
        where.append("p.data_gb >= ?")
        args.append(c["min_data"])
    if c.get("region"):
        # 「在杭州」= 能在杭州办 → 排除禁发地区含杭州/浙江的卡（不是去找名字带杭州的卡）
        reg = c["region"]
        prov = CITY_PROVINCE.get(reg, reg)
        where.append("(p.disable_area IS NULL OR p.disable_area = '' OR "
                     "(p.disable_area NOT LIKE ? AND p.disable_area NOT LIKE ?))")
        args += ["%" + reg + "%", "%" + prov + "%"]
    where.append("p.on_sale = 1")
    if c.get("sort") == "fee_asc":
        order = "ORDER BY (p.monthly_fee IS NULL), p.monthly_fee ASC, p.data_gb DESC"
    elif c.get("min_data"):
        order = "ORDER BY p.data_gb DESC, (p.monthly_fee IS NULL), p.monthly_fee ASC"
    else:
        order = "ORDER BY p.commission DESC, p.data_gb DESC"
    sql = "SELECT p.* FROM products p WHERE %s %s LIMIT ?" % (" AND ".join(where), order)
    conn = database.get_conn()
    try:
        return conn.execute(sql, args + [limit]).fetchall()
    finally:
        conn.close()


PRODUCT_HINTS = ("推荐", "办卡", "选卡", "哪款", "哪张", "哪个好", "有什么好",
                 "多少钱", "月租", "便宜", "资费", "划算")


def has_product_intent(q):
    c = parse_constraints(q)
    if any(k in c for k in ("operator", "max_fee", "min_data", "region")):
        return True
    return any(h in q for h in PRODUCT_HINTS)


STOP = {"怎么", "什么", "可以", "能不", "不能", "一下", "的话", "我们", "你们",
        "请问", "多少", "哪些", "这个", "那个", "有没", "没有", "是不", "不是",
        "如何", "怎样", "需要", "如果", "但是", "因为", "所以", "然后",
        "为什", "么我", "我的", "还没", "单还", "么时", "为么"}


def bigrams(s):
    s = s.lower()
    grams = set()
    for seg in re.findall(r"[\u4e00-\u9fa5]+|[a-z0-9]+", s):
        if re.match(r"[a-z0-9]", seg):
            grams.add(seg)
        else:
            for i in range(len(seg) - 1):
                grams.add(seg[i:i + 2])
    return grams


def text_search(q, k=6):
    conn = database.get_conn()
    try:
        chunks = conn.execute(
            "SELECT c.chunk_id, c.source, c.doc_id, c.audience, c.title, c.heading, c.text "
            "FROM kb_chunks c").fetchall()
    finally:
        conn.close()
    if not chunks:
        return []

    qg = bigrams(q) - STOP
    if not qg:
        return []

    docs = []
    for c in chunks:
        body = bigrams(c["text"])
        head = bigrams((c["title"] or "") + " " + (c["heading"] or ""))
        docs.append((c, body, head))

    n = len(docs)
    df = {g: sum(1 for _, b, h in docs if g in b or g in h) for g in qg}
    idf = {g: math.log((n + 1) / (df[g] + 0.5)) for g in qg}
    total = sum(idf.values()) or 1.0

    scored = []
    for c, body, head in docs:
        hit = [g for g in qg if g in body or g in head]
        if not hit:
            continue
        raw = sum(idf[g] for g in hit)
        head_hit = [g for g in qg if g in head]
        head_ratio = sum(idf[g] for g in head_hit) / total
        score = 0.55 * raw / total + 0.25 * len(hit) / len(qg) + 0.20 * head_ratio
        scored.append((score, len(hit), c))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [(s, c) for s, _, c in scored[:k]]


def vector_search(q, k=6):
    if not embed.enabled():
        return []
    conn = database.get_conn()
    try:
        rows = conn.execute(
            "SELECT e.chunk_id, e.vec, c.source, c.doc_id, c.audience, c.title, c.heading, c.text "
            "FROM embeddings e JOIN kb_chunks c ON c.chunk_id = e.chunk_id").fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    try:
        qv = embed.embed_texts([q])[0]
    except Exception as e:
        print("（向量检索跳过：%s）" % e)
        return []
    scored = []
    for r in rows:
        scored.append((embed.cosine(qv, embed.unpack(r["vec"])), r))
    scored.sort(key=lambda x: -x[0])
    return [(s, r) for s, r in scored[:k]]


def hybrid(q, k=6):
    merged = {}
    for i, (s, r) in enumerate(vector_search(q, k)):
        merged[r["chunk_id"]] = {"score": 0.55 * (s - i * 0.02), "row": r, "via": "vec"}
    for s, r in text_search(q, k):
        d = merged.get(r["chunk_id"])
        if d is None:
            merged[r["chunk_id"]] = {"score": 0.45 * s, "row": r, "via": "text"}
        else:
            d["score"] += 0.45 * s
            d["via"] += "+text"
    out = sorted(merged.values(), key=lambda d: -d["score"])
    return out[:k]
