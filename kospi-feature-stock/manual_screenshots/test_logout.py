# -*- coding: utf-8 -*-
import sys, time
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 800})

    # 1) 로그인
    page.goto('http://127.0.0.1:8000/login', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'ChangeMe123!')
    page.click('button[type=submit]')

    # SPA 클라이언트 라우팅: 로그아웃 버튼이 나타날 때까지 대기
    page.wait_for_selector('button:has-text("로그아웃")', timeout=8000)
    time.sleep(1)
    print('대시보드 진입 확인, URL:', page.url)

    # 2) 로그아웃 클릭
    page.click('button:has-text("로그아웃")')
    time.sleep(2)
    print('로그아웃 후 URL:', page.url)

    # 3) 로그아웃 후 화면 캡처
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/after_logout.png')
    print('캡처 완료')
    browser.close()
