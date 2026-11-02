"""向量化：把 kb_chunks 转成向量存进 embeddings 表。

后端是「OpenAI 兼容」的 /embeddings 接口，硅基流动/阿里百炼/智谱/Ollama 都能用。
没有 numpy：几百个块纯 Python 算余弦足够，上万条再换。
"""
import datetime as dt
import json
import math
import struct
import urllib.request
import urllib.error
from .. import config
from . import common


def enabled():
    e = config.embed_cfg()
    return bool(e.get("api_key")) and bool(e.get("base_url"))


def _post(url, payload, api_key, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
        method="POST")
    with common.urlopen_direct(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return json.loads(raw.decode())


def embed_texts(texts):
    e = config.embed_cfg()
    if not enabled():
        raise RuntimeError("embedding 未配置 api_key / base_url")
    base = e["base_url"].rstrip("/")
    url = base + "/embeddings"
    model = e.get("model", "BAAI/bge-m3")
    batch = int(e.get("batch", 16))
    out = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        res = _post(url, {"model": model, "input": chunk, "encoding_format": "float"}, e["api_key"])
        items = sorted(res["data"], key=lambda d: d.get("index", 0))
        out.extend([it["embedding"] for it in items])
    return out


def pack(vec):
    return struct.pack("<%df" % len(vec), *vec)


def unpack(blob):
    return list(struct.unpack("<%df" % (len(blob) // 4), blob))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def run(rebuild=False, check=False, conn=None):
    from .. import database
    own = conn is None
    conn = conn or database.get_conn()
    e = config.embed_cfg()
    model = e.get("model", "BAAI/bge-m3")
    try:
        if check:
            v = embed_texts(["广电飞花卡 29元192G"])[0]
            return {"ok": True, "model": model, "dim": len(v)}
        if rebuild:
            conn.execute("DELETE FROM embeddings")
            conn.commit()
        have = {r[0] for r in conn.execute("SELECT chunk_id FROM embeddings")}
        todo = [(r["chunk_id"], r["source"], r["text"])
                for r in conn.execute("SELECT chunk_id, source, text FROM kb_chunks")
                if r["chunk_id"] not in have]
        if not todo:
            return {"done": len(have), "new": 0}
        vecs = embed_texts([t[2] for t in todo])
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for (cid, source, _), v in zip(todo, vecs):
            conn.execute(
                "INSERT OR REPLACE INTO embeddings(chunk_id, source, model, dim, vec, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (cid, source, model, len(v), pack(v), ts))
        conn.commit()
        return {"done": len(have), "new": len(todo)}
    finally:
        if own:
            conn.close()
