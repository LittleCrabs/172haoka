#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二次探针：精确摸清评论输入框与地区文本格式。"""
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
        await page.wait_for_timeout(4500)
        await page.locator("section.note-item, div.note-item").first.click()
        await page.wait_for_timeout(4000)

        out = await page.evaluate("""() => {
            const res = {contenteditable: [], textarea: [], placeholders: [], date_region: []};
            document.querySelectorAll('[contenteditable="true"]').forEach(e => {
                res.contenteditable.push({
                    id: e.id || '', cls: (e.className || '').slice(0, 70),
                    ph: e.getAttribute('data-placeholder') || e.getAttribute('placeholder') || '',
                    visible: !!e.offsetParent,
                    text: (e.innerText || '').slice(0, 20)
                });
            });
            document.querySelectorAll('textarea').forEach(e => {
                res.textarea.push({id: e.id || '', cls: (e.className || '').slice(0, 60),
                                   ph: e.placeholder || '', visible: !!e.offsetParent});
            });
            // 找「说点什么」提示元素
            [...document.querySelectorAll('*')].forEach(e => {
                if (e.children.length === 0) {
                    const t = (e.textContent || '').trim();
                    if (t && t.length < 15 && /说点什么|发布你的评论|评论/.test(t) && res.placeholders.length < 6) {
                        res.placeholders.push({tag: e.tagName, cls: (e.className || '').slice(0, 60), text: t});
                    }
                }
            });
            // 时间/地区行：形如 "34分钟前 天津" / "编辑于 3天前 江苏"
            [...document.querySelectorAll('[class*="date"], [class*="time"], .bottom-container')].slice(0, 6).forEach(e => {
                res.date_region.push({cls: (e.className || '').slice(0, 50), text: (e.innerText || '').trim().slice(0, 40)});
            });
            // 发送按钮
            const send = [...document.querySelectorAll('button, div, span')].find(
                e => e.children.length === 0 && (e.textContent || '').trim() === '发送' && e.offsetParent);
            res.send_btn = send ? {tag: send.tagName, cls: (send.className || '').slice(0, 60)} : null;
            return res;
        }""")
        print(json.dumps(out, ensure_ascii=False, indent=1)[:2500])
        await b.close()


asyncio.run(main())
