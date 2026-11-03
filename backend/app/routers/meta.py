"""运行状态与全局检索：登录有效期、上次同步结果、跨模块搜索。

这三个接口都只读，前端用它们填空：设置页「登录状态」卡、同步页状态带、
topbar 的 Ctrl+K 搜索。
"""
import datetime as dt
import json

from fastapi import APIRouter

from .. import database
from ..services import common

router = APIRouter(prefix="/api", tags=["meta"])

# 复用 common 的路径，别自己拼 parent：token.json 在项目根，不在 backend/
TOKEN_FILE = common.TOKEN_FILE
TOKEN_TTL_DAYS = 7  # 后台登录 token 的有效期，与设置页说明保持一致


def _ts(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


@router.get("/login-status")
def login_status():
    """后台登录状态：有没有 token、属于谁、什么时候过期。

    以前这张卡片叫「登录状态」却只有获取验证码表单，用户根本看不出
    自己是登着的还是掉了，同步失败时只能去翻日志。
    """
    if not TOKEN_FILE.exists():
        return {"logged_in": False, "reason": "还没有登录过"}

    try:
        d = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"logged_in": False, "reason": "token 文件损坏，需要重新登录"}

    token = (d.get("token") or "").strip()
    if not token:
        return {"logged_in": False, "reason": "token 为空，需要重新登录"}

    # token 接口不给过期时间，用文件落盘时间 + 7 天倒推（登录成功时才写这个文件）
    login_at = dt.datetime.fromtimestamp(TOKEN_FILE.stat().st_mtime)
    expire_at = login_at + dt.timedelta(days=TOKEN_TTL_DAYS)
    left = (expire_at - dt.datetime.now()).days

    u = d.get("user") or {}
    return {
        "logged_in": True,
        "username": u.get("userName") or "",
        "role": u.get("roleName") or "",
        "agent_id": u.get("agentID"),
        "login_at": login_at.strftime("%Y-%m-%d %H:%M"),
        "expire_at": expire_at.strftime("%Y-%m-%d"),
        "days_left": left,
        "expiring": left <= 2,  # 快过期时前端标黄
    }


@router.get("/sync-status")
def sync_status(limit: int = 6):
    """上次同步结果 + 最近几条同步记录（两个通道合并按时间排）。"""
    conn = database.get_conn()
    try:
        cols = "id, kind, started_at, finished_at, total, inserted, updated, unchanged, offsale, status, message"
        rows = conn.execute(
            "SELECT %s FROM crawl_log ORDER BY started_at DESC, id DESC LIMIT ?" % cols, (limit,)
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            st, ed = _ts(d.get("started_at")), _ts(d.get("finished_at"))
            d["duration"] = round((ed - st).total_seconds(), 1) if (st and ed) else None
            d["kind"] = d.get("kind") or "手机卡"
            items.append(d)

        last_ok = {}
        for it in items:
            if it["status"] == "ok" and it["kind"] not in last_ok:
                last_ok[it["kind"]] = it

        running = next((it for it in items if it["status"] == "running"), None)
        return {"items": items, "last": items[0] if items else None,
                "last_ok": last_ok, "running": running}
    finally:
        conn.close()


@router.get("/search")
def search(q: str = "", limit: int = 6):
    """全局搜索：商品名 / 地区 / 关键词，加知识库文档与片段。

    958 个商品只能进页面再筛，跨模块找东西全靠翻侧栏——这里给一个统一入口。
    """
    kw = (q or "").strip()
    if not kw:
        return {"products": [], "kb": [], "total": 0}

    like = "%" + kw + "%"
    conn = database.get_conn()
    try:
        prods = conn.execute(
            "SELECT product_id, product_name, operator, category, area, on_sale, "
            "commission_read, monthly_fee FROM products "
            "WHERE product_name LIKE ? OR keywords LIKE ? OR area LIKE ? OR operator LIKE ? "
            "ORDER BY (product_name = ?) DESC, on_sale DESC, length(product_name) LIMIT ?",
            (like, like, like, like, kw, limit)).fetchall()

        docs = conn.execute(
            "SELECT doc_id, title, audience FROM kb_docs WHERE title LIKE ? OR content LIKE ? "
            "ORDER BY (title LIKE ?) DESC LIMIT ?",
            (like, like, like, max(2, limit // 2))).fetchall()

        # 只搜知识库自己的分块。kb_chunks 里还躺着每个商品的详情页正文（source='product'），
        # 不过滤的话「知识库」分组会被「商品名称：xxx」的片段灌满，文档反而找不到。
        # 已经整篇命中的文档，不再把它的片段重复列一遍。
        chunks = conn.execute(
            "SELECT chunk_id, doc_id, title, substr(text, 1, 80) AS snippet FROM kb_chunks "
            "WHERE text LIKE ? AND source = 'kb' "
            "AND doc_id NOT IN (SELECT doc_id FROM kb_docs WHERE title LIKE ? OR content LIKE ?) "
            "LIMIT ?", (like, like, like, max(2, limit // 2))).fetchall()

        total = conn.execute(
            "SELECT count(*) FROM products WHERE product_name LIKE ? OR keywords LIKE ?",
            (like, like)).fetchone()[0]

        return {
            "products": [dict(r) for r in prods],
            "kb": [{**dict(r), "kind": "doc"} for r in docs]
            + [{**dict(r), "kind": "chunk"} for r in chunks],
            "total": total,
        }
    finally:
        conn.close()
