"""知识库维护菜单 + 单篇重建 + 外挂文档源文件提示。"""
from playwright.sync_api import sync_playwright

errs = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1500, "height": 900})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.goto("http://127.0.0.1:5173/#/kb", wait_until="networkidle")
    pg.wait_for_timeout(1500)

    pg.get_by_role("button", name="维护").click()
    pg.wait_for_timeout(400)
    items = pg.locator(".el-dropdown-menu__item")
    print("维护项:")
    for i in range(items.count()):
        print("  -", items.nth(i).inner_text().replace("\n", " "))
    pg.screenshot(path="docs/_kb_edit_9_menu.png")

    # 点「重建本篇」
    pg.locator(".el-dropdown-menu__item", has_text="重建本篇").click()
    pg.wait_for_timeout(3500)
    print("单篇重建提示:", pg.locator(".el-message").last.inner_text())

    # 切到外挂 md 文档，看源文件标签与编辑提示
    pg.locator(".doc-item", has_text="客户常见问题").first.click()
    pg.wait_for_timeout(1200)
    tags = pg.locator(".doc-head .el-tag").all_inner_texts()
    print("文档头标签:", tags)
    pg.get_by_role("button", name="修改正文").click()
    pg.wait_for_timeout(600)
    print("编辑提示:", pg.locator(".editor-foot").inner_text().replace("\n", " "))
    pg.screenshot(path="docs/_kb_edit_10_md_doc.png")

    print("页面错误:", errs or "无")
    b.close()
