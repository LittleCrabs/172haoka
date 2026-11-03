#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书引流全自动机器人（Playwright 持久化上下文版）

流程：机器人自行启动 Chrome（独立 profile，登录态持久保存）→ 按关键词浏览搜索
结果页 → 抓帖子（正文 / IP 属地 / post_id）→ 调本地 /api/xhs/reply 判定目标人群 →
命中且未回复过 → 自动在帖子评论区发送生成的回复 → 记录 JSONL 日志。
浏览器由机器人全权管理：跑时自动打开、跑完自动关闭，无需手动保持窗口。

首次使用（登录一次即可）：
    backend/.venv/Scripts/python.exe xhs_bot.py login
    → 弹出浏览器，扫码登录小红书，登录成功后按回车保存退出。

运行：
    backend/.venv/Scripts/python.exe xhs_bot.py --dry          # 只抓帖+判定+生成，不发评论
    backend/.venv/Scripts/python.exe xhs_bot.py --limit 10     # 本轮最多处理 10 帖（正式发）
    backend/.venv/Scripts/python.exe xhs_bot.py --keywords "流量卡,校园卡"

安全护栏（全自动模式的底线）：
    - 每日发送上限 DAILY_SEND_LIMIT，超了自动收工
    - 每帖之间随机间隔 SEND_INTERVAL
    - 黑名单关键词（涉政/敏感/竞品纠纷帖不碰）
    - 已回复帖子去重（后端 xhs_replies 表 + 本地 JSONL 双保险）
    - 是否该发由后端判定（阈值在设置页「小红书」里配，宁缺毋滥）
"""
import argparse
import asyncio
import datetime as dt
import json
import random
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# 日志事件名 / 路径与后端共用一份契约（backend/app/services/xhs_events.py）。
# bot 是独立脚本、不 import 后端包，这里手动把 backend/ 加进 import 路径；
# xhs_events 只依赖标准库，不会连带拉起 FastAPI 或数据库。
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app.services.xhs_events import (  # noqa: E402
    write_event, LOG_PATH,
    START, DONE, SCANNED, HIT, SENT,
    SKIP_NO_CONTENT, SKIP_BLACKLIST, SKIP_REPLIED, SKIP_CACHED, NOT_TARGET, NO_REPLY,
    OPEN_FAILED, EXTRACT_FAILED, API_ERROR, SEND_FAILED, SEND_UNVERIFIED,
    FEED_REFRESH, SCROLL_STALL, STOP_TIMEOUT, STOP_NO_MORE_CONTENT,
    STOP_DAILY_LIMIT, INTERRUPTED, FATAL,
    SEND_WAIT, PAGE_RECOVER, PAGE_LOST,
    WINDOW_HIDDEN, WINDOW_HIDE_FAILED, CHROME_STALE,
)

# ------------------------- 配置（按需改） -------------------------
BASE_URL = "http://127.0.0.1:8123"        # 后端地址
USER_DATA_DIR = str(Path(__file__).parent / ".chrome-xhs")  # 浏览器 profile（登录态存这里）
CHROME_CHANNEL = "chrome"                 # 用系统安装的 Chrome 稳定版（免下载，指纹真实）
DAILY_SEND_LIMIT = 20                     # 每日真实发送上限
SEND_INTERVAL = (90, 240)                 # 每帖之间随机间隔秒数（含浏览时间）
BLACKLIST = ("投诉", "维权", "骗", "诈骗", "封号", " Verizon", "物联网卡", "死卡")

# 信息流刷新策略（防止一直在同一批推荐里打转 / 滑不动时死循环）
STALL_LIMIT = 3            # 连续滑动这么多次都没加载出新卡片 → 刷新首页
MAX_REFRESH = 3            # 单轮最多刷新首页次数，超了还没新内容就收工
REFRESH_EVERY = 10         # 每浏览这么多帖就刷新首页换一批推荐
# ↑ 实测首页顶部（刷新后的第一屏）命中率最高，越往下滑越偏，所以"勤刷新、少下滑"：
#   每批只看 10 条就换一批，比在旧推荐里一路滑到底的产出高得多。
MAX_MINUTES = 10           # 单轮最长运行分钟数（最终兜底）
# -----------------------------------------------------------------

ENDPOINT = BASE_URL.rstrip("/") + "/api/xhs/reply"
FEED_URL = "https://www.xiaohongshu.com/explore"
ACTION_TIMEOUT = 15000      # 单个页面操作的默认等待上限（毫秒），防止页面失效时无限等


def log(event, **kw):
    """结构化日志：打印 + 追加 JSONL（写入格式由 xhs_events.write_event 统一）。"""
    rec = write_event(event, **kw)
    print("[%s] %s %s" % (rec["ts"], event, " ".join("%s=%s" % kv for kv in kw.items())))
    return rec


def replied_ids_today():
    """本地 JSONL 里今天已真实发送的 post_id 集合。"""
    today = dt.date.today().isoformat()
    ids = set()
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") == SENT and str(r.get("ts", "")).startswith(today):
                ids.add(r.get("post_id"))
    return ids


def api_reply(post):
    """调后端判定 + 生成回复。
    注意：不传后端的 dry_run（那是"只拼 prompt 不调模型"的意思，用于调试）；
    这里始终让后端真实生成回复，发不发由本地 --dry 决定。"""
    payload = {
        "post_content": post.get("content", ""),
        "post_id": post.get("post_id"),
        "region": post.get("region"),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore"))}
    except Exception as e:
        return {"error": str(e)}


def api_mark_sent(post_id):
    """评论真的发出去之后回调后端，回填 delivered_at。

    后端在生成回复时就会写一条 xhs_replies（replied_at），dry 试跑也会写，
    所以只有这一笔回调才能证明「评论确实到了小红书」。
    失败不影响本轮（最多页面显示成"仅生成"），所以只返回错误不抛。
    """
    if not post_id:
        return {"error": "no post_id"}
    data = json.dumps({"post_id": post_id}).encode("utf-8")
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/api/xhs/mark-sent", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)[:120]}


def blacklisted(text):
    return any(w in text for w in BLACKLIST)


# ================= Playwright 部分 =================

_JS_EXTRACT = """() => {
    const pick = (sel) => { const e = document.querySelector(sel); return e ? (e.innerText || '').trim() : ''; };
    const title = pick('#detail-title');
    const content = pick('#detail-desc') || pick('.note-text') || pick('.desc');
    // 地区：详情底部「34分钟前 天津」「编辑于 3天前 江苏」「1小时前 四川」
    let region = '';
    const dEl = document.querySelector('.note-content .date, .bottom-container .date, .date');
    const dt = dEl ? (dEl.innerText || '').trim() : '';
    const m = dt.match(/(?:前|编辑于[^\\s]*)\\s*([\\u4e00-\\u9fa5]{2,6})\\s*$/);
    if (m) region = m[1];
    return {title, content, date_text: dt, region};
}"""


def _region_from_text(t):
    """从「1小时前 四川」这类文本尾部取地区名。"""
    import re
    if not t:
        return None
    m = re.search(r"(?:前|编辑于[^\s]*)\s*([\u4e00-\u9fa5]{2,6})\s*$", t)
    return m.group(1) if m else None


async def _open_feed(page, tries=3):
    """（重新）打开首页信息流，拿一批新的推荐。成功返回 True。

    加重试：上一页还有没走完的导航时，goto 会抛 net::ERR_ABORTED。
    以前一次失败就 fatal 整轮收工（日志里 18:58 那轮就是这么断的），
    现在按 Escape 清掉残余弹层后重试，三次都不行才认输。
    """
    last = None
    for i in range(tries):
        try:
            await page.goto(FEED_URL, wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_timeout(4000 + random.randint(0, 1500))
            return True
        except Exception as e:
            last = e
            if i + 1 < tries:
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                await page.wait_for_timeout(1200 + i * 1500)
    log(FATAL, err="打开信息流失败 %d 次：%s" % (tries, str(last)[:120]))
    return False


def _is_feed_url(url):
    """当前是否停在信息流列表页（/explore 或首页 /）。

    详情页是 /explore/<post_id>?...，搜索页是 /search_result，个人页是 /user/profile，
    这些都不算列表页 —— 一旦停在那种页面上，继续点 note-item 全是错的。
    """
    if not url or "xiaohongshu.com" not in url:
        return False
    path = url.split("xiaohongshu.com", 1)[1].split("?")[0].split("#")[0].rstrip("/")
    return path in ("", "/explore")


async def _ensure_feed(page, where=""):
    """确保停在信息流列表页；跑偏了就复位。返回 True 表示现在在列表页。

    跑偏的常见原因：手动按了浏览器「返回上一级」、点了侧边栏、搜索跳转、
    或详情弹层被手动关掉后 URL 没回退。复位顺序是 Escape → 重开信息流。
    """
    try:
        if page.is_closed():
            return False
        url = page.url
    except Exception:
        return False
    if _is_feed_url(url):
        return True

    log(PAGE_RECOVER, where=where, url=url[:80])
    try:
        await page.keyboard.press("Escape")      # 先试关详情弹层
        await page.wait_for_timeout(800)
        if _is_feed_url(page.url):
            return True
    except Exception:
        pass
    return await _open_feed(page)


async def browse_and_process(page, args, sent_today):
    """首页信息流下滑浏览：点开帖子 → 抓正文/地区 → 判定 → 命中就当场发评论 → 关闭继续滑。

    刷新策略：
      - 连续 STALL_LIMIT 次滑动都没加载出新卡片 → 重开首页换一批；最多 MAX_REFRESH 次，
        仍无新内容就收工（防止小红书限流/无更多推荐时死循环空转）
      - 每处理 REFRESH_EVERY 帖主动刷新一次首页，避免一直在同一批推荐里打转
      - 整轮超过 MAX_MINUTES 分钟强制收工
    """
    t0 = time.time()
    max_seconds = max(1, args.max_minutes) * 60
    await _open_feed(page)

    seen = set()
    processed = scanned = idx = 0
    stall = refresh_count = refreshed = 0
    last_refresh_at = 0

    while processed < args.limit and scanned < args.max_scan:
        # 兜底 0：浏览器窗口被关掉 / 页面失效 → 立即收工，不要在死页面上空转
        try:
            if page.is_closed():
                log(PAGE_LOST, scanned=scanned, processed=processed)
                break
        except Exception:
            log(PAGE_LOST, scanned=scanned, processed=processed)
            break

        # 兜底 0.5：每轮开头确认还在信息流列表页（被手动返回上一级就复位）
        if not await _ensure_feed(page, where="loop"):
            log(PAGE_LOST, scanned=scanned, processed=processed)
            break

        # 兜底 1：总时长
        if time.time() - t0 > max_seconds:
            log(STOP_TIMEOUT, minutes=args.max_minutes,
                scanned=scanned, processed=processed)
            break

        # 兜底 2：每浏览 N 帖主动刷新首页，换一批推荐
        # （按「浏览数」而非「命中数」判断：命中很稀疏，按命中数几乎触发不到）
        if scanned and scanned - last_refresh_at >= args.refresh_every:
            last_refresh_at = scanned
            refresh_count = 0        # 主动刷新不计入异常刷新额度
            log(FEED_REFRESH, reason="periodic", scanned=scanned, processed=processed)
            if not await _open_feed(page):
                break
            refreshed += 1
            idx = stall = 0

        items = page.locator("section.note-item, div.note-item")
        count = await items.count()
        if idx >= count:
            # 本屏看完，下滑加载下一批（这就是「下滑刷新」的自然行为）
            prev_count = count
            await page.mouse.wheel(0, 2200 + random.randint(0, 500))
            await page.wait_for_timeout(1800 + random.randint(0, 900))
            new_count = await items.count()

            if new_count > prev_count:
                stall = 0
                idx = max(0, prev_count - 6)   # 回退 6 张，防止漏掉新加载的
            else:
                # 没加载出新内容：直接跳到末尾继续滚，让停滞计数快速累加
                idx = new_count
                stall += 1
                log(SCROLL_STALL, stalls=stall, cards=new_count)
                if stall >= STALL_LIMIT:
                    stall = 0
                    if refresh_count >= MAX_REFRESH:
                        log(STOP_NO_MORE_CONTENT, cards=new_count,
                            scanned=scanned, processed=processed)
                        break
                    refresh_count += 1
                    log(FEED_REFRESH, reason="stall", times=refresh_count)
                    if not await _open_feed(page):
                        break
                    refreshed += 1
                    idx = 0
            continue

        item = items.nth(idx)
        idx += 1
        try:
            await item.scroll_into_view_if_needed(timeout=5000)
            await item.click()
            await page.wait_for_timeout(2200 + random.randint(0, 900))
        except Exception as e:
            log(OPEN_FAILED, err=str(e)[:80])
            continue

        # 从 URL 取 post_id（点击后自带 xsec_token，直接拼链接是打不开的）
        try:
            pid = page.url.split("/explore/")[1].split("?")[0]
        except Exception:
            pid = ""
        if not pid or pid in seen:
            await _close_detail(page)
            continue
        seen.add(pid)
        scanned += 1

        try:
            info = await page.evaluate(_JS_EXTRACT)
        except Exception as e:
            log(EXTRACT_FAILED, post_id=pid, err=str(e)[:80])
            await _close_detail(page)
            continue

        content = (info.get("content") or "").strip()
        title = (info.get("title") or "").strip()
        region = info.get("region") or _region_from_text(info.get("date_text"))
        if not content:
            log(SKIP_NO_CONTENT, post_id=pid)
            await _close_detail(page)
            continue

        full = (title + "\n" + content).strip()
        log(SCANNED, post_id=pid, title=title[:24], region=region or "-")

        if blacklisted(full):
            log(SKIP_BLACKLIST, post_id=pid)
            await _close_detail(page)
            continue
        if pid in sent_today:
            log(SKIP_REPLIED, post_id=pid)
            await _close_detail(page)
            continue

        post = {"post_id": pid, "title": title, "content": full,
                "region": region, "url": page.url}
        post_url = page.url  # 含 xsec_token，事后可用于复核
        resp = api_reply(post)
        if resp.get("error"):
            log(API_ERROR, post_id=pid, err=resp["error"][:120])
            await _close_detail(page)
            continue
        if not resp.get("should_reply"):
            log(NOT_TARGET, post_id=pid, reason=(resp.get("reason") or "")[:50])
            await _close_detail(page)
            continue
        # 阈值只在后端判一次（should_reply），这里只挡重复回复，
        # 否则设置页改了阈值、机器人还按旧的常量放行
        if resp.get("already_replied"):
            log(SKIP_CACHED, post_id=pid, score=resp.get("score"))
            await _close_detail(page)
            continue
        reply_text = resp.get("reply") or ""
        if not reply_text:
            log(NO_REPLY, post_id=pid)
            await _close_detail(page)
            continue

        processed += 1
        log(HIT, post_id=pid, score=resp.get("score"), region=resp.get("region"),
            tone=resp.get("tone"), reply=reply_text[:40])
        if args.dry:
            print("    [dry 回复预览] %s\n" % reply_text)
            await _close_detail(page)
            continue

        ok, err = await send_comment(page, reply_text)
        if ok:
            log(SENT, post_id=pid, score=resp.get("score"), region=resp.get("region"),
                reply=reply_text[:50], url=post_url)
            marked = api_mark_sent(pid)
            if marked.get("error"):
                # 只是页面上会显示成"仅生成"，评论本身已经发出去了
                print("    [警告] 回填发送状态失败：%s" % marked["error"])
        else:
            log(SEND_FAILED, post_id=pid, err=err)
        await _close_detail(page)
        # 每次真实发送后长间隔，模拟真人浏览节奏。
        # 必须用 asyncio.sleep：原来的 time.sleep 会把整个事件循环冻结，
        # 期间既不能响应任何页面操作，也不会写进度日志，看上去和死机一样。
        wait_s = random.randint(*SEND_INTERVAL)
        log(SEND_WAIT, seconds=wait_s, processed=processed, scanned=scanned)
        await asyncio.sleep(wait_s)

    log(DONE, processed=processed, scanned=scanned,
        elapsed=int(time.time() - t0), refreshes=refreshed)
    return processed


async def _close_detail(page):
    """关闭详情弹层，回到信息流。返回 True 表示确认已回到列表页。

    以前是「按了 Escape 就当关掉了」，如果弹层没关（或用户手动返回后 URL 已错位），
    后续所有操作都会打在一个错位的页面上。现在关完必须校验 URL。
    """
    try:
        if page.is_closed():
            return False
        if _is_feed_url(page.url):
            return True                  # 本来就在列表（点开失败 / 已被手动关掉）
    except Exception:
        return False

    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(900)
    except Exception:
        pass
    if _is_feed_url(page.url):
        return True

    try:
        btn = page.locator(".close, .close-mask, [class*='close']").first
        if await btn.count() > 0:
            await btn.click(timeout=2000)
            await page.wait_for_timeout(900)
    except Exception:
        pass
    if _is_feed_url(page.url):
        return True
    return await _ensure_feed(page, where="close_detail")


async def send_comment(page, reply_text):
    """在当前打开的帖子详情弹层里发评论。返回 (ok, err)。

    真实结构（2026-11 实测）：
      - 占位入口：<span>说点什么...</span>，点它才会展开输入区
      - 编辑器：<p id="content-textarea" class="content-input" contenteditable="true">
      - 发送按钮：<button class="btn submit gray">发送</button>（输入文字后去掉 gray）
    """
    try:
        # 1) 点「说点什么...」展开评论输入区
        trigger = page.locator("span:has-text('说点什么'), .focus-comments").first
        if await trigger.count() > 0:
            try:
                await trigger.click(timeout=4000)
                await page.wait_for_timeout(800)
            except Exception:
                pass

        # 2) 找到真实编辑器（是 <p> 不是 <div>！）
        box = page.locator("#content-textarea, .content-input[contenteditable='true']").first
        if await box.count() == 0:
            box = page.locator("[contenteditable='true']").last
        await box.wait_for(state="visible", timeout=10000)
        await box.click()
        await page.wait_for_timeout(300)
        await box.type(reply_text, delay=random.randint(45, 110))  # 拟人输入速度
        await page.wait_for_timeout(700)

        # 3) 发送按钮：等 gray 消失（有内容才可点）
        btn = page.locator("button.btn.submit:visible, button:has-text('发送'):visible").first
        if await btn.count() == 0:
            return False, "找不到发送按钮"
        for _ in range(14):
            cls = await btn.get_attribute("class") or ""
            if "gray" not in cls:
                break
            await page.wait_for_timeout(250)
        await btn.click()
        await page.wait_for_timeout(2600)

        # 4) 校验：输入框已清空（发送成功会清空）
        left = (await box.inner_text()).strip()
        if left:
            return False, "发送后输入框未清空（可能未发出）"

        # 5) 二次校验：评论区里出现刚发的内容前 8 个字（仅供参考，不作为失败依据，
        #    避免误判成失败后重发造成重复评论）
        probe = reply_text[:8]
        try:
            top_comments = await page.evaluate("""() => {
              const out = [];
              document.querySelectorAll('.comment-item, [class*="comment-item"]').forEach(e => {
                const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
                if (t) out.push(t.slice(0, 40));
              });
              return out.slice(0, 3);
            }""")
        except Exception:
            top_comments = []
        if top_comments and not any(probe in c for c in top_comments):
            log(SEND_UNVERIFIED, probe=probe, top=top_comments)
        return True, ""
    except Exception as e:
        return False, str(e)[:160]


async def launch_browser(p, hide=True, _retry=True):
    """启动机器人专用浏览器（持久化 profile，登录态跨次保留）。
    返回 (browser, page)。加反自动化检测参数，降低被识别概率。

    hide=True 时窗口不进任务栏：Chrome 仍以有头模式运行（指纹与真人浏览器一致，
    这是不用 headless 的原因 —— 小红书对无头特征判定很严），只是启动后把窗口从
    Windows 层面隐藏。窗口不可见会让 Chrome 认为页面在后台并降低渲染/timer 优先级，
    所以同时要关掉三种节流，否则会点不动、懒加载不触发。
    """
    import os

    before = _chrome_pids()          # 记录启动前已有的 Chrome 进程，用来认领新进程
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")}
    try:
        browser = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel=CHROME_CHANNEL,
            headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled", "--no-first-run",
                  "--no-default-browser-check", "--start-maximized",
                  "--hide-crash-restore-bubble",     # 别弹"要恢复页面吗"
                  # 下面几条是「窗口隐藏后仍能正常工作」的前提
                  "--disable-background-timer-throttling",
                  "--disable-backgrounding-occluded-windows",
                  "--disable-renderer-backgrounding",
                  "--disable-features=CalculateNativeWinOcclusion",
                  # 先放到屏幕外，避免启动瞬间闪一下白窗口
                  "--window-position=-32000,-32000"],
            env=env,
        )
    except Exception as e:
        # 最常见的原因：上一轮被强杀，Chrome 没跟着退出，还占着 profile 锁。
        # 新实例启动后会把标签交给旧实例然后自己退出，报 "browser has been closed"。
        if _retry and "has been closed" in str(e):
            stale = _kill_stale_chrome()
            log(CHROME_STALE, killed=stale)
            if stale:
                return await launch_browser(p, hide=hide, _retry=False)
        raise

    page = browser.pages[0] if browser.pages else await browser.new_page()
    page.set_default_timeout(ACTION_TIMEOUT)   # 页面失效时别干等 30 秒
    await page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    if hide:
        # 等窗口真正创建出来再隐藏（Chrome 是异步建窗的，太早找不到句柄）
        await page.wait_for_timeout(1200)
        handles = []
        for _ in range(10):
            handles = _chrome_windows(_chrome_pids() - before)
            if handles:
                break
            await page.wait_for_timeout(400)
        if handles:
            _set_window_visible(handles, False)
            log(WINDOW_HIDDEN, count=len(handles))
        else:
            log(WINDOW_HIDE_FAILED, err="没找到 Chrome 窗口句柄，窗口将保持可见")
    return browser, page


def _kill_stale_chrome():
    """杀掉占用机器人 profile 的残留 Chrome（只认 --user-data-dir 含 .chrome-xhs 的）。

    上一轮被强杀时 Chrome 会活下来，锁住 profile，导致下一轮根本起不来。
    返回被清理的主进程 pid 列表。
    """
    if sys.platform != "win32":
        return []
    tag = Path(USER_DATA_DIR).name          # .chrome-xhs
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        "Where-Object { $_.CommandLine -like '*%s*' -and $_.CommandLine -notlike '*--type=*' } | "
        "ForEach-Object { Write-Output $_.ProcessId; "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    ) % tag
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=30,
        ).stdout.decode("utf-8", "ignore")
    except Exception:
        return []
    return [int(x) for x in out.split() if x.strip().isdigit()]


def _chrome_pids():
    """当前所有 chrome.exe 的 pid 集合。"""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
                             capture_output=True).stdout.decode("utf-8", "ignore")
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        cells = [c.strip('"') for c in line.split('","')]
        if len(cells) >= 2 and cells[1].isdigit():
            pids.add(int(cells[1]))
    return pids


def _chrome_windows(pids):
    """找出属于这些 pid 的 Chrome 顶层窗口句柄。"""
    if not pids or sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        found = []
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and u32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(128)
                u32.GetClassNameW(hwnd, buf, 128)
                if buf.value == "Chrome_WidgetWin_1":     # Chrome 主窗口类名
                    found.append(hwnd)
            return True

        u32.EnumWindows(proto(cb), 0)
        return found
    except Exception:
        return []


def _set_window_visible(handles, visible):
    """显示 / 隐藏窗口。SW_HIDE 会让任务栏图标一起消失。"""
    if not handles or sys.platform != "win32":
        return
    try:
        import ctypes
        u32 = ctypes.WinDLL("user32")
        for h in handles:
            u32.ShowWindow(h, 5 if visible else 0)   # 5=SW_SHOW, 0=SW_HIDE
            if visible:
                u32.SetForegroundWindow(h)
    except Exception:
        pass


async def cmd_login():
    """登录模式：打开小红书等用户扫码，检测到登录成功后自动退出保存。"""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser, page = await launch_browser(p, hide=False)   # 扫码必须看得见窗口
        await page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
        print("浏览器已打开，请在窗口里扫码登录小红书……（检测到登录成功后会自动保存退出）")
        ok = False
        for i in range(120):  # 最多等 4 分钟
            await page.wait_for_timeout(2000)
            try:
                logged = await page.evaluate("""() => {
                    // 已登录：右上角出现用户入口，且没有登录弹窗
                    const modal = document.querySelector('.login-container, .sign-container');
                    const user = document.querySelector('.user.side-bar-component, .avatar_item, [class*="avatar"]');
                    return !!user && !modal;
                }""")
            except Exception:
                logged = False
            if logged:
                ok = True
                break
        if ok:
            await page.wait_for_timeout(2500)  # 等 cookie/state 落盘
            print("✅ 检测到登录成功，profile 已保存。以后直接跑 --dry / 正式模式即可。")
        else:
            print("⚠️ 等待超时未检测到登录。profile 已保留，可重跑 login 继续。")
        await browser.close()
        return ok


async def run(args):
    from playwright.async_api import async_playwright

    sent_today = replied_ids_today()
    log(START, mode="dry" if args.dry else "live", limit=args.limit,
        max_scan=args.max_scan, max_minutes=args.max_minutes, sent_today=len(sent_today))
    if not args.dry and len(sent_today) >= DAILY_SEND_LIMIT:
        log(STOP_DAILY_LIMIT, sent_today=len(sent_today))
        return

    async with async_playwright() as p:
        browser, page = await launch_browser(p, hide=not args.show_browser)
        try:
            await browse_and_process(page, args, sent_today)
        finally:
            try:
                await browser.close()          # 用户手动关掉窗口时 close 会抛，不能吞掉主流程
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description="小红书引流全自动机器人（首页信息流版）")
    ap.add_argument("--dry", action="store_true", help="只抓帖+判定+生成回复，不真发评论")
    ap.add_argument("--limit", type=int, default=30, help="本轮最多处理（判定命中）帖子数")
    ap.add_argument("--max-scan", type=int, default=60, help="本轮最多浏览帖子数（防无限滑动）")
    ap.add_argument("--max-minutes", type=int, default=MAX_MINUTES,
                    help="本轮最长运行分钟数，超时强制收工（默认 %d）" % MAX_MINUTES)
    ap.add_argument("--refresh-every", type=int, default=REFRESH_EVERY,
                    help="每浏览多少帖刷新一次首页换推荐（默认 %d）" % REFRESH_EVERY)
    ap.add_argument("--show-browser", action="store_true",
                    help="不隐藏浏览器窗口（默认隐藏，不进任务栏；调试或过验证码时用）")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "login"],
                    help="login=打开浏览器扫码登录（首次使用）；run=执行自动化（默认）")
    args = ap.parse_args()

    try:
        if args.command == "login":
            asyncio.run(cmd_login())
        else:
            asyncio.run(run(args))
    except KeyboardInterrupt:
        log(INTERRUPTED)
    except Exception as e:
        log(FATAL, err=str(e)[:200])
        sys.exit(1)


if __name__ == "__main__":
    main()
