"""知识库 API：文档列表、正文读写、文本块检索/浏览、外挂导入、重建分块。"""
import datetime as dt
import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import database
from ..services import chunks, embed, ingest, retrieve

router = APIRouter(prefix="/api/kb", tags=["kb"])

VALID_AUDIENCE = ("agent", "customer", "shared")


@router.get("/docs")
def list_docs():
    conn = database.get_conn()
    try:
        rows = conn.execute(
            "SELECT doc_id,title,audience,category,fetched_at FROM kb_docs ORDER BY doc_id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/chunks")
def browse_chunks(q: str = "", limit: int = 60):
    """无 q 时浏览全部；有 q 时按二元组检索。"""
    conn = database.get_conn()
    try:
        if q:
            hits = retrieve.text_search(q, k=limit)
            return [{"chunk_id": h[1]["chunk_id"], "doc_id": h[1]["doc_id"],
                    "title": h[1]["title"], "heading": h[1]["heading"],
                    "text": h[1]["text"], "score": round(h[0], 4)} for h in hits]
        rows = conn.execute(
            "SELECT chunk_id,doc_id,source,audience,title,heading,text FROM kb_chunks "
            "ORDER BY rowid LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------- 单篇文档的正文读写 ----------------
# 页面上看到的分块是派生产物，改分块没意义（下次重建就没了）。真要修内容
# 得改 kb_docs.content，再让这条文档重新分块、补向量。

DOC_FIELDS = ("doc_id", "title", "audience", "category", "fetched_at", "content")


class DocIn(BaseModel):
    content: str | None = None
    title: str | None = None
    audience: str | None = None


class TextIn(BaseModel):
    text: str


@router.post("/clean-text")
def clean_text_api(body: TextIn):
    """只清洗、不保存：编辑框里先看一眼再决定要不要用。

    复用后端同一份 clean_text，避免前端再实现一套规则导致两边判断不一致。
    """
    old = body.text or ""
    new = chunks.clean_text(old)
    return {"ok": True, "text": new, "before": len(old), "after": len(new),
            "changed": new != old}


@router.get("/doc/{doc_id}")
def get_doc(doc_id: str):
    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT %s FROM kb_docs WHERE doc_id=?" % ",".join(DOC_FIELDS), (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "文档不存在")
        d = dict(row)
        d["chars"] = len(d.get("content") or "")
        d["chunk_count"] = conn.execute(
            "SELECT count(*) FROM kb_chunks WHERE source='kb' AND doc_id=?", (doc_id,)
        ).fetchone()[0]
        src = ingest.find_file(doc_id)
        d["source_file"] = str(src).replace("\\", "/") if src else None
        return d
    finally:
        conn.close()


@router.post("/doc/{doc_id}/rebuild")
def rebuild_doc(doc_id: str):
    """只重切这一篇，不改内容。

    分块规则或清洗规则改过之后，不必去动「全量重建」把 1292 条向量一起重算；
    改一篇只影响一篇的向量。
    """
    conn = database.get_conn()
    try:
        if not conn.execute("SELECT 1 FROM kb_docs WHERE doc_id=?", (doc_id,)).fetchone():
            raise HTTPException(404, "文档不存在")
        res = chunks.rebuild_one(doc_id, conn=conn)
        return {"ok": True, **res, "embed": _run_embed()}
    finally:
        conn.close()


@router.put("/doc/{doc_id}")
def save_doc(doc_id: str, body: DocIn):
    """保存正文 → 只重建这一篇的分块 → 增量补向量。

    走 rebuild_one 而不是 rebuild：全量重建会清空 embeddings 且不重算，
    向量检索会静默失效；这里只动本篇，改一篇不牵连其余 100 多段。
    """
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM kb_docs WHERE doc_id=?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "文档不存在")

        sets, args = [], []
        title = (body.title or "").strip() or row["title"]
        aud = body.audience if body.audience in VALID_AUDIENCE else (row["audience"] or "agent")
        if body.content is not None:
            txt = body.content.replace("\r\n", "\n")
            sets.append("content=?")
            args.append(txt)
            # content_hash 是导入时用来判断「内容有没有变」的，改了正文必须同步，
            # 否则下次「导入外挂」会认为没变、把用户的修改原样覆盖回去
            sets.append("content_hash=?")
            args.append(hashlib.md5(txt.encode("utf-8")).hexdigest())
            sets.append("fetched_at=?")
            args.append(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if body.title is not None and body.title.strip():
            sets.append("title=?")
            args.append(title)
        if body.audience is not None and body.audience in VALID_AUDIENCE:
            sets.append("audience=?")
            args.append(aud)
        if not sets:
            raise HTTPException(400, "没有要保存的字段")

        # 外挂 md/txt：页面上改完直接落回源文件，否则下次「导入外挂」文件还是旧的。
        # 写不进去（文件被移走/只读）也不阻断保存，如实回传原因由界面提示。
        file_info = {}
        if body.content is not None and doc_id.startswith("md-"):
            file_info = ingest.write_back(doc_id, title, aud, txt)
            if file_info.get("written"):
                sets.append("url=?")
                args.append("file://" + file_info["path"])

        conn.execute("UPDATE kb_docs SET %s WHERE doc_id=?" % ",".join(sets), (*args, doc_id))
        conn.commit()

        res = chunks.rebuild_one(doc_id, conn=conn)
        embed_res = _run_embed() if body.content is not None else {}
        return {"ok": True, **res, "embed": embed_res, "file": file_info}
    finally:
        conn.close()


@router.post("/ingest")
def ingest_md():
    return {"ok": True, **ingest.ingest_md()}


@router.post("/rebuild")
def rebuild():
    """全量重切分块，并**紧接着补算向量**。

    chunks.rebuild() 会 DELETE FROM embeddings；以前调完这里就结束了，
    向量表空着没人管，语义检索从此静默失效（关键词检索照常，所以很难发现）。
    与其在文档里写「记得再去向量化一次」，不如在这里一次做完。
    """
    res = chunks.rebuild()
    return {"ok": True, **res, "embed": _run_embed()}


@router.post("/embed")
def embed_all():
    """补算向量：只算 embeddings 表里还没有的分块，已经算过的直接跳过。"""
    if not embed.enabled():
        raise HTTPException(400, "未配置向量模型（设置 → 模型服务 → 向量模型）")
    return {"ok": True, **_run_embed()}


def _run_embed():
    if not embed.enabled():
        return {"skipped": "未配置向量模型"}
    try:
        return embed.run()
    except Exception as e:      # 向量服务挂了不该让重建/清洗整体失败
        return {"error": str(e)[:300]}


@router.post("/clean")
def clean_chunks(dry_run: bool = False):
    """清洗已有正文（控制字符 / HTML 实体 / OCR 碎片行），不动向量。

    历史数据是一次性刷的，页面上的「整理正文」按钮也走这里；dry_run
    只统计会被改动的条数，用来先看一眼影响面。
    """
    return {"ok": True, **chunks.clean_existing(dry_run=dry_run)}
