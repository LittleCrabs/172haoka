"""小红书引流回复接口：POST /api/xhs/reply，GET /api/xhs/history。"""
from fastapi import APIRouter, HTTPException, Query

from ..services import xhs as xhs_svc
from .. import database

router = APIRouter(prefix="/api", tags=["xhs"])


@router.post("/xhs/reply")
def xhs_reply(body: dict):
    """
    入参（JSON）：
      post_content (必填): 小红书帖子正文（通常已含 IP 属地，如「IP属地：江苏」）
      region       (可选): 显式地区/省份，优先于从正文抽取
      ip           (可选): IP 地址，仅作兜底解析地区（失败不影响）
      audience     (可选): 目标人群描述，作为生成参考
      dry_run      (可选): true 时只返回组装好的 prompt，不调大模型
      post_id      (可选): 小红书帖子 ID，用于去重（不传则按正文哈希兜底）
      force        (可选): true 时忽略去重缓存，强制重新生成

    返回：{ reply, region, should_reply, score, reason, signals, region_available,
            already_replied, error, [prompt], [candidates] }
      - should_reply: 是否命中目标人群（规则预筛，非目标人群时 reply 为空、不调大模型）
      - score: 目标人群匹配强度（各类信号加权，供设阈值 / 排序优先级）
      - reason: 判定理由
      - signals: 命中的目标人群信号类别与关键词
      - region_available: 该地区在售且非禁发的卡数（地区未知时为 null）
      - already_replied: 是否命中去重缓存（true=复用历史回复、未调大模型）
    """
    post_content = body.get("post_content") or body.get("content") or ""
    if not post_content.strip():
        raise HTTPException(status_code=400, detail="post_content 不能为空")
    try:
        return xhs_svc.reply(
            post_content,
            ip=body.get("ip"),
            region=body.get("region"),
            audience=body.get("audience"),
            dry_run=bool(body.get("dry_run")),
            post_id=body.get("post_id"),
            force=bool(body.get("force")),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/xhs/history")
def xhs_history(limit: int = Query(50, ge=1, le=500)):
    """已回复 / 已判定记录（去重表），按时间倒序。"""
    conn = database.get_conn()
    try:
        rows = conn.execute(
            "SELECT post_id, region, should_reply, score, reply_text, replied_at "
            "FROM xhs_replies ORDER BY replied_at DESC LIMIT ?", (limit,)).fetchall()
        return {"total": len(rows), "items": [dict(r) for r in rows]}
    finally:
        conn.close()

