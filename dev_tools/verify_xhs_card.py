"""小红书已回记录表：验证「推荐卡 / 客户下单链接」列渲染。"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 950})
    errs, console = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: console.append(m.type + ": " + m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:5173/#/xhs", wait_until="networkidle")
    pg.wait_for_timeout(2500)

    # 找到「推荐卡」这一列的第 1 行单元格
    cell = pg.locator("td").filter(has=pg.locator(".rec-name")).first
    if cell.count() == 0:
        print("!! 没找到 .rec-name（推荐卡名未渲染）")
    else:
        print("卡名:", cell.locator(".rec-name").inner_text())
        print("摘要:", cell.locator(".rec-meta span").first.inner_text())
        link = cell.locator(".rec-link")
        print("链接文案:", link.inner_text())
        print("链接 href:", link.get_attribute("href"))
        bb = cell.bounding_box()
        print("单元格高:", round(bb["height"], 1), "宽:", round(bb["width"], 1))

    # 表头文字
    heads = [pg.locator("th").nth(i).inner_text() for i in range(pg.locator("th").count())]
    print("表头:", [h for h in heads if h][:12])

    # 取这张表的截图（只截表格所在卡片）
    card = pg.locator(".el-table").first
    card.screenshot(path="docs/_xhs_card_col.png")
    pg.screenshot(path="docs/_xhs_page.png", full_page=False)
    print("console 错误:", console or "无")
    print("页面错误:", errs or "无")
    b.close()
