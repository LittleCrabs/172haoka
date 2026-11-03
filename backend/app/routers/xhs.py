"""小红书引流：判定/生成接口、运行统计、试算、启动一轮机器人。

本文件只做「解析请求 → 调 service → 返回结果」。
机器人子进程的启动与状态查询在 services/bot_runner.py（参数上下限、单实例互斥都在那边）。
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..services import bot_runner, xhs as xhs_svc
from .. import config, database

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
    """已回复 / 已判定记录（去重表），按时间倒序。

    额外带出这条回复「实际推的是哪张卡」：product_name / order_url（客户下单版）
    / product_fee / product_data / product_operator。回复正文本身不点名、不带链接，
    这些字段只给代理跟进用。
    """
    conn = database.get_conn()
    try:
        rows = conn.execute(
            "SELECT post_id, region, should_reply, score, tone, reply_text, replied_at, "
            "       delivered_at, product_id, product_name, order_url, "
            "       product_fee, product_data, product_operator "
            "FROM xhs_replies ORDER BY replied_at DESC LIMIT ?", (limit,)).fetchall()
        return {"total": len(rows), "items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/xhs/mark-sent")
def xhs_mark_sent(body: dict):
    """机器人真正发完评论后回调，回填 delivered_at。

    replied_at 是「后端生成了回复」的时间（dry 试跑也有），
    delivered_at 才是「评论真的到小红书上了」。页面上两者必须分开显示。
    """
    post_id = (body.get("post_id") or "").strip()
    if not post_id:
        raise HTTPException(status_code=400, detail="post_id 不能为空")
    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE xhs_replies SET delivered_at=? WHERE post_id=? AND delivered_at IS NULL",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), post_id))
        conn.commit()
        return {"ok": True, "updated": cur.rowcount}
    finally:
        conn.close()


@router.post("/xhs/assess")
def xhs_assess(body: dict):
    """只做规则判定（目标人群得分 / 命中信号 / 地区可办卡数），不调大模型、不落库。"""
    post_content = body.get("post_content") or ""
    if not post_content.strip():
        raise HTTPException(status_code=400, detail="post_content 不能为空")
    try:
        return xhs_svc.assess_detail(post_content, region=body.get("region"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/xhs/stats")
def xhs_stats(days: int = Query(7, ge=1, le=30)):
    """运行统计：扫描/命中/发送量、分数与地区分布、跳过原因、每日趋势、最近事件。"""
    return xhs_svc.stats(days=days)


@router.get("/xhs/config")
def xhs_config():
    """当前生效的判分配置（阈值 / 六类权重 / 人格），供页面显示规则与试算说明。

    额外带上 factory_tones：设置页每个「人格」卡片上的「恢复默认」需要原文，
    否则用户改坏了只能去翻代码。
    """
    cfg = dict(config.xhs_cfg())
    cfg["factory_tones"] = dict(config.XHS_DEFAULTS.get("tones") or {})
    return cfg


@router.post("/xhs/run")
def xhs_run(body: dict):
    """启动一轮机器人（会弹出一个专用 Chrome 窗口）。同一时间只允许一轮。"""
    try:
        return bot_runner.start(body)
    except bot_runner.AlreadyRunning as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="启动失败：%s" % e)


@router.get("/xhs/run/status")
def xhs_run_status():
    """是否在跑 / pid / 退出码 / 本轮参数 / 日志尾巴。"""
    return bot_runner.status()
