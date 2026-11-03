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


# ---------------- 文本清洗 ----------------
# 上游有三个来源会往正文里塞脏东西，全都在没有提示的情况下污染了阅读体验：
#   1. H5 详情页抓取：&nbsp; 与 \x03（原站拿 ETX 当有序列表的换行标记）
#   2. 语雀导出：零宽字符、三四层连续空行
#   3. 截图 OCR：一行一个标签（"已签收 / 查看物流 / 订单详情"），
#      直接按行渲染会竖排成一列，看上去像排版坏了
# 清洗放在入库前做，历史数据用 clean_existing() 就地重刷，不动向量。

_ETX_RE = re.compile(r"\x03")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZW_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_MANY_NL_RE = re.compile(r"\n{3,}")
_ENTITY_RE = re.compile(r"&(#\d{1,6}|#x[0-9a-fA-F]{1,6}|[a-zA-Z]{2,8});")

_ENTITY_MAP = {
    "nbsp": " ", "ensp": " ", "emsp": " ", "thinsp": " ", "amp": "&",
    "lt": "<", "gt": ">", "quot": '"', "apos": "'", "middot": "·",
    "hellip": "…", "mdash": "—", "ndash": "–", "times": "x",
    "ldquo": "“", "rdquo": "”", "lsquo": "‘", "rsquo": "’",
}

FRAG_MAX = 14   # 短于这个长度、又不在列表里的行，视为 OCR / 布局碎片
FRAG_AVG = 20   # 整段平均行长低于这个数才做合并，正常段落一律不动
_LIST_HEAD_RE = re.compile(
    r"^\s*(?:\d{1,2}\s*[.、．)）]|[一二三四五六七八九十]{1,2}\s*[、.]"
    r"|[·•▪▫◦*+\-–—]|[（(]\s*\d{1,2}\s*[)）])")
# 「商品名称：xxx」「归属地：xx」这种字段行是刻意一行一个的，合并会毁掉结构
_KV_HEAD_RE = re.compile(r"^([^：:\n]{2,10})[：:]")
_SENT_END = "。！？，；、：.!?,;:"


def _is_frag_line(s):
    """这一行像不像截图 OCR / 布局抖动切出来的碎片。"""
    s = (s or "").strip()
    if not s or len(s) > FRAG_MAX:
        return False
    if _LIST_HEAD_RE.match(s):
        return False                      # 有序条目自带层级，合并就没了
    m = _KV_HEAD_RE.match(s)
    # 「商品名称：xx」是真字段行；「15:54」只是长得像，冒号前面没有中文就不算
    if m and re.search(r"[\u4e00-\u9fa5]", m.group(1)):
        return False
    if s[-1] in _SENT_END:
        return False                      # 以标点收尾的是正常句子
    return True


def _entity(m):
    key = m.group(1)
    if key.startswith("#"):
        try:
            cp = int(key[2:], 16) if key[1:2].lower() == "x" else int(key[1:])
        except ValueError:
            return ""
        return chr(cp) if 31 < cp < 0x10000 else ""
    return _ENTITY_MAP.get(key.lower(), m.group(0))


def _merge_fragments(text):
    """把被 OCR / 布局切碎的短行用 · 拼成一行。

    逐行扫，连续 ≥3 个碎片行合成一行；碎片组内部的空行一并吃掉（OCR 出来的
    碎片经常被空行隔开，按「空行分块」判断会漏掉这些，页面上照样竖排一列）。

    三个不合并的前提（宁可留着让人自己删，也别把结构搞乱）：
      1. 连续不足 3 行——两个短行可能只是恰好都短
      2. 以标点收尾——正常句子会有 。！？，；
      3. 有序条目、「字段：值」、超长行——它们自带层级
    """
    out, run = [], []
    blanks = 0

    def flush():
        nonlocal blanks
        if run:
            if len(run) >= 3:
                out.append(" · ".join(run))
            else:
                out.extend(run)
            run.clear()
        if blanks:
            out.append("")       # 碎片组后面的段间距要还给下一段
            blanks = 0

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            if run:
                blanks += 1      # 组内空行先攒着，合并后丢弃
            else:
                out.append("")
            continue
        if _is_frag_line(s):
            run.append(s)
            continue
        flush()
        out.append(s)
    flush()
    return _MANY_NL_RE.sub("\n\n", "\n".join(out))


def clean_text(text):
    """统一清洗一段正文。幂等：同一段文本清洗多次结果不变。"""
    if not text:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    s = _ETX_RE.sub("\n", s)                 # ETX 还原成它本来代表的换行
    s = _ZW_RE.sub("", s)
    s = s.replace("\xa0", " ")
    s = _ENTITY_RE.sub(_entity, s)
    s = _CTRL_RE.sub("", s)                  # 剩下的控制字符没有语义
    s = "\n".join(l.strip() for l in s.split("\n"))
    s = _MANY_NL_RE.sub("\n\n", s)
    return _merge_fragments(s).strip()


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
        v = clean_text(secs.get(k) or "")
        if not v or v in ("无", "暂无"):
            continue
        # 详情里一个区块只占一行，段内换行压成空格，避免把整块撑成十几行
        lines.append("%s：%s" % (k, " ".join(v.split("\n"))))
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


# 句末标点后面切开，保留标点本身
_SENT_RE = re.compile(r"(?<=[。！？；!?;])")
# 块尾的「小标题行」「模板块头」：短、且以冒号或逗号收尾，属于下一句的开头
_LABEL_TAIL_RE = re.compile(r"^[^。！？；\n]{1,24}[：:，,]$")


def _sentences(p):
    return [s for s in _SENT_RE.split(p) if s]


def _split_long(p, size):
    """把一个超过 size 的段落按句子边界拆成多块。

    原来的做法是「整段塞进一块 + 末尾复制 overlap 字凑第二块」：656 字的文档
    只有一段、没有换行，于是 seq0 是整篇 633 字，seq1 是从句子中间开始的 80
    字残尾（「非常不合理的，…」）。既重复又难读，检索还会把同一段返回两次。

    现在按句切：每块尽量接近 size 但一定落在句号之后；单句本身就超长（没有
    标点的长串）才硬切。
    """
    out, cur = [], ""
    for s in _sentences(p):
        while len(s) > size:            # 单句超长，先硬切走一块
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:size])
            s = s[size:]
        if cur and len(cur) + len(s) > size:
            out.append(cur)
            cur = s
        else:
            cur += s
    if cur.strip():
        out.append(cur)
    return [x for x in out if x.strip()]


def _split_md(lines, size):
    """按 markdown 标题切块，heading 保留完整层级路径。

    标题原来是 `s.lstrip("#")` 一把抓，`## 一、办卡与资料` 和它下面的
    `### 办卡需要准备什么？` 只剩最后一级。检索时模型只看到「办卡需要准备
    什么？」，不知道属于哪个章节；改成「一、办卡与资料 / 办卡需要准备什么？」。
    """
    chunks, cur = [], []
    stack = {}                     # 标题层级 -> 文本

    def heading_path():
        levels = sorted(stack)
        if not levels:
            return ""
        # 每一级都要带上。原来这里是「有二级就从二级开始拼」，理由是「一级标题
        # 通常就是整篇的名字」——但那只对「导入时已经把 # 第一行剥成标题」的
        # 外挂 md 成立。手写正文里 `# 第一节` 和 `## 方法一` 是父子关系，丢掉
        # 一级就只剩「方法一」，看不出属于哪一节。
        return " / ".join(stack[lv] for lv in levels)

    def flush():
        body = "\n".join(cur).strip()
        if body:
            chunks.append((heading_path(), body))
        cur.clear()

    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("#"):
            flush()
            level = len(s) - len(s.lstrip("#"))
            stack[level] = s.lstrip("#").strip()
            for deeper in [k for k in stack if k > level]:   # 换章节时丢掉更深的标题
                del stack[deeper]
            continue
        for piece in (_split_long(s, size) if len(s) > size else [s]):
            cur.append(piece)
            if len("\n".join(cur)) >= size:
                flush()
    flush()
    return chunks


def _split_para(text, size, overlap):
    """按段落/句子边界切分。overlap 参数保留只为兼容调用方。

    以前是「累加到 ≥size 就切，再复制末尾 overlap 个字当作下一块开头」：切点
    落在句子中间，第二块开头是上一块的残尾。现在既然每块都落在句号之后，就
    不需要字符级重叠了——重叠只会让同一段话在检索结果里出现两次。
    """
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    chunks, cur, heading = [], [], ""
    spill = []         # 被挤到下一块开头的行（块尾的小标题 / 模板块头）

    def flush():
        items = list(cur)
        # 「工信部投诉教程：/申诉内容模版：/涉及手机号：xxx，」这种块头留在上一块
        # 尾部，下一块就从半句话开始，读起来很怪。整组挪到下一块去。
        while len(items) > 1 and _LABEL_TAIL_RE.match(items[-1].strip()):
            spill.insert(0, items.pop())
        body = "\n".join(items).strip()
        if body:
            chunks.append((heading, body))
        cur.clear()

    for p in paras:
        if looks_like_heading(p):
            flush()
            heading = p
            cur.extend(spill)
            spill.clear()
            continue
        for piece in (_split_long(p, size) if len(p) > size else [p]):
            if cur and len("\n".join(cur)) + len(piece) > size:
                flush()
                cur.extend(spill)
                spill.clear()
            cur.append(piece)
    if spill:                      # 整篇就剩几行块头，别丢
        cur.extend(spill)
        spill.clear()
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
        for seq, (heading, body) in enumerate(split_kb(clean_text(d["content"] or ""))):
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


def rebuild_one(doc_id, conn=None):
    """只重建一篇文档的分块（页面上编辑保存后调用）。

    为什么不直接调 rebuild()：那个是全表重建，会清空 embeddings 却不重算向量，
    向量检索会静默失效。这里只删这一篇的 chunk + 向量，保存接口随后调
    embed.run() 增量补齐，几百篇文档改一篇不用等整表跑完。
    """
    own = conn is None
    conn = conn or database.get_conn()
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    d = conn.execute("SELECT * FROM kb_docs WHERE doc_id=?", (doc_id,)).fetchone()
    if not d:
        if own:
            conn.close()
        return {"ok": False, "reason": "文档不存在"}

    olds = [r[0] for r in conn.execute(
        "SELECT chunk_id FROM kb_chunks WHERE source='kb' AND doc_id=?", (doc_id,))]
    for cid in olds:
        conn.execute("DELETE FROM kb_fts WHERE chunk_id=?", (cid,))
        conn.execute("DELETE FROM embeddings WHERE chunk_id=?", (cid,))
    conn.execute("DELETE FROM kb_chunks WHERE source='kb' AND doc_id=?", (doc_id,))

    # 新行号接在全表现有最大值后面：商品分块占了几个固定区段（PRODUCT_ROWID_BASE 等），
    # 直接复用序号会撞。
    rowid = conn.execute("SELECT IFNULL(max(rowid),0) FROM kb_fts").fetchone()[0] + 1
    aud = d["audience"] or "agent"
    n = 0
    dropped = 0
    for seq, (heading, body) in enumerate(split_kb(clean_text(d["content"] or ""))):
        cid = "kb:%s:%d" % (doc_id, seq)
        txt = "%s\n%s" % (heading, body) if heading else body
        if aud != "agent":
            txt, dr = sanitize_shared(txt)
            dropped += dr
            if len(txt.strip()) < 30:
                continue
        conn.execute(
            "INSERT INTO kb_chunks(chunk_id, source, doc_id, audience, title, heading, seq, text, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, "kb", doc_id, aud, d["title"], heading, seq, txt, ts))
        conn.execute("INSERT INTO kb_fts(rowid, chunk_id, title, text) VALUES (?,?,?,?)",
                     (rowid, cid, "%s %s" % (d["title"] or "", heading), txt))
        rowid += 1
        n += 1
    conn.commit()
    if own:
        conn.close()
    return {"ok": True, "doc_id": doc_id, "chunks": n, "before": len(olds), "dropped": dropped}


def clean_existing(conn=None, dry_run=False):
    """就地清洗已有 chunk 的正文，不动 embeddings。

    与 rebuild 的区别：rebuild 会清空整张表并重建，embeddings 表也跟着清掉、
    而重建后不会自动重算向量，向量检索会静默失效。清洗只是把一个字段的
    脏字符换掉，向量本身照旧可用，所以单独走这条路。
    """
    own = conn is None
    conn = conn or database.get_conn()
    rows = conn.execute("SELECT chunk_id, text FROM kb_chunks").fetchall()
    changed, saved = [], 0
    for r in rows:
        old = r["text"] or ""
        new = clean_text(old)
        if new == old:
            continue
        changed.append({"chunk_id": r["chunk_id"],
                        "before": len(old), "after": len(new)})
        if dry_run:
            continue
        conn.execute("UPDATE kb_chunks SET text=? WHERE chunk_id=?", (new, r["chunk_id"]))
        # FTS 里存的也是同一段正文，两份必须一起改，否则检索命中的
        # 还是旧文本，页面上看是干净的、搜出来却是脏的
        try:
            conn.execute("UPDATE kb_fts SET text=? WHERE chunk_id=?", (new, r["chunk_id"]))
        except Exception:
            saved += 1  # 计数只为排查，FTS 更新失败不影响正文
    if not dry_run:
        conn.commit()
    if own:
        conn.close()
    return {"total": len(rows), "changed": len(changed),
            "fts_update_failed": saved, "sample": changed[:10]}
