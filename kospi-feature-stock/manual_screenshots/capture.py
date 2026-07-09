import asyncio
import sys
from playwright.async_api import async_playwright
import os

sys.stdout.reconfigure(encoding='utf-8')

SCREENSHOT_DIR = "D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        pages_to_capture = [
            ("01_dashboard", "http://localhost:8000/"),
            ("02_features", "http://localhost:8000/features"),
            ("03_recommendations", "http://localhost:8000/recommendations"),
            ("04_stock_search", "http://localhost:8000/search"),
            ("05_performance_tracking", "http://localhost:8000/tracking"),
            ("06_model_performance", "http://localhost:8000/model"),
            ("07_screener", "http://localhost:8000/screener"),
            ("08_backtest", "http://localhost:8000/backtest"),
            ("09_system_health", "http://localhost:8000/health-dashboard"),
            ("10_intel", "http://localhost:8000/intel"),
            ("11_trader", "http://localhost:8000/trader"),
            ("12_watchlist", "http://localhost:8000/watchlist"),
            ("13_notifications", "http://localhost:8000/notifications"),
            ("14_ranking", "http://localhost:8000/ranking"),
            ("15_settings", "http://localhost:8000/settings"),
        ]

        for name, url in pages_to_capture:
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await page.wait_for_timeout(2500)
                await page.screenshot(
                    path=f"{SCREENSHOT_DIR}/{name}.png",
                    full_page=True,
                )
                print(f"OK: {name}")
            except Exception as e:
                # Fallback: try DOMContentLoaded
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(3000)
                    await page.screenshot(
                        path=f"{SCREENSHOT_DIR}/{name}.png",
                        full_page=True,
                    )
                    print(f"OK(fallback): {name}")
                except Exception as e2:
                    print(f"FAIL: {name} - {e2}")

        await browser.close()


asyncio.run(capture())
