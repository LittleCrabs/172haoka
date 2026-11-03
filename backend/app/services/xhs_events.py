"""小红书机器人日志契约（事件名 / 文件路径 / 中文标签）。

为什么要单独一个模块：这些字符串是 **xhs_bot.py（写）** 和 **services/xhs.py（读统计）**
之间的隐式接口。以前两边各写各的字面量，一边改名另一边不知道，页面统计就会静默变成 0
而不报任何错。现在两边都从这里取，改名只需要改这一个文件。

依赖约束：本模块只能依赖标准库 —— bot 是独立脚本，import 它时不能连带拉起
FastAPI / 数据库连接。
"""
import json
from datetime import datetime
from pathlib import Path

# 项目根目录（haoka/）：backend/app/services/xhs_events.py → 上三级
PROJECT_DIR = Path(__file__).resolve().parents[3]

# 机器人结构化日志（JSONL，每行一个事件）与最近一轮的原始输出
LOG_PATH = PROJECT_DIR / "xhs_bot_log.jsonl"
LAST_RUN_LOG = PROJECT_DIR / "xhs_bot_lastrun.log"

# ---- 事件名（写日志用这些常量，不要写字面量） ----
START = "start"                    # 一轮开始：mode / limit / max_scan / refresh_every
DONE = "done"                      # 一轮结束：processed / scanned
SCANNED = "scanned"                # 浏览到一条帖子
HIT = "hit"                        # 判定为目标人群且有回复
SENT = "sent"                      # 评论已发出

SKIP_NO_CONTENT = "skip_no_content"
SKIP_BLACKLIST = "skip_blacklist"
SKIP_REPLIED = "skip_replied"      # 本地日志里今天已发过
SKIP_CACHED = "skip_cached"        # 后端判过/生成过（去重命中）
NOT_TARGET = "not_target"          # 规则判定非目标人群
NO_REPLY = "no_reply"              # 判为目标人群但没生成出内容

OPEN_FAILED = "open_failed"
EXTRACT_FAILED = "extract_failed"
API_ERROR = "api_error"
SEND_FAILED = "send_failed"
SEND_UNVERIFIED = "send_unverified"

FEED_REFRESH = "feed_refresh"      # 换一批推荐
SCROLL_STALL = "scroll_stall"      # 滑不动
SEND_WAIT = "send_wait"            # 两条评论之间的静默等待（发一条后 1.5-4 分钟）
PAGE_RECOVER = "page_recover"      # 页面跑偏（被手动返回/跳走）已复位到信息流
PAGE_LOST = "page_lost"            # 浏览器窗口被关掉或页面已失效
WINDOW_HIDDEN = "window_hidden"    # 已把浏览器窗口从任务栏隐藏
WINDOW_HIDE_FAILED = "window_hide_failed"  # 隐藏失败（找不到窗口句柄，保持可见）
CHROME_STALE = "chrome_stale"      # 上一轮残留的 Chrome 占着 profile，已清掉重试
STOP_TIMEOUT = "stop_timeout"
STOP_NO_MORE_CONTENT = "stop_no_more_content"
STOP_DAILY_LIMIT = "stop_daily_limit"
INTERRUPTED = "interrupted"
FATAL = "fatal"

ALL_EVENTS = (
    START, DONE, SCANNED, HIT, SENT,
    SKIP_NO_CONTENT, SKIP_BLACKLIST, SKIP_REPLIED, SKIP_CACHED, NOT_TARGET, NO_REPLY,
    OPEN_FAILED, EXTRACT_FAILED, API_ERROR, SEND_FAILED, SEND_UNVERIFIED,
    FEED_REFRESH, SCROLL_STALL, STOP_TIMEOUT, STOP_NO_MORE_CONTENT, STOP_DAILY_LIMIT,
    INTERRUPTED, FATAL,
    SEND_WAIT, PAGE_RECOVER, PAGE_LOST,
    WINDOW_HIDDEN, WINDOW_HIDE_FAILED, CHROME_STALE,
)

# 计入「跳过原因」统计的事件 → 页面显示的中文说明
SKIP_LABELS = {
    NOT_TARGET: "非目标人群",
    SKIP_BLACKLIST: "命中黑名单",
    SKIP_NO_CONTENT: "正文为空",
    SKIP_REPLIED: "本地已回复",
    SKIP_CACHED: "后端判过已回复",
    OPEN_FAILED: "打开详情失败",
    SEND_FAILED: "发送失败",
    SEND_UNVERIFIED: "发送未复核到",
    "skip_low_or_cached": "分数不足/已缓存（旧版遗留，仅用于读历史日志）",
}


def write_event(event, **kw):
    """追加一条 JSONL 事件，返回写入的记录（供调用方顺手打印）。"""
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **kw}
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_events(limit=None):
    """读取全部事件（旧→新）；坏行跳过，不让一行脏数据毁掉统计。"""
    if not LOG_PATH.exists():
        return []
    out = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out[-limit:] if limit else out
