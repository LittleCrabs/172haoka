"""知识库工具栏：一行放得下 + 维护下拉可用。"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1500, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5173/#/kb", wait_until="networkidle")
    pg.wait_for_timeout(1500)

    tb = pg.locator(".toolbar")
    box = tb.bounding_box()
    # 工具栏高度 ≈ 一个按钮高（32~40），说明没折行
    print("工具栏高度:", round(box["height"], 1))

    pg.get_by_role("button", name="维护").click()
    pg.wait_for_timeout(500)
    items = pg.locator(".el-dropdown-menu__item")
    print("下拉项:", [items.nth(i).inner_text().replace("\n", " ") for i in range(items.count())])
    print("提示色:", pg.evaluate(
        "() => { const e=document.querySelector('.dd-hint');"
        " return e ? getComputedStyle(e).color + '/' + getComputedStyle(e).fontSize : 'missing' }"))
    pg.screenshot(path="docs/_kb_edit_7_dropdown.png")

    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    pg.get_by_role("button", name="修改正文").click()
    pg.wait_for_timeout(600)
    b2 = pg.locator(".toolbar").bounding_box()
    print("编辑态工具栏高度:", round(b2["height"], 1))
    pg.screenshot(path="docs/_kb_edit_8_toolbar_edit.png")
    print("页面错误:", errs or "无")
    b.close()
