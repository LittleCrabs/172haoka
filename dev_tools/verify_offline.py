#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证「连不上后端 → 页面给出提示，且提示不推挤布局」这条链路。

跑法（需要后端 8123 与前端 5173 都在）：
    backend/.venv/Scripts/python.exe dev_tools/verify_offline.py

用浏览器的离线模式模拟断网，不去杀后端进程 —— 这样跑测试不会打断正在执行的任务。

做四件事：
  1. 打开 #/xhs，确认页面正常渲染、无 JS 报错、无断连提示
  2. 切到离线，等 24 秒，确认提示出现（而不是页面静默不动）
  3. 确认提示出现时内容区顶部位置没变（提示是悬浮的，不能把内容顶下去）
  4. 恢复在线，等 14 秒，确认提示自动消失

注意：提示要求连续两次健康检查失败才出现（避免偶发超时闪一下），
健康检查每 10 秒一次，所以断开后最多要约 20 秒才会弹。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT = "http://127.0.0.1:5173/#/xhs"
MAIN_TOP_OK = 60          # topbar 高度，提示悬浮时内容区顶部应始终是这个值


def main():
    from playwright.sync_api import sync_playwright

    errors = []
    ok = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))

        page.goto(FRONT, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        toast = page.locator(".offline-toast")
        title = page.locator(".page-title").inner_text()
        top0 = page.evaluate("() => document.querySelector('.main').getBoundingClientRect().top")
        print("1) 页面标题:", title)
        print("   断连提示:", "有（异常）" if toast.count() else "无（正确）")
        print("   内容区顶部:", top0)
        print("   JS 报错:", errors or "无")
        page.screenshot(path=str(ROOT / "dev_tools" / "_offline_1_ok.png"))

        # ---- 断网 ----
        ctx.set_offline(True)
        print("\n2) 已切换到离线，等 24 秒看提示…")
        page.wait_for_timeout(24000)
        page.screenshot(path=str(ROOT / "dev_tools" / "_offline_2_down.png"))
        cnt = toast.count()
        txt = toast.first.inner_text().replace("\n", " ") if cnt else ""
        print("   断连提示:", ("出现 → %s" % txt) if cnt else "没出现（失败）")

        top1 = page.evaluate("() => document.querySelector('.main').getBoundingClientRect().top")
        print("   内容区顶部:", top1, "（应与之前一致，否则说明提示又占了文档流）")

        # ---- 恢复 ----
        ctx.set_offline(False)
        print("\n3) 已恢复在线，等 14 秒…")
        page.wait_for_timeout(14000)
        cnt2 = toast.count()
        print("   提示已消失:", "是（正确）" if cnt2 == 0 else "否（仍是断连状态）")
        page.screenshot(path=str(ROOT / "dev_tools" / "_offline_3_back.png"))

        ok = cnt == 1 and cnt2 == 0 and top0 == top1 == MAIN_TOP_OK
        browser.close()

    print("\n结论:", "通过" if ok else "未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
