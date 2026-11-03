"""核对：打开指定帖子，检查评论区里是否出现我们发的内容。"""
import asyncio, os, sys
from playwright.async_api import async_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".chrome-xhs")
POST_ID = sys.argv[1] if len(sys.argv) > 1 else "6ae804f4000000001200d184"
PROBE = sys.argv[2] if len(sys.argv) > 2 else "流量不够用真的太烦人了"


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            USER_DATA_DIR, channel="chrome", headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        url = "https://www.xiaohongshu.com/explore/%s" % POST_ID
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(5000)
        print("URL:", page.url[:90])

        title = await page.evaluate("() => { const e = document.querySelector('#detail-title'); return e ? e.innerText.trim() : ''; }")
        print("标题:", title[:50] or "(空)")
        print("正文前60:", (await page.evaluate("() => { const e=document.querySelector('#detail-desc'); return e?e.innerText.trim():''; }"))[:60])

        found = await page.evaluate("(t) => (document.body.innerText||'').includes(t)", PROBE)
        print("\n评论区包含我们的回复:", "是 ✅" if found else "否 ❌")

        # dump 评论区前几条评论的文本
        comments = await page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('.comment-item, [class*="comment-item"]').forEach(e => {
            const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
            if (t) out.push(t.slice(0, 60));
          });
          return out.slice(0, 6);
        }""")
        print("\n评论列表（前6条）:")
        for c in comments:
            print(" -", c)

        await page.screenshot(path=".debug_verify.png")
        print("\n截图: .debug_verify.png")
        await ctx.close()


asyncio.run(main())
