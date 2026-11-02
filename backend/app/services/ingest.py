"""外挂知识库：把本地 md / txt 文件导入 kb_docs（对客话术、补充资料都走这里）。

约定：
  · 文件名（不含扩展名）= doc_id，重复导入覆盖
  · 第一行 # 标题 用作标题，否则用文件名
  · 顶部可写 `audience: customer` 指定受众，不写默认 agent
"""
import datetime as dt
import hashlib
import os
import re
from .. import database

PROJECT_DIR = database.PROJECT_DIR
DEFAULT_DIR = PROJECT_DIR / "kb_extra"
EXTS = (".md", ".markdown", ".txt")
VALID_AUDIENCE = ("agent", "customer", "shared")


def parse_audience(body):
    m = re.search(r"^\s*audience\s*[:：]\s*(\w+)", body, re.I | re.M)
    if m and m.group(1).lower() in VALID_AUDIENCE:
        aud = m.group(1).lower()
        body = re.sub(r"^\s*audience\s*[:：].*\n?", "", body, count=1, flags=re.I | re.M)
        return aud, body.strip()
    return "agent", body


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError("无法解码 %s" % path)


def ingest_md(directory=None, conn=None):
    d = directory or str(DEFAULT_DIR)
    os.makedirs(d, exist_ok=True)
    files = [f for f in sorted(os.listdir(d)) if f.lower().endswith(EXTS)]
    own = conn is None
    conn = conn or database.get_conn()
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    imported = []
    try:
        for f in files:
            path = os.path.join(d, f)
            body = read_text(path).strip()
            if len(body) < 20:
                continue
            doc_id = "md-" + os.path.splitext(f)[0]
            title = os.path.splitext(f)[0]
            aud, body = parse_audience(body)
            first = body.split("\n", 1)[0].strip()
            if first.startswith("#"):
                title = first.lstrip("#").strip() or title
                body = body.split("\n", 1)[1].strip() if "\n" in body else body
            conn.execute(
                "INSERT INTO kb_docs(doc_id, title, url, category, audience, content, content_hash, fetched_at)"
                " VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title, audience=excluded.audience,"
                " content=excluded.content, content_hash=excluded.content_hash, fetched_at=excluded.fetched_at",
                (doc_id, title, "file://" + path.replace("\\", "/"), "外挂", aud,
                 body, hashlib.md5(body.encode()).hexdigest(), ts))
            n += 1
            imported.append({"doc_id": doc_id, "title": title, "audience": aud})
    finally:
        if own:
            conn.close()
    return {"imported": n, "files": imported}
