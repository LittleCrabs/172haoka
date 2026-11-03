#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性 DOM 探针：摸清小红书首页信息流的卡片 / 详情 / 评论框结构。"""
import asyncio
import os
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch_persistent_context(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".chrome-xhs"),
            channel="chrome", headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"])
        page = b.pages[0] if b.pages else await b.new_page()
        await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(5000)

        print("== 首页 URL:", page.url[:90])
        info = await page.evaluate("""() => {
            const sels = {
                'a_explore': 'a[href*="/explore/"]',
                'note_item': 'section.note-item, div.note-item',
                'cover': '[class*="cover"]',
            };
            const out = {counts: {}, samples: []};
            for (const [k, s] of Object.entries(sels)) out.counts[k] = document.querySelectorAll(s).length;
            const links = [...document.querySelectorAll('a[href*="/explore/"]')].slice(0, 4);
            out.samples = links.map(a => ({href: a.getAttribute('href').slice(0, 140)}));
            return out;
        }""")
        print("== 卡片统计:", json.dumps(info, ensure_ascii=False, indent=1)[:900])

        # 点击第一张卡片（点封面，不点空 a 标签），看详情弹层结构
        card = page.locator('section.note-item, div.note-item').first
        if await card.count() > 0:
            await card.click()
            await page.wait_for_timeout(4500)
            print("== 点击后 URL:", page.url[:110])
            detail = await page.evaluate("""() => {
                const out = {};
                for (const sel of ['#detail-desc', '.note-text', '.desc', '#detail-title',
                                   '.note-content', '[class*="note-content"]', '[class*="desc"]']) {
                    const e = document.querySelector(sel);
                    out[sel] = e ? (e.innerText || '').slice(0, 80) : null;
                }
                const ipEl = [...document.querySelectorAll('*')].find(
                    e => e.children.length === 0 && /IP\\s*属地/.test(e.textContent || ''));
                out.ip = ipEl ? ipEl.textContent.trim().slice(0, 30) : null;
                out.modal = !!document.querySelector('[class*="note-detail"], [id*="detail"]');
                // 评论输入框候选
                const box = document.querySelector('#post-textarea')
                    || document.querySelector('div[contenteditable="true"]')
                    || document.querySelector('textarea');
                out.comment_box = box ? (box.id || box.className || box.tagName).slice(0, 60) : null;
                // 正文整体文本（兜底）
                const nm = document.querySelector('[class*="note-scroller"], .note-container');
                out.container_text = nm ? (nm.innerText || '').slice(0, 200) : null;
                return out;
            }""")
            print("== 详情结构:", json.dumps(detail, ensure_ascii=False, indent=1)[:1400])
        await b.close()


asyncio.run(main())
