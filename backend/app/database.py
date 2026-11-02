import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent  # haoka/
DB_PATH = PROJECT_DIR / "data" / "haoka.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# 老库升级：CREATE TABLE IF NOT EXISTS 不会给已存在的表加列，这里补齐
NEEDED_COLUMNS = {
    "kb_docs": [("audience", "TEXT DEFAULT 'agent'")],
    "kb_chunks": [("audience", "TEXT DEFAULT 'agent'")],
    "products": [("category", "TEXT"), ("detail_url", "TEXT"), ("create_time", "TEXT"), ("exclusive_url", "TEXT")],
    "product_changes": [("batch_id", "TEXT")],
    "xhs_replies": [("tone", "TEXT")],
}


def _ensure_columns(conn):
    for table, cols in NEEDED_COLUMNS.items():
        have = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        for name, ddl in cols:
            if name not in have:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, ddl))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_audience ON kb_chunks(audience)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_changes_batch ON product_changes(batch_id)")


def get_meta(conn, key, default=None):
    r = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return r["v"] if r else default


def set_meta(conn, key, value):
    import datetime as _dt
    conn.execute("INSERT INTO meta(k, v, updated_at) VALUES (?,?,?) "
                 "ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
                 (key, value, _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _ensure_columns(conn)
    conn.commit()
    conn.close()
