"""小红书引流回复生成。

思路：复用现有检索能力，按帖子正文（通常含 IP 属地）抽取地区，筛选合规可办的号卡，
再调大模型产出「分享类 / 科普类」风格、符合小红书社区规范的回复。

安全边界：
- 上下文**只用商品数据**，绝不引入代理商知识库（操作手册），避免泄露内部信息。
- system prompt 硬约束：不导流、不出现联系方式、不夸大、不贬低同行、只走分享/科普口吻。
- 商品上下文不含佣金 / 结算 / 代理等内部字段。
"""
import hashlib
import json
import re
import urllib.request
import urllib.error
from .. import config, database
from . import common, retrieve
from .ask import call_llm


def _dedup_key(post_id, post_content):
    if post_id:
        return "id:" + str(post_id)
    return "hash:" + hashlib.sha1((post_content or "").encode("utf-8")).hexdigest()


def lookup_reply(key):
    """查该帖是否已有生成过的回复。返回 (reply_text, replied_at, tone) 或 (None, None, None)。"""
    conn = database.get_conn()
    try:
        r = conn.execute(
            "SELECT reply_text, replied_at, tone FROM xhs_replies WHERE key=?",
            (key,)).fetchone()
        if r:
            return (r["reply_text"], r["replied_at"], r["tone"])
        return (None, None, None)
    finally:
        conn.close()


def save_reply(key, post_id, post_content, region, score, tone, reply_text, ts):
    conn = database.get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO xhs_replies"
            "(key, post_id, post_hash, region, should_reply, score, tone, reply_text, replied_at) "
            "VALUES(?,?,?,?,1,?,?,?,?)",
            (key, post_id,
             hashlib.sha1((post_content or "").encode("utf-8")).hexdigest(),
             region, score, tone, reply_text, ts))
        conn.commit()
    finally:
        conn.close()


def extract_region(text):
    """从小红书帖子抽地区，优先级：
    1) 显式「IP属地：浙江 / IP属地:杭州 / IP属地 江苏」这类平台自带属地；
    2) 全文扫描省份 / 城市名。
    返回省份或城市名（供禁发过滤与展示），解析不到返回 None。
    """
    if not text:
        return None
    # 1) IP 属地（小红书几乎都带）
    m = re.search(r'IP\s*属地[：:\s]*([\u4e00-\u9fa5]{2,4})', text)
    if m:
        tok = m.group(1)
        if tok in retrieve.PROVINCES:
            return tok
        if tok in retrieve.CITIES or tok in retrieve.CITY_PROVINCE:
            return tok
        for prov in retrieve.PROVINCES:      # 「浙江省」→「浙江」
            if tok.startswith(prov):
                return prov
        for city in retrieve.CITY_PROVINCE:  # 「杭州市」→「杭州」
            if tok.startswith(city):
                return city
    # 2) 全文扫描：先省份后城市
    for prov in retrieve.PROVINCES:
        if prov in text:
            return prov
    for city in retrieve.CITIES:
        if city in text:
            return city
    return None


# 共享的硬性合规约束（所有人格都必须遵守，最后拼接进每条 system prompt）。
# 注意：回复【禁止】点名具体套餐/卡品名称，也【禁止】附任何详情页/购买/外链。
_CONSTRAINTS = """\n\n风格与合规（最高优先级，必须严格遵守）：
1. 必须是「分享类 / 科普类」口吻，像真实用户在有感而发；绝对不要硬广、
   不要出现"私我""加微信""戳我主页""看我简介""主页有"等任何导流话术，不要堆砌卖点。
2. 遵守小红书社区规范：不诱导私下交易、不出现任何联系方式（电话 / 微信 / QQ / 外链）、
   不夸大资费与网速、不承诺办卡结果与时效、不贬低其他运营商、不涉政不涉医不引战。
3. 自然地从帖子话题切入（省钱 / 校园 / 流量不够 / 异地 / 新办卡等），
   再轻描淡写地科普一下怎么选卡、怎么避坑，点到为止，不要写成广告。
4. 【严禁】在回复中出现任何具体套餐 / 卡品名称（如"飞旬卡""XX卡"等），也【严禁】
   附任何详情页、购买或外链地址。若需要引导，只说"可以去运营商官方 App 或线下营业厅
   了解当前大流量低月租活动"这类通用建议——绝不点名具体产品、绝不给链接。
5. 资料里没有的套餐 / 资费不要编；以通用科普与建议为主，不要硬推具体商品。
6. 严禁出现佣金、返佣、代理、分佣、后台、上游渠道等任何内部或商业敏感信息。
7. 用中文，口语化、有温度；40-120 字为宜。"""

# 多人格话术：同一硬性约束下切换不同口吻，避免整站一个调性被识别成机器。
TONES = {
    "自然分享": "你是帮 172 号卡代理商在小红书做内容引流的运营助手，"
                "像真实用户在有感而发地分享，亲切自然。",
    "理性数码": "你是懂行的数码博主，在小红书做内容引流，语气客观、讲参数和性价比，"
                "像在认真给建议而不是推销。",
    "省钱过来人": "你是精打细算的过来人，在小红书做内容引流，语气像劝朋友避坑省钱，"
                  "带点生活经验感。",
    "在校学长": "你是在校大学生，在小红书做内容引流，语气像同校学长学姐分享校园实用经验，"
                "贴近宿舍 / 校园场景。",
}
DEFAULT_TONE = "自然分享"
_SYSTEM_XHS = TONES[DEFAULT_TONE] + _CONSTRAINTS  # 兼容引用


def tone_system(name):
    """返回指定人格的 system prompt（含共享合规约束）；无效名称回退默认。"""
    return (TONES.get(name) or TONES[DEFAULT_TONE]) + _CONSTRAINTS


def pick_tone(key, tone=None, force=False, exclude=None):
    """决定本次用哪个人格。
    - 显式 tone：直接用；
    - 否则 auto：按 key 哈希稳定选一个（同帖始终同口吻）；
    - force 且 auto 且有 exclude（上次用的）：优先选一个不同的，做轮换。
    """
    names = list(TONES.keys())
    if tone in TONES:
        return tone
    if force and exclude in names and len(names) > 1:
        others = [n for n in names if n != exclude]
        return others[abs(hash(key)) % len(others)]
    return names[abs(hash(key)) % len(names)]


# 目标人群信号：命中任一类即视为潜在办卡 / 用卡需求者（172号卡买家画像）。
_TARGET_SIGNALS = {
    "流量需求": ("流量", "流量不够", "流量少", "流量贵", "流量包", "流量卡", "不够用",
              "刷剧", "打游戏", "热点", "共享流量", "上网"),
    "资费敏感": ("月租", "套餐", "资费", "话费", "省钱", "划算", "便宜", "实惠",
              "性价比", "最省", "低价"),
    "办卡意图": ("办卡", "选卡", "换卡", "新办卡", "副卡", "手机卡", "号卡", "办张",
              "办一张", "申请卡", "开卡"),
    "学生校园": ("学生", "校园", "大学", "考研", "实习", "宿舍", "校园卡"),
    "异地流动": ("异地", "外地", "老家", "返乡", "跨省", "搬家", "出差", "务工"),
    "网络体验": ("wifi", "信号", "网速", "断网", "卡顿", "连不上"),
}

# 各类信号的权重（办卡意图最硬，其余按相关性给分）。score 供设阈值 / 排序优先级。
_SCORE_WEIGHTS = {
    "办卡意图": 3,
    "流量需求": 2,
    "资费敏感": 2,
    "学生校园": 2,
    "异地流动": 1,
    "网络体验": 1,
}


def _score_of(signals):
    return sum(_SCORE_WEIGHTS.get(s["category"], 1) for s in signals)


def assess_post(post_content, region=None):
    """规则化判断帖子是否属于目标人群（在调大模型前先筛，省 token）。
    返回 {should_reply, reason, signals, region_available}。
    - 无任一类信号 → 非潜在客户，不回；
    - 已知地区但该地区在售且非禁发卡为 0 → 无卡可推，不回；
    - 其余 → 值得回。
    """
    text = (post_content or "").lower()
    signals = []
    for cat, kws in _TARGET_SIGNALS.items():
        hit = [k for k in kws if k.lower() in text]
        if hit:
            signals.append({"category": cat, "hits": hit})

    # 地区可办性：已知地区时，统计该地区在售且非禁发的卡数
    region_available = None
    if region:
        try:
            conn = database.get_conn()
            try:
                rows = retrieve.product_rows({"category": "手机卡", "region": region},
                                             limit=1000)
                region_available = len(rows)
            finally:
                conn.close()
        except Exception:
            region_available = None

    if not signals:
        return {"should_reply": False, "score": 0,
                "reason": "未识别到办卡/流量/资费/学生/异地等目标人群信号，非潜在客户",
                "signals": [], "region_available": region_available}
    if region_available == 0:
        return {"should_reply": False, "score": _score_of(signals),
                "reason": "已识别需求，但该地区（%s）暂无可办卡种（候选为空）" % region,
                "signals": signals, "region_available": 0}
    return {"should_reply": True, "score": _score_of(signals),
            "reason": "命中目标人群信号：%s" % "、".join(s["category"] for s in signals),
            "signals": signals, "region_available": region_available}


def _geoip(ip):
    """可选兜底：尝试把 IP 解析成地区（帖子通常已含 IP 属地，此步失败不影响主流程）。"""
    if not ip:
        return None
    try:
        p = config.proxy()
        opener = urllib.request.build_opener()
        if p:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": p, "https": p}))
        req = urllib.request.Request(
            "https://ipapi.co/%s/json/" % ip,
            headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=4) as r:
            data = json.loads(r.read().decode())
        return data.get("region") or data.get("city") or data.get("country_name")
    except Exception:
        return None


def build_xhs_context(post_content, region=None, limit=6):
    """只取商品（按地区排除禁发卡）做【中性可办性摘要】——不点名套餐、不给链接，
    仅告知该地区是否有低价大流量卡及大致区间，供模型判断可行性，回复中不得外显名称/链接。
    """
    c = retrieve.parse_constraints(post_content or "")
    if region:
        c["region"] = region
    rows = retrieve.product_rows(c, limit=limit)

    n = len(rows)
    if n:
        fees = [r["monthly_fee"] for r in rows if r["monthly_fee"]]
        gbs = [r["data_gb"] for r in rows if r["data_gb"]]
        fee_range = "%d-%d元/月" % (min(fees), max(fees)) if fees else "月租未标注"
        gb_range = "%d-%dG" % (min(gbs), max(gbs)) if gbs else "流量未标注"
        avail = ("该地区当前有 %d 张在售的低价大流量手机卡（月租约 %s、流量约 %s），"
                 "但回复中不得点名具体套餐、不得附任何链接。" % (n, fee_range, gb_range))
    else:
        avail = "未检索到该地区在售的匹配卡种，仅做通用科普 / 共情即可，不要硬推。"

    summary = {"count": n,
               "fee_range": fee_range if n else "",
               "gb_range": gb_range if n else ""}
    ctx = ("【候选号卡概况】（仅供判断可行性，回复中不得点名具体套餐，也不得附任何链接）\n"
           + avail)
    return ctx, summary, rows


def reply(post_content, ip=None, region=None, audience=None, dry_run=False,
          post_id=None, force=False, tone=None):
    city = region or extract_region(post_content) or _geoip(ip)  # 显式 > 正文抽取 > IP兜底
    assess = assess_post(post_content, region=city)
    key = _dedup_key(post_id, post_content)
    ctx, summary, _rows = build_xhs_context(post_content or "", region=city)

    # 去重：查缓存时一并取回上次用的人格，force 时用于轮换
    cached_text, cached_at, cached_tone = ("", None, None)
    if not force:
        cached_text, cached_at, cached_tone = lookup_reply(key)
    eff_tone = pick_tone(key, tone=tone, force=force, exclude=cached_tone)
    system = tone_system(eff_tone)

    user = (
        "【用户帖子】\n%s\n\n"
        "【帖子地区 / IP 属地】%s\n"
        "【目标人群（可选）】%s\n\n"
        "%s"
    ) % (post_content or "(空)", city or "未知", audience or "不限", ctx)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    # 每条返回都带判定字段，供自动化判读
    base = {"region": city, "should_reply": assess["should_reply"],
            "score": assess["score"], "reason": assess["reason"],
            "signals": assess["signals"],
            "region_available": assess["region_available"],
            "tone": eff_tone, "already_replied": False}

    if dry_run:
        # 仅预览组装好的 prompt，不调大模型、不消耗 token
        return {**base, "reply": "", "error": "",
                "prompt": {"system": system, "user": user}, "candidates": summary}

    # 非目标人群：直接跳过，不调大模型（省 token）
    if not assess["should_reply"]:
        return {**base, "reply": "", "error": ""}

    # 去重：已生成过且非强制，则直接复用缓存回复，不调大模型（省 token + 防重复发帖）
    if cached_text:
        return {**base, "reply": cached_text, "error": "",
                "already_replied": True, "replied_at": cached_at, "tone": cached_tone}

    if not config.llm_cfg().get("api_key"):
        return {**base, "reply": "", "error":
                "未配置大模型（请在设置页填写 LLM 的 base_url / model / api_key）",
                "prompt": {"system": system, "user": user}}

    try:
        text = call_llm(messages)
    except Exception as e:
        return {**base, "reply": "", "region": city, "error": str(e)}
    # 生成成功：落库（含人格），下次同帖直接复用
    save_reply(key, post_id, post_content, city, assess["score"], eff_tone, text,
               __import__("datetime").datetime.now().isoformat(timespec="seconds"))
    return {**base, "reply": text, "error": ""}
