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


def find_file(doc_id):
    """按 doc_id 在 kb_extra 里找源文件。

    不信任 kb_docs.url：项目目录搬过家，库里存的还是旧路径
    （D:/workarea/WorkBuddy/2026-11-01.../kb_extra/xxx.md），照着它写会写到
    一个不存在的目录里去。文件名才是可靠标识，约定里本来也这么定。
    """
    if not doc_id.startswith("md-"):
        return None
    name = doc_id[3:]
    for ext in EXTS:
        p = DEFAULT_DIR / (name + ext)
        if p.exists():
            return p
    return None


def write_back(doc_id, title, audience, content):
    """把页面上的修改写回外挂源文件。

    写回时要重建文件头（audience 标记 + # 标题）：parse_audience 和标题提取
    都在导入时把这些头部剥掉了，只把 content 写回去，下次导入受众就退回默认
    agent、标题退化成文件名。
    """
    path = find_file(doc_id)
    if not path:
        return {"written": False, "reason": "源文件不存在" if doc_id.startswith("md-") else "非外挂文档"}
    head = ""
    if audience and audience != "agent":
        head += "audience: %s\n\n" % audience
    if title:
        head += "# %s\n\n" % title
    try:
        path.write_text(head + content.strip() + "\n", encoding="utf-8")
    except OSError as e:
        return {"written": False, "reason": "写入失败：%s" % e}
    return {"written": True, "path": str(path).replace("\\", "/")}


def ingest_md(directory=None, conn=None):
    d = directory or str(DEFAULT_DIR)
    os.makedirs(d, exist_ok=True)
    files = [f for f in sorted(os.listdir(d)) if f.lower().endswith(EXTS)]
    own = conn is None
    conn = conn or database.get_conn()
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    imported = []
    skipped = []
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
            # 页面上改过的文档，库里的时间戳比文件新——这时候导入会把人的修改
            # 覆盖回去。跳过并报出来，让人自己决定是改文件还是删库里的版本。
            prev = conn.execute("SELECT fetched_at FROM kb_docs WHERE doc_id=?", (doc_id,)).fetchone()
            if prev and prev[0]:
                try:
                    db_ts = dt.datetime.strptime(prev[0], "%Y-%m-%d %H:%M:%S").timestamp()
                    if db_ts > os.path.getmtime(path) + 1:
                        skipped.append({"doc_id": doc_id, "title": title,
                                        "reason": "库里的版本更新（页面改过），未覆盖"})
                        continue
                except ValueError:
                    pass
            conn.execute(
                "INSERT INTO kb_docs(doc_id, title, url, category, audience, content, content_hash, fetched_at)"
                " VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title, audience=excluded.audience,"
                " content=excluded.content, content_hash=excluded.content_hash, fetched_at=excluded.fetched_at",
                (doc_id, title, "file://" + path.replace("\\", "/"), "外挂", aud,
                 body, hashlib.md5(body.encode()).hexdigest(), ts))
            n += 1
            imported.append({"doc_id": doc_id, "title": title, "audience": aud})
        # get_conn() 是默认事务模式，不 commit 就 close 等于整批回滚。
        # 以前这里只 close，接口照样返回 imported=N，库里却一条没进。
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()
    return {"imported": n, "files": imported, "skipped": skipped}
