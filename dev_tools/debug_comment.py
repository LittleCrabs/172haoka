"""探针：打开首页第一条帖子，dump 评论输入框的真实 DOM 结构。"""
import asyncio, json, os
from playwright.async_api import async_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".chrome-xhs")

JS = """() => {
  const out = {editables: [], placeholder: [], submitBtns: []};
  const describe = (e) => {
    const r = e.getBoundingClientRect();
    return {
      tag: e.tagName,
      id: e.id || '',
      cls: (e.className && typeof e.className === 'string') ? e.className.slice(0, 80) : '',
      ph: e.getAttribute('placeholder') || e.getAttribute('data-placeholder') || '',
      text: (e.innerText || '').slice(0, 30),
      visible: r.width > 0 && r.height > 0,
    };
  };
  document.querySelectorAll("[contenteditable='true'], textarea, input[type='text']").forEach(e => {
    out.editables.push(describe(e));
  });
  document.querySelectorAll("*").forEach(e => {
    if (e.children.length === 0 && /说点什么/.test(e.textContent || '')) {
      out.placeholder.push(describe(e));
    }
  });
  document.querySelectorAll("button, .submit, [class*='submit']").forEach(e => {
    const t = (e.innerText || '').trim();
    if (/发送|评论/.test(t) || /submit/i.test(e.className || '')) out.submitBtns.push(describe(e));
  });
  const cc = document.querySelector("[class*='comments-container'], [class*='comment-container'], .comments-el, [class*='note-scroller']");
  out.commentsContainer = cc ? {cls: String(cc.className).slice(0, 100), childCount: cc.children.length} : null;
  return out;
}"""


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            USER_DATA_DIR, channel="chrome", headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(4500)

        items = page.locator("section.note-item, div.note-item")
        print("卡片数:", await items.count())
        await items.nth(0).scroll_into_view_if_needed(timeout=5000)
        await items.nth(0).click()
        await page.wait_for_timeout(4000)
        print("URL:", page.url[:70])

        info = await page.evaluate(JS)
        print("\n--- contenteditable/textarea ---")
        for e in info["editables"]:
            print(json.dumps(e, ensure_ascii=False))
        print("\n--- 「说点什么」节点 ---")
        for e in info["placeholder"]:
            print(json.dumps(e, ensure_ascii=False))
        print("\n--- 发送按钮候选 ---")
        for e in info["submitBtns"]:
            print(json.dumps(e, ensure_ascii=False))
        print("\n--- 评论容器 ---", json.dumps(info["commentsContainer"], ensure_ascii=False))

        # 点击「说点什么」后再看一次
        trig = page.locator("span:has-text('说点什么')").first
        try:
            if await trig.count() > 0:
                await trig.click(timeout=3000)
                await page.wait_for_timeout(1200)
                print("\n=== 点击「说点什么」之后 ===")
                info2 = await page.evaluate(JS)
                for e in info2["editables"]:
                    print("ED:", json.dumps(e, ensure_ascii=False))
                for e in info2["submitBtns"]:
                    print("BTN:", json.dumps(e, ensure_ascii=False))
        except Exception as e:
            print("点击失败:", str(e)[:120])

        await page.screenshot(path=".debug_comment_box.png")
        print("\n截图: .debug_comment_box.png")
        await ctx.close()


asyncio.run(main())
