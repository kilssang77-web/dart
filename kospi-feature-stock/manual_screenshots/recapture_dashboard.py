import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

SCREENSHOT_DIR = "D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots"


async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        try:
            await page.goto("http://localhost:8000/", wait_until="commit", timeout=20000)
            await page.wait_for_timeout(4000)
            await page.screenshot(
                path=f"{SCREENSHOT_DIR}/01_dashboard.png",
                full_page=True,
            )
            print("OK: 01_dashboard")
        except Exception as e:
            print(f"FAIL: 01_dashboard - {e}")

        await browser.close()


asyncio.run(capture())
