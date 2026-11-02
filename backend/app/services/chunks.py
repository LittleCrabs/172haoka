"""把商品行 + 知识库文档转成检索用文本块，写入 kb_chunks 与 FTS 索引。

一行商品 = 一个 chunk，不拆碎（套餐信息拆开就失去意义）。
整表重建（幂等）：先清空 chunk/FTS/embeddings，再全量写入。
"""
import datetime as dt
import json
import re
from .. import database
from . import specs

PRODUCT_ROWID_BASE = 1000000
KB_ROWID_BASE = 2000000

AGENT_ONLY_SECTIONS = {"温馨提示"}
CUSTOMER_SECTIONS = ["产品套餐", "主套餐", "套外资费", "优惠详情", "合约期",
                     "快递方式", "激活方式", "充值链接", "办卡年龄",
                     "不发货地区", "定向范围", "复机及注销方式"]

HARD_TERMS = ("佣金", "结算", "分佣", "抽成", "返佣", "提现", "上级", "下级",
              "二次包装", "套取")
SOFT_TERMS = ("代理", "后台", "上游")
AGENT_VOICE = ("代理看的版本", "给直属代理", "很多代理", "代理可以", "代理把",
               "代理需要", "代理们", "跟客户讲", "怎么跟客户", "让代理")


def is_internal(seg):
    if any(t in seg for t in HARD_TERMS):
        return True
    if any(t in seg for t in AGENT_VOICE):
        return True
    return sum(1 for t in SOFT_TERMS if t in seg) >= 2


def sanitize_shared(text):
    kept, dropped = [], 0
    for seg in re.split(r"(?<=[。！？!?\n])", text):
        if not seg.strip():
            continue
        if is_internal(seg):
            dropped += 1
            continue
        kept.append(seg)
    return "".join(kept).strip(), dropped


def load_details(conn):
    try:
        rows = conn.execute("SELECT product_id, sections FROM product_details").fetchall()
    except Exception:
        return {}
    out = {}
    for r in rows:
        try:
            out[r["product_id"]] = json.loads(r["sections"] or "{}")
        except Exception:
            continue
    return out


def detail_text(secs):
    lines = []
    for k in CUSTOMER_SECTIONS:
        v = (secs.get(k) or "").strip()
        if not v or v in ("无", "暂无"):
            continue
        lines.append("%s：%s" % (k, v.replace("\n", " ")))
    return "\n".join(lines)


def product_text(r, secs=None):
    parts = ["商品名称：%s" % r["product_name"]]
    meta = ["运营商：%s" % (r["operator"] or "未知"), "类型：%s" % (r["category"] or "手机卡")]
    if r["monthly_fee"] is not None:
        meta.append("月租：%s元/月" % r["monthly_fee"])
    if r["data_gb"] is not None:
        meta.append("流量：%sG" % r["data_gb"])
    if r["voice_min"] is not None:
        meta.append("通话：%s分钟" % r["voice_min"])
    parts.append(" | ".join(meta))
    if r["area_read"] or r["area"]:
        parts.append("归属地：%s" % (r["area_read"] or r["area"]))
    if r["disable_area"]:
        parts.append("禁发地区：%s" % r["disable_area"])
    if r["age_min"] and r["age_max"]:
        parts.append("年龄要求：%s-%s周岁" % (r["age_min"], r["age_max"]))
    if r["keywords"]:
        parts.append("卖点：%s" % r["keywords"])
    parts.append("当前状态：%s" % ("在售" if r["on_sale"] else "已下架"))
    return "\n".join(parts)


CHUNK_SIZE = 500
CHUNK_OVERLAP = 80

SECTION_RE = re.compile(
    r"^\s*(?:\d{1,2}\s*、"
    r"|第[一二三四五六七八九十百]+\s*[、.．章节步种部分]"
    r"|[一二三四五六七八九十]+\s*、)")


def looks_like_heading(line):
    s = line.strip()
    if not s or len(s) > 26 or len(s) < 4:
        return False
    if s.count("X") >= 2 or sum(c.isdigit() for c in s) > 3:
        return False
    if not re.search(r"[\u4e00-\u9fa5]", s):
        return False
    if s[-1] in "。，；：！？,;、":
        return False
    return bool(SECTION_RE.match(s))


def split_kb(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    lines = text.split("\n")
    if any(l.lstrip().startswith("#") for l in lines):
        return _split_md(lines, size)
    return _split_para(text, size, overlap)


def _split_md(lines, size):
    chunks, cur, heading = [], [], ""

    def flush():
        body = "\n".join(cur).strip()
        if body:
            chunks.append((heading, body))

    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("#"):
            flush()
            heading = s.lstrip("#").strip()
            cur = []
            continue
        cur.append(s)
        if len("\n".join(cur)) >= size:
            flush()
            cur = []
    flush()
    return chunks


def _split_para(text, size, overlap):
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    chunks, cur, heading = [], [], ""
    for p in paras:
        if looks_like_heading(p):
            body = "\n".join(cur).strip()
            if body:
                chunks.append((heading, body))
                cur = []
            heading = p
            continue
        cur.append(p)
        if len("".join(cur)) >= size:
            chunks.append((heading, "\n".join(cur)))
            tail = "\n".join(cur)[-overlap:]
            cur = [tail]
    body = "\n".join(cur).strip()
    if body and (heading and len(body) > 8 or len(body) > 20):
        chunks.append((heading, body))
    return chunks


def rebuild(conn=None):
    own = conn is None
    conn = conn or database.get_conn()
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("DELETE FROM kb_fts")
    conn.execute("DELETE FROM kb_chunks")
    conn.execute("DELETE FROM embeddings")

    n_prod = 0
    details = load_details(conn)
    for r in conn.execute("SELECT * FROM products").fetchall():
        cid = "product:%s" % r["product_id"]
        secs = details.get(r["product_id"]) or {}
        txt = product_text(r)
        conn.execute(
            "INSERT INTO kb_chunks(chunk_id, source, doc_id, audience, title, heading, seq, text, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, "product", str(r["product_id"]), "shared",
             r["product_name"], "商品信息", 0, txt, ts))
        conn.execute("INSERT INTO kb_fts(rowid, chunk_id, title, text) VALUES (?,?,?,?)",
                     (PRODUCT_ROWID_BASE + int(r["product_id"]), cid, r["product_name"], txt))
        n_prod += 1

        dtext = detail_text(secs)
        if dtext:
            did = "%s:detail" % cid
            conn.execute(
                "INSERT INTO kb_chunks(chunk_id, source, doc_id, audience, title, heading, seq, text, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (did, "product", str(r["product_id"]), "shared",
                 r["product_name"], "套餐详情", 2, dtext, ts))
            conn.execute("INSERT INTO kb_fts(rowid, chunk_id, title, text) VALUES (?,?,?,?)",
                         (1400000 + int(r["product_id"]), did, "%s 套餐详情" % r["product_name"], dtext))

        note = (secs.get("温馨提示") or "").strip()
        if note and note not in ("无", "暂无"):
            nid = "%s:note" % cid
            ntxt = "平台规则提醒（%s）：%s" % (r["product_name"], note.replace("\n", " "))
            conn.execute(
                "INSERT INTO kb_chunks(chunk_id, source, doc_id, audience, title, heading, seq, text, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (nid, "product", str(r["product_id"]), "agent",
                 r["product_name"], "平台规则提醒", 1, ntxt, ts))
            conn.execute("INSERT INTO kb_fts(rowid, chunk_id, title, text) VALUES (?,?,?,?)",
                         (1500000 + int(r["product_id"]), nid, r["product_name"], ntxt))

    n_kb = 0
    dropped_total = 0
    for d in conn.execute("SELECT * FROM kb_docs ORDER BY doc_id").fetchall():
        aud = d["audience"] or "agent"
        for seq, (heading, body) in enumerate(split_kb(d["content"] or "")):
            cid = "kb:%s:%d" % (d["doc_id"], seq)
            txt = "%s\n%s" % (heading, body) if heading else body
            if aud != "agent":
                txt, dropped = sanitize_shared(txt)
                dropped_total += dropped
                if len(txt.strip()) < 30:
                    continue
            conn.execute(
                "INSERT INTO kb_chunks(chunk_id, source, doc_id, audience, title, heading, seq, text, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (cid, "kb", d["doc_id"], aud, d["title"], heading, seq, txt, ts))
            conn.execute("INSERT INTO kb_fts(rowid, chunk_id, title, text) VALUES (?,?,?,?)",
                         (KB_ROWID_BASE + n_kb, cid, "%s %s" % (d["title"] or "", heading), txt))
            n_kb += 1

    conn.commit()
    dist = dict(conn.execute("SELECT audience, count(*) FROM kb_chunks GROUP BY audience").fetchall())

    # 顺手重算流量结构
    specs.rebuild(conn)

    if own:
        conn.close()
    return {"products": n_prod, "kb_chunks": n_kb, "audience_dist": dist,
            "dropped_internal_sentences": dropped_total}
