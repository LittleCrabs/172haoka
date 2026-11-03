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
from datetime import datetime

from .. import config, database
from . import common, retrieve
from .llm import call_llm
from .xhs_events import (SKIP_LABELS, LOG_PATH, read_events,
                         START, DONE, SCANNED, HIT, SENT)


def _dedup_key(post_id, post_content):
    if post_id:
        return "id:" + str(post_id)
    return "hash:" + hashlib.sha1((post_content or "").encode("utf-8")).hexdigest()


def lookup_reply(key):
    """查该帖是否已有生成过的回复。没有则返回 None，有则返回缓存行（含推荐卡）。"""
    conn = database.get_conn()
    try:
        r = conn.execute(
            "SELECT reply_text, replied_at, tone, product_id, product_name, order_url,"
            "       product_fee, product_data, product_operator"
            " FROM xhs_replies WHERE key=?",
            (key,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def save_reply(key, post_id, post_content, region, score, tone, reply_text, ts,
               product=None):
    product = product or {}
    conn = database.get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO xhs_replies"
            "(key, post_id, post_hash, region, should_reply, score, tone, reply_text, replied_at,"
            " product_id, product_name, order_url, product_fee, product_data, product_operator) "
            "VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?,?,?)",
            (key, post_id,
             hashlib.sha1((post_content or "").encode("utf-8")).hexdigest(),
             region, score, tone, reply_text, ts,
             product.get("product_id"), product.get("product_name"),
             product.get("order_url"), product.get("monthly_fee"),
             product.get("data_gb"), product.get("operator")))
        conn.commit()
    finally:
        conn.close()


def pick_recommend(rows):
    """从这次检索到的候选里挑一张「实际推给他的卡」，只写后台、不进回复正文。

    回复本身按合规要求不点名套餐、不附链接，所以对客户来说这张卡是隐形的；
    记录它的意义在于：客户评论/私信过来时，代理点开这条记录就能拿到**客户下单
    版**链接（products.exclusive_url，带推广码），不用再回商品库翻。

    取候选第一名，不另设权重：rows 已经是「禁发地区已排除 + 按佣金与流量排序」
    的结果，即这条帖子地区能办、代理收益最好的那张。
    """
    for r in rows or []:
        url = r["exclusive_url"] if "exclusive_url" in r.keys() else None
        if not url:
            continue
        return {"product_id": r["product_id"],
                "product_name": r["product_name"],
                "order_url": url,
                "monthly_fee": r["monthly_fee"],
                "data_gb": r["data_gb"],
                "operator": r["operator"]}
    return {}


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
# 注意：回复【禁止】点名具体套餐/卡品名称，【禁止】附任何详情页/购买/外链，
# 【禁止】给"去哪办"的渠道建议（保守策略：只共情 + 给判断标准）。
_CONSTRAINTS = """\n\n风格与合规（最高优先级，必须严格遵守）：
1. 必须是「分享类 / 科普类」口吻，像真实用户在有感而发；绝对不要硬广、
   不要出现"私我""加微信""戳我主页""看我简介""主页有"等任何导流话术，不要堆砌卖点。
2. 遵守小红书社区规范：不诱导私下交易、不出现任何联系方式（电话 / 微信 / QQ / 外链）、
   不夸大资费与网速、不承诺办卡结果与时效、不贬低其他运营商、不涉政不涉医不引战。
3. 自然地从帖子话题切入（省钱 / 校园 / 流量不够 / 异地 / 新办卡等），
   再轻描淡写地科普一下怎么选卡、怎么避坑，点到为止，不要写成广告。
4. 【严禁】出现任何具体套餐 / 卡品名称（如"飞旬卡""XX卡"等），【严禁】附任何
   详情页、购买或外链地址。
5. 【严禁】给"去哪办"的渠道建议——"官方App""线下营业厅""官方渠道""正规渠道"
   "找代理"这类提法一律不写。此条不分语境，任何情况下都不出现。
6. 回复只做两件事：接住对方当下的处境（共情），再给【一个】能让他自己判断的标准。
   每次只挑最贴合这条帖子的那一点讲透（合约期长短、通用还是定向、限速阈值、
   优惠期过后涨价、副卡共用规则……挑一个就行），讲完就停。
   【不要】在一句话里并列第二点，也别用"另外…""还有…""其次…"去凑点数。
   不要替对方下"你可以办/值得办"的结论。
   也【不要】写"我之前也遇到过""我也踩过这个坑""我之前也是"这类自称同款经历的开场，
   直接说他现在这件事本身。
7. 结尾【不要】套用每帖都一样的收尾："建议…""希望…能帮到你""祝早日…"
   "记得看清楚条款"这类句式换着来或者干脆不写，也不要每条都用问句收尾。
   只有对方的关键情况确实还没说清时，才可以顺口带一句相关的提问
   （月租多少、每月大概用多少 G、在哪个省），这种提问最多三四条里出现一次，
   其余直接停在判断标准上。
8. 资料里没有的套餐 / 资费不要编；以通用科普与建议为主，不要硬推具体商品。
9. 严禁出现佣金、返佣、代理、分佣、后台、上游渠道等任何内部或商业敏感信息。
10. 用中文，口语化、有温度；40-120 字为宜。"""

# 多人格话术：同一硬性约束下切换不同口吻，避免整站一个调性被识别成机器。
# 文案与默认人格都走配置（设置页「小红书」Tab），这里只留读取逻辑。
# 人格名固定为这四个：配置里缺哪个就回落到默认文案，不会出现「人格消失」。
DEFAULT_TONE = "自然分享"


def _xhs_cfg():
    return config.xhs_cfg()


def tone_system(name):
    """返回指定人格的 system prompt（含共享合规约束）；无效名称回退默认。"""
    c = _xhs_cfg()
    return (c["tones"].get(name) or c["tones"][c["default_tone"]]) + _CONSTRAINTS


def pick_tone(key, tone=None, force=False, exclude=None):
    """决定本次用哪个人格。
    - 显式 tone：直接用；
    - 关闭「自动轮换」时：固定用默认人格；
    - 否则按 key 哈希稳定选一个（同帖始终同口吻），force 时优先换一个不同的。
    """
    c = _xhs_cfg()
    names = list(c["tones"].keys())
    if tone in c["tones"]:
        return tone
    if not c["rotate_tone"]:
        return c["default_tone"]
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

# 各类信号的权重与阈值都走配置（设置页「小红书」Tab），这里不再写死。
# 调权重的典型场景：觉得「资费敏感」放进来太多废话，就把它从 2 调到 1。

# 信号分级（决定"能不能单独成立"）：
# - strong：本身就是明确的号卡需求，单独命中即可回；
# - weak  ：偏泛（"套餐""便宜""学生"），必须两类以上共现才算数；
# - soft  ：只能加分，永不单独成立。
_STRONG_CATS = {"办卡意图", "流量需求"}
_WEAK_CATS = {"资费敏感", "学生校园"}
_SOFT_CATS = {"异地流动", "网络体验"}

# 无关领域词典：这些词说明帖子在聊别的事。
# 典型误判：医院帖的「办卡（就诊卡）」、银行的「办卡（信用卡）」、餐厅的「套餐」。
_OFFTOPIC = {
    "医疗": ("挂号", "门诊", "就诊", "医院", "医生", "专家号", "体检", "牙科",
             "看病", "复诊", "科室", "处方", "住院", "手术", "面诊", "口罩"),
    "金融": ("信用卡", "银行卡", "储蓄卡", "借记卡", "社保卡", "医保卡", "额度",
             "征信", "还款", "年费", "贷款", "理财", "保险", "分期"),
    "餐饮旅游": ("餐厅", "套餐饭", "奶茶", "火锅", "自助餐", "旅游套餐", "酒店",
                 "门票", "机票", "民宿"),
    "生活服务": ("会员卡", "储值卡", "健身卡", "美发卡", "剪发", "年卡", "次卡",
                 "美容"),
    "招聘房产": ("招聘", "岗位", "简历", "二手房", "楼盘", "租房", "中介", "看房"),
}

# 通讯强锚点：出现即说明帖子确实在聊手机卡，前面的领域词不再作为排除依据
# （例：「手机卡套餐对比，顺便问下银行卡能不能实名」仍算目标人群）
_TELCO_ANCHORS = ("手机卡", "流量卡", "号卡", "电话卡", "副卡", "sim卡", "月租",
                  "话费", "运营商", "中国移动", "中国联通", "中国电信", "广电",
                  "流量不够", "流量套餐", "通用流量", "定向流量", "5g", "4g")


def _score_of(signals):
    weights = _xhs_cfg()["weights"]
    return sum(weights.get(s["category"], 1) for s in signals)


def _offtopic_hit(text):
    """返回命中的无关领域（可能有多个）。"""
    return [scene for scene, kws in _OFFTOPIC.items() if any(k in text for k in kws)]


def _has_telco_anchor(text):
    return any(k in text for k in _TELCO_ANCHORS)


def _region_available(region):
    """已知地区时，统计该地区在售且非禁发的手机卡数量。"""
    if not region:
        return None
    try:
        rows = retrieve.product_rows({"category": "手机卡", "region": region}, limit=1000)
        return len(rows)
    except Exception:
        return None


def assess_post(post_content, region=None):
    """规则化判断帖子是否属于目标人群（在调大模型前先筛，省 token）。

    判定顺序（任一不过即不回）：
    1. 无任何信号 → 非潜在客户；
    2. 命中无关领域（医疗/金融/餐饮/招聘…）且全篇没有通讯语境 → 无关内容；
    3. 只有 strong 信号才能单独成立；weak 需两类以上共现；soft 只加分；
    4. 总分低于阈值（设置页可调，默认 2）→ 不回；
    5. 已知地区但该地区在售卡为 0 → 无卡可推，不回。
    """
    text = (post_content or "").lower()
    signals = []
    for cat, kws in _TARGET_SIGNALS.items():
        hit = [k for k in kws if k.lower() in text]
        if hit:
            level = ("strong" if cat in _STRONG_CATS
                     else "weak" if cat in _WEAK_CATS else "soft")
            signals.append({"category": cat, "hits": hit, "level": level})

    cats = {s["category"] for s in signals}
    score = _score_of(signals)
    min_score = _xhs_cfg()["min_score"]
    region_available = _region_available(region)

    def _no(reason):
        return {"should_reply": False, "score": score, "reason": reason,
                "signals": signals, "region_available": region_available}

    if not signals:
        return _no("未识别到办卡/流量/资费/学生等目标人群信号，非潜在客户")

    scenes = _offtopic_hit(text)
    if scenes and not _has_telco_anchor(text):
        return _no("命中%s场景且全篇无「手机卡/流量/月租」等通讯语境，判为无关内容"
                   % "、".join(scenes))

    strong = cats & _STRONG_CATS
    weak_n = len(cats & _WEAK_CATS)
    if not strong and weak_n < 2:
        return _no("仅命中偏泛的%s，缺少明确的办卡/流量需求，易误判故不回"
                   % "、".join(sorted(cats)))

    if score < min_score:
        return _no("信号分 %d 低于阈值 %d" % (score, min_score))

    if region_available == 0:
        return _no("已识别需求，但该地区（%s）暂无可办卡种（候选为空）" % region)

    return {"should_reply": True, "score": score,
            "reason": "命中目标人群信号：%s" % "、".join(sorted(cats)),
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


def assess_detail(post_content, region=None):
    """只做规则判定 + 可办性统计，不调大模型、不落库（供页面「试算」用）。"""
    city = region or extract_region(post_content)
    assess = assess_post(post_content, region=city)
    _ctx, summary, _rows = build_xhs_context(post_content or "", region=city)
    return {
        "region": city,
        "should_reply": assess["should_reply"],
        "score": assess["score"],
        "reason": assess["reason"],
        "signals": assess["signals"],
        "region_available": assess["region_available"],
        "candidates": summary,
    }


# ==================== 机器人运行日志统计 ====================

def _bucket(counter, key):
    if key:
        counter[key] = counter.get(key, 0) + 1


def stats(days=7):
    """汇总机器人日志：扫描/命中/发送量、分数与地区分布、跳过原因、每日趋势、最近一轮。"""
    events = read_events()
    today = datetime.now().strftime("%Y-%m-%d")

    scanned = hits = sent = 0
    today_sent = today_scanned = 0
    score_dist, region_dist, tone_dist, skip_dist, daily = {}, {}, {}, {}, {}
    last_start = last_done = None
    runs = 0

    for e in events:
        ev = e.get("event")
        ts = (e.get("ts") or "")[:10]
        d = daily.setdefault(ts, {"scanned": 0, "hit": 0, "sent": 0}) if ts else None
        if ev == START:
            runs += 1
            last_start = e
        elif ev == DONE:
            last_done = e
        elif ev == SCANNED:
            scanned += 1
            if d is not None:
                d["scanned"] += 1
            if ts == today:
                today_scanned += 1
        elif ev in (HIT, SENT):
            if ev == HIT:
                hits += 1
                if d is not None:
                    d["hit"] += 1
                _bucket(score_dist, e.get("score"))
                _bucket(region_dist, e.get("region") or "未知")
            else:
                sent += 1
                if d is not None:
                    d["sent"] += 1
                if ts == today:
                    today_sent += 1
            _bucket(tone_dist, e.get("tone"))
        elif ev in SKIP_LABELS:
            _bucket(skip_dist, SKIP_LABELS[ev])

    trend = [{"date": k, **v} for k, v in sorted(daily.items())][-days:]
    recent = list(reversed(events[-80:]))

    return {
        "total": {
            "scanned": scanned,
            "hit": hits,
            "sent": sent,
            "runs": runs,
            "hit_rate": round(hits / scanned * 100, 1) if scanned else 0,
            "send_rate": round(sent / hits * 100, 1) if hits else 0,
        },
        "today": {"scanned": today_scanned, "sent": today_sent, "date": today},
        "score_dist": [{"score": k, "count": v} for k, v in sorted(score_dist.items())],
        "region_dist": sorted(
            [{"region": k, "count": v} for k, v in region_dist.items()],
            key=lambda x: -x["count"])[:12],
        "tone_dist": [{"tone": k, "count": v} for k, v in tone_dist.items()],
        "skip_dist": [{"reason": k, "count": v}
                      for k, v in sorted(skip_dist.items(), key=lambda x: -x[1])],
        "trend": trend,
        "last_run": {
            "started_at": (last_start or {}).get("ts"),
            "mode": (last_start or {}).get("mode"),
            "limit": (last_start or {}).get("limit"),
            "max_scan": (last_start or {}).get("max_scan"),
            "finished_at": (last_done or {}).get("ts"),
            "processed": (last_done or {}).get("processed"),
            "scanned": (last_done or {}).get("scanned"),
        },
        "recent": recent,
    }


def reply(post_content, ip=None, region=None, audience=None, dry_run=False,
          post_id=None, force=False, tone=None):
    city = region or extract_region(post_content) or _geoip(ip)  # 显式 > 正文抽取 > IP兜底
    assess = assess_post(post_content, region=city)
    key = _dedup_key(post_id, post_content)
    ctx, summary, cand_rows = build_xhs_context(post_content or "", region=city)
    rec = pick_recommend(cand_rows)

    # 去重：查缓存时一并取回上次用的人格，force 时用于轮换
    cached = None
    if not force:
        cached = lookup_reply(key)
    cached_tone = (cached or {}).get("tone")
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
            "tone": eff_tone, "already_replied": False,
            # 这次「实际上推给他」的那张卡（客户下单链接），只做记录，回复正文里不出现
            "recommend": rec}

    if dry_run:
        # 仅预览组装好的 prompt，不调大模型、不消耗 token
        return {**base, "reply": "", "error": "",
                "prompt": {"system": system, "user": user}, "candidates": summary}

    # 非目标人群：直接跳过，不调大模型（省 token）
    if not assess["should_reply"]:
        return {**base, "reply": "", "error": ""}

    # 去重：已生成过且非强制，则直接复用缓存回复，不调大模型（省 token + 防重复发帖）
    if cached:
        # 老记录可能没有推荐卡（加这个字段之前生成的），用本次算出来的补上展示
        hit_rec = ({"product_id": cached.get("product_id"),
                    "product_name": cached.get("product_name"),
                    "order_url": cached.get("order_url"),
                    "monthly_fee": cached.get("product_fee"),
                    "data_gb": cached.get("product_data"),
                    "operator": cached.get("product_operator")}
                   if cached.get("order_url") else rec)
        return {**base, "recommend": hit_rec, "reply": cached["reply_text"], "error": "",
                "already_replied": True, "replied_at": cached["replied_at"],
                "tone": cached["tone"]}

    if not config.llm_cfg().get("api_key"):
        return {**base, "reply": "", "error":
                "未配置大模型（请在设置页填写 LLM 的 base_url / model / api_key）",
                "prompt": {"system": system, "user": user}}

    try:
        text = call_llm(messages)
    except Exception as e:
        return {**base, "reply": "", "region": city, "error": str(e)}
    # 生成成功：落库（含人格 + 这次推的那张卡的客户下单链接），下次同帖直接复用
    save_reply(key, post_id, post_content, city, assess["score"], eff_tone, text,
               __import__("datetime").datetime.now().isoformat(timespec="seconds"),
               product=rec)
    return {**base, "reply": text, "error": ""}
