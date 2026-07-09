import asyncio, sys
from playwright.async_api import async_playwright
sys.stdout.reconfigure(encoding='utf-8')

SHOT = "D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1) 대시보드 로드
        await page.goto("http://localhost:8000/", wait_until="commit", timeout=20000)
        await page.wait_for_timeout(5000)
        await page.screenshot(path=f"{SHOT}/topbar_with_manual_btn.png")
        print("OK: topbar screenshot")

        # 2) 매뉴얼 버튼 클릭 - JS로 BookOpen SVG가 있는 버튼 클릭
        clicked = await page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            for (const b of buttons) {
                if (b.title && b.title.includes('매뉴얼')) {
                    b.click(); return 'clicked: ' + b.title;
                }
            }
            // fallback: BookOpen SVG path 검색
            for (const b of buttons) {
                const svg = b.querySelector('svg');
                if (svg && b.closest('header')) {
                    const allBtns = [...document.querySelectorAll('header button')];
                    const lastBtn = allBtns[allBtns.length - 1];
                    lastBtn.click();
                    return 'clicked last header button';
                }
            }
            return 'not found, total buttons: ' + buttons.length;
        }""")
        print(f"click result: {clicked}")
        await page.wait_for_timeout(6000)
        await page.screenshot(path=f"{SHOT}/manual_modal_open.png", full_page=False)
        print("OK: manual modal screenshot")

        # 3) manual.html 단독
        page2 = await ctx.new_page()
        await page2.goto("http://localhost:8000/manual.html", wait_until="commit", timeout=20000)
        await page2.wait_for_timeout(4000)
        await page2.screenshot(path=f"{SHOT}/manual_standalone.png")
        print("OK: manual standalone screenshot")

        await browser.close()

asyncio.run(run())
