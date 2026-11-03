"""页面布局抖动审计：打开前端页面，隔一段时间采样关键元素的位置/尺寸，
把"跳来跳去"量化出来。只读，不点任何按钮。

用法：
    python dev_tools/audit_layout.py            # 默认审计 /#/xhs
    python dev_tools/audit_layout.py /#/ask
"""
import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:5173/" + (sys.argv[1].lstrip("/") if len(sys.argv) > 1 else "#/xhs")

# 采样的选择器 -> 好读的名字
TARGETS = {
    "main": "main.main",
    "页面根": ".main > div",
    "第一张卡片": ".main .el-card",
    "统计行": ".stat-row",
    "两列卡片": ".two-col",
    "回复表格": ".main .el-table",
    "页脚卡片": ".main .el-card:last-of-type",
}


def sample(page):
    out = {}
    for name, sel in TARGETS.items():
        el = page.query_selector(sel)
        if not el:
            out[name] = None
            continue
        box = el.bounding_box()
        out[name] = None if not box else (round(box["y"], 1), round(box["height"], 1))
    out["scrollHeight"] = page.evaluate("document.querySelector('main.main').scrollHeight")
    out["scrollTop"] = page.evaluate("document.querySelector('main.main').scrollTop")
    return out


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path="dev_tools/_layout_top.png")

        frames = []
        for i in range(8):
            frames.append((i, sample(page)))
            page.wait_for_timeout(1200)

        keys = list(TARGETS.keys()) + ["scrollHeight", "scrollTop"]
        print(f"页面: {URL}   采样间隔 1.2s × 8\n")
        header = "采样  " + "  ".join(f"{k}(y/h)" if k in TARGETS else k for k in keys)
        print(header)
        for i, s in frames:
            cells = []
            for k in keys:
                v = s.get(k)
                if v is None:
                    cells.append("—")
                elif isinstance(v, tuple):
                    cells.append(f"{v[0]}/{v[1]}")
                else:
                    cells.append(str(v))
            print(f"{i:>3}   " + "  ".join(cells))

        # 汇总：哪些元素在不同采样之间发生过位移
        print("\n位移汇总（同一元素多次采样间 y 或 h 的最大差值）:")
        any_jump = False
        for k in keys:
            vals = [s[k] for _, s in frames if s.get(k) is not None]
            if not vals:
                continue
            if isinstance(vals[0], tuple):
                dy = max(v[0] for v in vals) - min(v[0] for v in vals)
                dh = max(v[1] for v in vals) - min(v[1] for v in vals)
                if dy or dh:
                    any_jump = True
                    print(f"  {k}: 位置差 {dy:+.1f}px  高度差 {dh:+.1f}px")
            else:
                dv = max(vals) - min(vals)
                if dv:
                    any_jump = True
                    print(f"  {k}: 变化 {dv}")
        if not any_jump:
            print("  无抖动")

        browser.close()


if __name__ == "__main__":
    main()
