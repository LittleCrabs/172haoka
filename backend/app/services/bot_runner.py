"""小红书机器人进程管理：启动 / 查状态 / 单实例互斥。

为什么单独一个模块：这套逻辑原来长在 routers/xhs.py 里，HTTP 层同时负责
「解析请求」「把参数翻译成命令行」「管子进程」，三件事混在一起。搬出来后：
- 参数上下限只定义一处（PARAM_LIMITS），页面、CLI、将来的定时任务共用同一套规则；
- 任何入口都能直接 `bot_runner.start(...)` 跑一轮，不必绕 HTTP。

状态存两层，各管一件事：
1. 内存 `_RUN`：持有 Popen 句柄 —— 只有它能拿到**退出码**，但活不过后端重启；
2. 数据库 `bot_runs`：唯一可信的「这一轮在不在跑」。启动时插一行 state='running'，
   结束时回填 returncode / finished_at；判断存活靠 pid + **进程创建时间**
   （Windows 用 GetProcessTimes 比对，防 PID 被系统复用后误判成"还在跑"）。

可靠性边界：
- 后端重启后仍能知道上一轮是否在跑（pid 活着且创建时间对得上 → 继续拦重复启动）；
- 后端崩溃留下 state='running' 的死行，下次 status/start 会验活并自动收敛成
  done/failed/stale（依据日志里的 done / fatal 事件推断），不会永久卡住；
- 多 worker / 多次误点：靠数据库唯一索引 `uniq_bot_run_running` 兜底，
  并发情况下第二个 INSERT 会失败，转成 AlreadyRunning。
"""
import json
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from .. import database
from . import xhs_events
from .xhs_events import (LAST_RUN_LOG, DONE, FATAL, INTERRUPTED,
                         STOP_TIMEOUT, STOP_NO_MORE_CONTENT, STOP_DAILY_LIMIT)

PROJECT_DIR = Path(__file__).resolve().parents[3]   # haoka/
SCRIPT = "xhs_bot.py"
PLATFORM = "xhs"

# 参数上下限：改这里就能同时约束接口、页面与将来的调度器。
PARAM_LIMITS = {
    "limit": (1, 50, 5),           # 每轮最多发几条评论
    "max_scan": (1, 300, 20),      # 最多翻多少帖
    "max_minutes": (1, 60, 10),    # 单轮最长分钟数
    "refresh_every": (3, 60, 10),  # 每浏览多少帖换一批推荐
}

# 视为「正常收尾」的事件（非崩溃）
_GRACEFUL = (DONE, STOP_TIMEOUT, STOP_NO_MORE_CONTENT, STOP_DAILY_LIMIT, INTERRUPTED)

# 当前进程句柄（只在存活的这次后端进程内有效，用来拿退出码）
_LOCK = threading.Lock()
_RUN = {"proc": None, "run_id": None}


class AlreadyRunning(Exception):
    """已有一轮在跑。路由层据此返回 409。"""


# ==================== 参数 ====================

def _clamp(name, value):
    lo, hi, default = PARAM_LIMITS[name]
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(v, hi))


def normalize(params=None):
    """把外部参数（字符串 / None / 脏值）规整成合法值，顺带丢弃未知字段。"""
    p = params or {}
    out = {k: _clamp(k, p.get(k)) for k in PARAM_LIMITS}
    out["dry"] = bool(p.get("dry"))
    # 默认隐藏浏览器窗口（不进任务栏）；只有明确传 false 才显示
    h = p.get("hide", True)
    if isinstance(h, str):
        h = h.strip().lower() not in ("0", "false", "no", "off", "")
    out["hide"] = bool(h)
    return out


def build_cmd(params=None):
    """组装命令行：`python -u xhs_bot.py --limit ... --max-scan ...`"""
    p = normalize(params)
    cmd = [sys.executable, "-u", SCRIPT,
           "--limit", str(p["limit"]),
           "--max-scan", str(p["max_scan"]),
           "--max-minutes", str(p["max_minutes"]),
           "--refresh-every", str(p["refresh_every"])]
    if p["dry"]:
        cmd.append("--dry")
    if not p["hide"]:
        cmd.append("--show-browser")
    return cmd


# ==================== 进程探活 ====================

STILL_ACTIVE = 259          # GetExitCodeProcess：进程还活着时的返回值


def _win_proc_info(pid):
    """Windows：返回 (是否存活, 创建时间epoch秒)。进程不存在返回 (False, None)。

    只看 OpenProcess 成功是不够的——父进程还握着子进程句柄时，已退出的子进程
    依然能被 OpenProcess 打开，必须再查 GetExitCodeProcess 是否为 STILL_ACTIVE。
    """
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.OpenProcess(0x1000 | 0x00100000, False, int(pid))  # QUERY_LIMITED|SYNCHRONIZE
        if not h:
            return False, None
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False, None
            alive = code.value == STILL_ACTIVE
            ts = None
            ct, et, kt, ut = (wintypes.FILETIME() for _ in range(4))
            if k32.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et),
                                   ctypes.byref(kt), ctypes.byref(ut)):
                ft = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
                ts = ft / 1e7 - 11644473600.0     # 1601-01-01 → 1970-01-01
            return alive, ts
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False, None


def _win_creation_ts(pid):
    """只为登记用：拿到创建时间即可，不关心是否存活。"""
    return _win_proc_info(pid)[1]


def _proc_alive(pid, expect_create_ts=None):
    """进程是否还活着。给了 expect_create_ts 时还会核对创建时间，防 PID 复用。"""
    if not pid:
        return False
    pid = int(pid)
    if sys.platform == "win32":
        alive, ts = _win_proc_info(pid)
        if not alive:
            return False
        if expect_create_ts and ts and abs(ts - float(expect_create_ts)) > 5:
            return False        # pid 被别的进程复用了
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True             # 存在但没权限，视为活着
    except Exception:
        return False
    return True


# ==================== 数据库 ====================

def _now():
    return datetime.now().isoformat(timespec="seconds")


def _latest(conn):
    return conn.execute(
        "SELECT * FROM bot_runs WHERE platform=? ORDER BY id DESC LIMIT 1",
        (PLATFORM,)).fetchone()


def _infer_state(row):
    """进程已死但没有退出码时，从日志推断结局。

    只看「本轮时间窗」内的事件：started_at 起、max_minutes 再加 2 分钟缓冲。
    否则日志里下一轮的事件会被算到这一轮头上，把崩溃误判成正常收尾。
    """
    started = row["started_at"] or ""
    try:
        t0 = datetime.fromisoformat(started)
    except Exception:
        return "stale"
    limit_min = _load_params(row["params"]).get("max_minutes") or 10
    t_end = t0.timestamp() + int(limit_min) * 60 + 120

    try:
        events = xhs_events.read_events()
    except Exception:
        events = []
    for e in reversed(events):
        ts = e.get("ts") or ""
        try:
            et = datetime.fromisoformat(ts).timestamp()
        except Exception:
            continue
        if et < t0.timestamp():
            break
        if et > t_end:
            continue          # 超出本轮窗口，属于别的轮次
        ev = e.get("event")
        if ev == FATAL:
            return "failed"
        if ev in _GRACEFUL:
            return "done"
    return "stale"


def _reconcile(conn):
    """把「库里写着 running 但进程其实没了」的僵尸行收敛掉，返回最新一行。"""
    row = _latest(conn)
    if not row or row["state"] != "running":
        return row
    proc = _RUN["proc"]
    mine = proc is not None and _RUN["run_id"] == row["id"]
    # 自己启动的那一轮：poll() 最准，顺便拿到退出码
    if mine and proc.poll() is None:
        return row
    if not mine and _proc_alive(row["pid"], row["pid_create_ts"]):
        return row
    rc = proc.returncode if mine else None
    if rc == 0:
        state = "done"
    elif rc is not None:
        state = "failed"
    else:
        state = _infer_state(row)      # 重启后拿不到退出码，只能看日志
    conn.execute("UPDATE bot_runs SET state=?, returncode=?, finished_at=? WHERE id=?",
                 (state, rc, _now(), row["id"]))
    conn.commit()
    return _latest(conn)


def _open_conn():
    return database.get_conn()


# ==================== 对外接口 ====================

def is_running():
    conn = _open_conn()
    try:
        row = _reconcile(conn)
        return bool(row and row["state"] == "running")
    finally:
        conn.close()


def start(params=None):
    """启动一轮。返回 {started, run_id, pid, cmd, params}；已在跑则抛 AlreadyRunning。"""
    params = normalize(params)
    return _start_cmd(build_cmd(params), params)


def _start_cmd(cmd, params):
    """启动给定命令行并登记状态（start 的实现，测试可传入假命令）。"""
    with _LOCK:
        conn = _open_conn()
        try:
            row = _reconcile(conn)
            if row and row["state"] == "running":
                raise AlreadyRunning("已有一轮正在运行，请等它结束")

            started_at = _now()
            lf = open(LAST_RUN_LOG, "w", encoding="utf-8")
            try:
                proc = subprocess.Popen(cmd, cwd=str(PROJECT_DIR), stdout=lf,
                                        stderr=subprocess.STDOUT)
            except Exception:
                lf.close()
                raise
            # 子进程已继承句柄，父进程这份可以关掉（否则每轮泄漏一个文件句柄）
            lf.close()

            create_ts = _win_creation_ts(proc.pid) if sys.platform == "win32" else None
            try:
                cur = conn.execute(
                    "INSERT INTO bot_runs(platform, pid, pid_create_ts, started_at,"
                    " state, params, log_path) VALUES(?,?,?,?, 'running', ?, ?)",
                    (PLATFORM, proc.pid, create_ts, started_at,
                     _dump_params(params), str(LAST_RUN_LOG)))
                conn.commit()
            except sqlite3.IntegrityError:
                # 唯一索引兜底：另一个 worker（或另一次点击）抢先插入了 running
                proc.kill()
                raise AlreadyRunning("已有一轮正在运行，请等它结束")

            _RUN.update({"proc": proc, "run_id": cur.lastrowid})
            return {"started": True, "run_id": cur.lastrowid, "pid": proc.pid,
                    "cmd": cmd, "params": params}
        finally:
            conn.close()


def status(tail_chars=2000):
    """当前 / 最近一轮：是否在跑、pid、退出码、参数、结局、日志尾巴。

    running 以数据库 + 进程验活为准，因此后端重启后依然准确。
    """
    conn = _open_conn()
    try:
        row = _reconcile(conn)
    finally:
        conn.close()

    tail = ""
    try:
        if LAST_RUN_LOG.exists():
            tail = LAST_RUN_LOG.read_text(encoding="utf-8", errors="ignore")[-tail_chars:]
    except Exception:
        tail = ""

    if not row:
        return {"running": False, "pid": None, "returncode": None, "started_at": None,
                "finished_at": None, "state": "idle", "params": _empty_params(),
                "tail": tail, "log_path": str(LAST_RUN_LOG), "run_id": None}

    return {
        "running": row["state"] == "running",
        "pid": row["pid"],
        "returncode": row["returncode"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "state": row["state"],
        "params": _load_params(row["params"]),
        "tail": tail,
        "log_path": str(LAST_RUN_LOG),
        "run_id": row["id"],
    }


def history(limit=20):
    """最近的运行记录（页面「历史轮次」可用）。"""
    conn = _open_conn()
    try:
        _reconcile(conn)
        rows = conn.execute(
            "SELECT * FROM bot_runs WHERE platform=? ORDER BY id DESC LIMIT ?",
            (PLATFORM, max(1, int(limit)))).fetchall()
        return [{"run_id": r["id"], "state": r["state"], "pid": r["pid"],
                 "started_at": r["started_at"], "finished_at": r["finished_at"],
                 "returncode": r["returncode"], "params": _load_params(r["params"])}
                for r in rows]
    finally:
        conn.close()


# ==================== 参数序列化 ====================

def _dump_params(p):
    return json.dumps(p, ensure_ascii=False)


def _load_params(raw):
    if not raw:
        return _empty_params()
    try:
        p = json.loads(raw)
    except Exception:
        return _empty_params()
    out = {k: p.get(k) for k in (*PARAM_LIMITS, "dry")}
    return out


def _empty_params():
    return {k: None for k in (*PARAM_LIMITS, "dry")}
