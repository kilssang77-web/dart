# -*- coding: utf-8 -*-
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8000'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})

    # 로그인
    page.goto(f'{BASE}/login', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'ChangeMe123!')
    page.click('button[type=submit]')
    page.wait_for_selector('button:has-text("로그아웃")', timeout=8000)
    time.sleep(1)

    # 계정 관리 페이지 이동
    page.goto(f'{BASE}/account', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)

    # 전체 페이지 (상단)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/account_top.png')
    print('계정 관리 상단 캡처 완료')

    # 사용자 관리 카드로 스크롤
    page.locator('text=사용자 관리').first.scroll_into_view_if_needed()
    time.sleep(0.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/account_users.png')
    print('사용자 관리 카드 캡처 완료')

    # 사용자 추가 모달 열기
    page.click('button:has-text("사용자 추가")')
    time.sleep(0.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/account_add_modal.png')
    print('사용자 추가 모달 캡처 완료')

    # 모달에서 신규 사용자 입력
    inputs = page.locator('.fixed input')
    inputs.nth(0).fill('testuser')
    inputs.nth(1).fill('테스트 사용자')
    inputs.nth(2).fill('Test1234!')
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/account_add_filled.png')
    print('모달 입력 후 캡처 완료')

    # 추가 실행
    page.locator('.fixed button:has-text("추가")').click()
    time.sleep(1.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/account_after_add.png')
    print('사용자 추가 후 목록 캡처 완료')

    browser.close()
