"""知识库 API：文档列表、文本块检索/浏览、外挂导入、重建分块。"""
from fastapi import APIRouter
from .. import database
from ..services import chunks, ingest, retrieve

router = APIRouter(prefix="/api/kb", tags=["kb"])


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


@router.post("/ingest")
def ingest_md():
    return {"ok": True, **ingest.ingest_md()}


@router.post("/rebuild")
def rebuild():
    return {"ok": True, **chunks.rebuild()}
