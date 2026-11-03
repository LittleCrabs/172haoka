"""知识库就地编辑：端到端验证（选文档 → 修改正文 → 保存 → 分块与向量同步）。"""
import re
import sys

from playwright.sync_api import sync_playwright

SHOT = "docs/_kb_edit_{}.png"
errors, bad = [], []


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
        pg.on("console", lambda m: m.type == "error" and errors.append("console: %s" % m.text))
        pg.on("response", lambda r: r.status >= 400 and bad.append("%s %s" % (r.status, r.url)))

        pg.goto("http://127.0.0.1:5173/#/kb", wait_until="networkidle")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=SHOT.format("1_read"), full_page=False)

        # 1) 默认应是全文视图，且已自动选中第一篇
        head = pg.locator(".doc-head-title").inner_text()
        full = pg.locator(".doc-full").inner_text()
        print("默认文档:", head, "| 全文字数:", len(full))

        # 2) 点「修改正文」进入编辑态
        pg.get_by_role("button", name="修改正文").click()
        pg.wait_for_timeout(400)
        ta = pg.locator(".doc-editor textarea")
        assert ta.count() == 1, "编辑框没出现"
        before = ta.input_value()
        print("编辑框载入字数:", len(before))
        pg.screenshot(path=SHOT.format("2_edit"))

        # 3) 追加一句话并保存
        marker = "\n\n【自测】就地编辑保存链路验证。"
        ta.click()
        ta.press("Control+End")
        ta.type(marker)
        pg.get_by_role("button", name="保存并重建").click()
        pg.wait_for_timeout(2500)
        full2 = pg.locator(".doc-full").inner_text()
        ok_saved = "【自测】就地编辑保存链路验证。" in full2
        print("保存后全文含标记:", ok_saved, "| 字数:", len(full2))

        # 4) 切到分块视图，确认分块也跟着更新
        pg.locator(".el-radio-button", has_text="分块").first.click()
        pg.wait_for_timeout(600)
        chunks = pg.locator(".chunk").count()
        tail = pg.locator(".chunk-text").last.inner_text()
        print("分块数:", chunks, "| 末段含标记:", "【自测】" in tail)
        pg.screenshot(path=SHOT.format("3_chunks"))

        # 5) 回滚：重新进入编辑，删掉标记后保存
        pg.locator(".el-radio-button", has_text="全文").first.click()
        pg.wait_for_timeout(300)
        pg.get_by_role("button", name="修改正文").click()
        pg.wait_for_timeout(400)
        ta = pg.locator(".doc-editor textarea")
        fixed = ta.input_value().replace(marker, "")
        ta.fill(fixed)
        pg.get_by_role("button", name="保存并重建").click()
        pg.wait_for_timeout(2200)
        full3 = pg.locator(".doc-full").inner_text()
        print("回滚后仍含标记:", "【自测】" in full3, "| 字数:", len(full3))
        pg.screenshot(path=SHOT.format("4_reverted"))

        # 6) 未保存改动切文档应弹确认
        pg.get_by_role("button", name="修改正文").click()
        pg.wait_for_timeout(300)
        pg.locator(".doc-editor textarea").type("x")
        items = pg.locator(".doc-item")
        if items.count() > 1:
            items.nth(1).click()
            pg.wait_for_timeout(600)
            dialog = pg.locator(".el-message-box").count()
            print("切换拦截弹窗:", dialog > 0)
            if dialog:
                pg.get_by_role("button", name="继续编辑").click()
                pg.wait_for_timeout(300)
        pg.screenshot(path=SHOT.format("5_dirty_guard"))

        # 7) 整理格式：把 OCR 碎片行合并，结果只回填编辑框、不落库
        # 上一步选了「继续编辑」，先退出编辑态
        if pg.get_by_role("button", name="取消").count():
            pg.get_by_role("button", name="取消").click()
            pg.wait_for_timeout(400)
            if pg.locator(".el-message-box").count():
                pg.get_by_role("button", name="放弃").click()
                pg.wait_for_timeout(400)
        pg.locator(".doc-item").first.click()
        pg.wait_for_timeout(500)
        if pg.locator(".el-message-box").count():
            pg.get_by_role("button", name="放弃并切换").click()
            pg.wait_for_timeout(600)
        pg.get_by_role("button", name="修改正文").click()
        pg.wait_for_timeout(400)
        ta = pg.locator(".doc-editor textarea")
        raw = ta.input_value()
        pg.get_by_role("button", name="整理格式").click()
        pg.wait_for_timeout(1500)
        tidied = ta.input_value()
        print("整理格式生效:", tidied != raw, "|", len(raw), "->", len(tidied))
        print("碎片已合并为一行:", "今8 · 15:54" in tidied)
        pg.screenshot(path=SHOT.format("6_tidy"))
        pg.get_by_role("button", name="取消").click()
        pg.wait_for_timeout(400)
        if pg.locator(".el-message-box").count():
            pg.get_by_role("button", name="放弃").click()
            pg.wait_for_timeout(300)
        b.close()

    print("\n页面错误:", errors or "无")
    print("HTTP>=400:", bad or "无")


if __name__ == "__main__":
    sys.exit(main())
