"""问答：检索 → 组装 prompt → 调大模型。单用户（代理商）为主，保留对客口径。"""
import json
import time
import urllib.request
import urllib.error
from .. import config, database
from . import common, retrieve

SYSTEM_AGENT = """你是 172 号卡代理商的运营助手，服务对象是代理商本人。

规则：
1. 只依据【商品数据】和【知识库片段】回答，不要引入资料之外的经验。
2. 资料里没有的内容，直接说"资料里没写，建议查后台或问上游"，不要猜。
3. 每条关键结论后用括号标注来源，如（商品 P1）（知识库 K2）。
4. 涉及具体订单状态、物流、审核结果时，明确说明必须去后台按订单号查，
   不要根据知识库推断某个客户的具体进度。
5. 回答用中文，简洁口语化，像在跟同事说话，不要用"您好，感谢咨询"这类模板腔。
6. 如果问题本身有歧义（比如没说地区、没说预算），先问一句再答。
7. 只要推荐或提到具体商品，就必须在该商品后面原样附上它的详情页链接
   （上下文【商品数据】每条末尾的「详情页：...」），一条都不能省。"""

SYSTEM_CUSTOMER = """你是号卡销售的一线客服，直接回复客户。

规则：
1. 只依据【商品信息】和【常见问题】回答，不要编造套餐内容、资费、时效。
2. 绝对不要提及佣金、返佣、结算、代理、分佣、后台操作、上游渠道等内部信息；
   客户问这些，就说"这个我帮您转接专门同事"。
3. 资料里没有的内容，说"这个我需要帮您确认一下"，不要猜。
4. 涉及具体订单状态、物流、审核结果，让客户提供手机号，由人工去后台查，
   不要给出任何预计时间或推断结果。
5. 语气自然亲切但不肉麻，直接说事，不要用"亲""您好，感谢您的咨询"这类模板腔。
6. 信息不全（没说地区、没说预算、没说用途）时，先问一句再推荐。
7. 推荐或提到具体商品时，附上它的详情/办理链接（上下文【商品信息】每条末尾的「详情页：...」），方便客户直接点开查看。"""


def build_context(q, k=6, audience="agent"):
    c = retrieve.parse_constraints(q)
    prods = retrieve.product_rows(c, limit=6) if retrieve.has_product_intent(q) else []
    chunks = retrieve.hybrid(q, k)
    to_customer = audience == "customer"

    try:
        conn = database.get_conn()
        try:
            base = common.h5_base(conn, refresh=True)
        finally:
            conn.close()
    except Exception:
        base = ""

    parts = []
    shown = set()
    if prods:
        lines = ["【商品信息】" if to_customer else "【商品数据】"]
        for i, r in enumerate(prods, 1):
            shown.add(str(r["product_id"]))
            fee = "%s元/月" % r["monthly_fee"] if r["monthly_fee"] else "月租未标注"
            gb = "%sG" % r["data_gb"] if r["data_gb"] else "流量未标注"
            base_line = "[P%d] %s | %s %s %s" % (i, r["product_name"], r["operator"], fee, gb)
            if r["voice_min"]:
                base_line += " %s分钟" % r["voice_min"]
            if not to_customer:
                base_line += " | 佣金%s元(%s) | 结算：%s" % (
                    r["commission"], r["commission_type"], (r["rule"] or "-")[:60])
                if r["remark"]:
                    base_line += " | 下单限制：%s" % r["remark"][:60]
            base_line += " | 禁发：%s" % (r["disable_area"] or "无")[:60]
            if r["age_min"] and r["age_max"]:
                base_line += " | 年龄%s-%s" % (r["age_min"], r["age_max"])
            if to_customer:
                excl = r["exclusive_url"] if "exclusive_url" in r.keys() else None
                if excl:
                    base_line += "\n     专属链接：%s" % excl
                elif base and r["sn"]:
                    base_line += "\n     详情页：%s/PackInfo/Detail/%s" % (base, r["sn"])
            else:
                if base and r["sn"]:
                    base_line += "\n     详情页：%s/PackInfo/Detail/%s" % (base, r["sn"])
            lines.append(base_line)
        parts.append("\n".join(lines))

    kept, detail_n = [], 0
    for h in chunks:
        r = h["row"]
        if r["source"] == "product" and r["doc_id"] in shown:
            if (r["heading"] or "") == "套餐详情" and detail_n < 3:
                detail_n += 1
                kept.append(h)
            continue
        kept.append(h)
    chunks = kept

    if chunks:
        lines = ["【常见问题】" if to_customer else "【知识库片段】"]
        for i, h in enumerate(chunks, 1):
            r = h["row"]
            body = " ".join(r["text"].split())
            lines.append("[K%d] 《%s》%s\n%s" % (i, r["title"], r["heading"] or "", body[:700]))
        parts.append("\n".join(lines))

    return "\n\n".join(parts) or "（没有检索到相关资料）", prods, chunks


def call_llm(messages, cfg=None):
    L = cfg or config.llm_cfg()
    base = (L.get("base_url") or "").rstrip("/")
    body = {
        "model": L.get("model"),
        "messages": messages,
        "temperature": L.get("temperature", 0.3),
        "max_tokens": L.get("max_tokens", 1200),
    }
    extra = L.get("extra")
    if isinstance(extra, dict):
        body.update(extra)
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + L.get("api_key", "")}
    last_err = None
    for attempt in range(4):
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST")
        try:
            with common.urlopen_direct(req, timeout=120) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
            return json.loads(raw.decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 or 500 <= e.code < 600:
                wait = min(8.0, 1.0 * (2 ** attempt))
                ra = e.headers.get("Retry-After")
                if ra and str(ra).isdigit():
                    wait = float(ra)
                if attempt < 3:
                    time.sleep(wait)
                    continue
            raise
    raise last_err


def ask(q, dry_run=False, audience="agent"):
    system = SYSTEM_CUSTOMER if audience == "customer" else SYSTEM_AGENT
    ctx, prods, chunks = build_context(q, audience=audience)
    user = "%s：%s\n\n%s" % ("客户问题" if audience == "customer" else "代理商问题", q, ctx)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    sources = []
    to_customer = audience == "customer"
    for i, r in enumerate(prods, 1):
        url = r["exclusive_url"] if to_customer else r["detail_url"]
        sources.append({"type": "product", "ref": "P%d" % i, "title": r["product_name"],
                        "detail_url": url})
    for i, h in enumerate(chunks, 1):
        sources.append({"type": "kb", "ref": "K%d" % i,
                        "title": h["row"]["title"], "heading": h["row"]["heading"]})

    if not config.llm_cfg().get("api_key"):
        return {"answer": "", "sources": sources,
                "error": "未配置大模型（请在设置页填写 LLM 的 base_url / model / api_key）",
                "prompt": {"system": system, "user": user}}
    if dry_run:
        # dry_run 仅用于预览检索上下文，不调大模型、不消耗 token
        return {"answer": "", "sources": sources, "error": "",
                "prompt": {"system": system, "user": user}}

    try:
        answer = call_llm(messages)
    except Exception as e:
        return {"answer": "", "sources": sources, "error": str(e)}
    return {"answer": answer, "sources": sources, "error": ""}


def build_prompt(q, audience="agent"):
    """构建 system / user / sources，供流式接口复用。"""
    system = SYSTEM_CUSTOMER if audience == "customer" else SYSTEM_AGENT
    ctx, prods, chunks = build_context(q, audience=audience)
    user = "%s：%s\n\n%s" % ("客户问题" if audience == "customer" else "代理商问题", q, ctx)
    sources = []
    to_customer = audience == "customer"
    for i, r in enumerate(prods, 1):
        url = r["exclusive_url"] if to_customer else r["detail_url"]
        sources.append({"type": "product", "ref": "P%d" % i, "title": r["product_name"],
                        "detail_url": url})
    for i, h in enumerate(chunks, 1):
        sources.append({"type": "kb", "ref": "K%d" % i,
                        "title": h["row"]["title"], "heading": h["row"]["heading"]})
    return system, user, sources


def call_llm_stream(messages, cfg=None):
    """流式调用大模型，逐段 yield 文本增量（OpenAI 兼容 SSE）。"""
    L = cfg or config.llm_cfg()
    base = (L.get("base_url") or "").rstrip("/")
    body = {
        "model": L.get("model"),
        "messages": messages,
        "temperature": L.get("temperature", 0.3),
        "max_tokens": L.get("max_tokens", 1200),
        "stream": True,
    }
    extra = L.get("extra")
    if isinstance(extra, dict):
        body.update(extra)
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + L.get("api_key", "")}
    req = urllib.request.Request(base + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    with common.urlopen_direct(req, timeout=120) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
            except Exception:
                continue
