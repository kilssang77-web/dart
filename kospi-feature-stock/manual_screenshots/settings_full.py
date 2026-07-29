# -*- coding: utf-8 -*-
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8000'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # 실제 브라우저로 확인
    page = browser.new_page(viewport={'width': 1440, 'height': 900})

    # 로그인
    page.goto(f'{BASE}/login', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'ChangeMe123!')
    page.click('button[type=submit]')
    page.wait_for_selector('button:has-text("로그아웃")', timeout=8000)
    time.sleep(1)

    # 설정 페이지로 이동
    page.goto(f'{BASE}/settings', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)

    # 페이지 전체 높이 확인
    total_height = page.evaluate('document.body.scrollHeight')
    print(f'페이지 전체 높이: {total_height}px')

    # 비밀번호 변경 카드 위치로 스크롤
    pw_card = page.locator('text=비밀번호 변경').first
    pw_card.scroll_into_view_if_needed()
    time.sleep(0.5)

    # 비밀번호 변경 카드 영역 캡처
    page.screenshot(
        path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/settings_pw_section.png',
        full_page=False
    )
    print('비밀번호 변경 카드 캡처 완료')

    # 설정 페이지 상단부터 캡처
    page.evaluate('window.scrollTo(0, 0)')
    time.sleep(0.5)
    page.screenshot(
        path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/settings_top.png',
        full_page=False
    )
    print('설정 페이지 상단 캡처 완료')

    browser.close()
