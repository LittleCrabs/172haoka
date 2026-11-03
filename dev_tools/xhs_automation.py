#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书引流自动化 · 示例脚手架（仅供对接参考，不能直接运行抓取 / 发帖）

职责边界：
- 本脚本只负责「调本地 /api/xhs/reply 接口 + 按 should_reply / score 决定发不发」。
- 【拉帖子】和【发回复】这两步依赖你的浏览器 / 账号，无法由后端代劳，已在下方留成
  清晰桩点（fetch_posts / send_reply），你把自己的自动化工具接进去即可。

运行（需后端 127.0.0.1:8123 在跑）：
    python xhs_automation.py --demo        # 用内置示例帖子跑一遍，不真发
    python xhs_automation.py --demo --dry-run   # 连 LLM 调用都省，只看判定
    python xhs_automation.py               # 接好你自己的 fetch_posts / send_reply 后正式跑
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

# ------------------------- 配置（按需改） -------------------------
BASE_URL = "http://127.0.0.1:8123"      # 后端地址
MIN_SCORE = 0                            # 仅 score >= 此值才发（0 = 只要命中人群就发）
DRY_RUN = False                          # True = 只生成不真发（send_reply 不会被调用）
# -----------------------------------------------------------------

ENDPOINT = BASE_URL.rstrip("/") + "/api/xhs/reply"


def call_xhs(post, dry_run=DRY_RUN):
    """调本地接口，返回解析后的 JSON。post: {post_content, region?, ip?, audience?}。"""
    payload = {
        "post_content": post.get("post_content", ""),
        "region": post.get("region"),
        "ip": post.get("ip"),
        "audience": post.get("audience"),
        "dry_run": dry_run,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore"))}
    except Exception as e:
        return {"error": str(e)}


def decide(resp):
    """根据接口返回决定是否发送。返回 (是否发送, 原因)。"""
    if resp.get("error"):
        return False, "接口报错：%s" % resp["error"]
    if not resp.get("should_reply"):
        return False, "非目标人群：%s" % resp.get("reason", "")
    if resp.get("score", 0) < MIN_SCORE:
        return False, "score %s < 阈值 %s" % (resp.get("score"), MIN_SCORE)
    if not resp.get("reply"):
        return False, "未生成回复（候选为空 / 未配置模型）"
    return True, "命中(%s) score=%s" % (
        "、".join(s["category"] for s in resp.get("signals", [])), resp.get("score"))


# ===== 以下两段是你必须替换成自己工具的地方 =====

def fetch_posts():
    """【需替换】从小红书拉取待处理帖子。
    返回 list[dict]，每条至少含 post_content（正文，通常自带 IP属地），
    可选 region / ip / audience。
    实现方式举例：用你的浏览器自动化 / 爬虫拿到帖子正文与属地，组装成 dict 返回。
    未接入时返回 []，脚本不会做任何事。
    """
    return []  # TODO: 接入你的抓帖工具


def send_reply(post, reply_text):
    """【需替换】把 reply_text 发到该帖子的评论区 / 私信。
    未接入时打印即可（配合 DRY_RUN 用于试跑）。
    """
    print("    -> [模拟发送] 帖子: %s\n      回复: %s" % (
        post.get("post_content", "")[:30], reply_text))


# ===================================================

def demo_posts():
    """内置示例帖子，用于不接浏览器也能跑通整条链路。post_id 用于去重演示。"""
    return [
        {"post_id": "demo_1",
         "post_content": "IP属地：江苏。手机流量总不够用，每个月都要额外买流量包，太贵了😭",
         "region": "江苏"},
        {"post_id": "demo_2",
         "post_content": "学生党，大学宿舍wifi烂，想要张便宜大流量的校园卡", "region": "杭州"},
        {"post_id": "demo_3",
         "post_content": "今天做了一道超好吃的红烧肉，做法分享～", "region": "江苏"},  # 非人群
        {"post_id": "demo_4",
         "post_content": "异地工作，老家号不想换，想办张当地流量卡", "region": "广东"},
    ]


def run(posts):
    sent = skip = 0
    for i, post in enumerate(posts, 1):
        print("\n[%d/%d] %s" % (i, len(posts), post.get("post_content", "")[:40]))
        resp = call_xhs(post)
        ok, why = decide(resp)
        print("    判定: should_reply=%s score=%s region=%s | %s" % (
            resp.get("should_reply"), resp.get("score"), resp.get("region"), why))
        if not ok:
            skip += 1
            continue
        if DRY_RUN:
            print("    [DRY_RUN] 不真发。回复预览: %s" % resp.get("reply"))
            continue
        send_reply(post, resp.get("reply"))
        sent += 1
        time.sleep(2)  # 简单限速，避免触发风控
    print("\n完成：发送 %d / 跳过 %d" % (sent, skip))


def main():
    ap = argparse.ArgumentParser(description="小红书引流自动化示例")
    ap.add_argument("--demo", action="store_true", help="用内置示例帖子跑一遍")
    ap.add_argument("--dry-run", action="store_true", help="只生成不真发（连发帖桩点都不触发）")
    args = ap.parse_args()

    global DRY_RUN
    if args.dry_run:
        DRY_RUN = True

    posts = demo_posts() if args.demo else fetch_posts()
    if not posts:
        print("没有待处理帖子：未接入 fetch_posts() 或非 demo 模式且无数据。")
        sys.exit(0)
    run(posts)


if __name__ == "__main__":
    main()
