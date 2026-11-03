#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对「日志说已发送」的评论，在小红书上到底存不存在。

为什么不直接用 post_id 拼链接：小红书详情页需要 xsec_token（点击卡片时自动带上），
拿 post_id 直接拼 /explore/<id> 会打不开或跳回首页。所以这里从 xhs_bot_log.jsonl
的 sent 事件里取当时抓到的完整 URL。

跑法：
    backend/.venv/Scripts/python.exe dev_tools/check_sent.py [条数]

输出每条：是否在评论区找到回复的前 8 个字。
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import xhs_bot as bot  # noqa: E402

GRAB = """() => {
  const out = [];
  document.querySelectorAll('.comment-item, [class*="comment-item"]').forEach(e => {
    const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
    if (t) out.push(t.slice(0, 100));
  });
  return out;
}"""


def sent_events(n):
    evs = []
    for line in (ROOT / "xhs_bot_log.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") == "sent" and r.get("url"):
            evs.append(r)
    return evs[-n:]


async def main(n=2):
    from playwright.async_api import async_playwright

    targets = sent_events(n)
    if not targets:
        print("日志里没有带 URL 的 sent 记录")
        return 1

    async with async_playwright() as p:
        browser, page = await bot.launch_browser(p, hide=True)
        try:
            for ev in targets:
                probe = (ev.get("reply") or "")[:8]
                print("\n" + "=" * 70)
                print("%s  帖子 %s" % (ev.get("ts"), (ev.get("post_id") or "")[:12]))
                print("期望内容开头：%s" % probe)
                try:
                    await page.goto(ev["url"], wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(4200)
                    for _ in range(3):        # 往下滚，评论区可能懒加载
                        await page.mouse.wheel(0, 1400)
                        await page.wait_for_timeout(900)
                    comments = await page.evaluate(GRAB)
                except Exception as e:
                    print("打开失败：%s" % str(e)[:120])
                    continue

                print("抓到评论 %d 条" % len(comments))
                hit = [c for c in comments if probe and probe in c]
                if hit:
                    print("✅ 找到我们的评论：%s" % hit[0][:70])
                else:
                    print("❌ 评论区里没有这条内容")
                    for c in comments[:5]:
                        print("   · %s" % c[:60])
        finally:
            try:
                await browser.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    cnt = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    sys.exit(asyncio.run(main(cnt)))
