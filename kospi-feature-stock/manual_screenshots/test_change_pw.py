# -*- coding: utf-8 -*-
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8000'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})

    # 로그인
    page.goto(f'{BASE}/login', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'ChangeMe123!')
    page.click('button[type=submit]')
    page.wait_for_selector('button:has-text("로그아웃")', timeout=8000)
    time.sleep(1)

    # 설정 페이지 이동
    page.goto(f'{BASE}/settings', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)

    # 비밀번호 변경 카드 스크롤 위치로 이동
    card = page.locator('text=비밀번호 변경').first
    card.scroll_into_view_if_needed()
    time.sleep(0.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/change_pw_card.png')
    print('설정 페이지 캡처 완료')

    # ── 오류 케이스: 현재 비밀번호 틀림 ───────────────────────────────────────
    inputs = page.locator('input[type=password], input[type=text]')
    pw_inputs = page.locator('form input')
    pw_inputs.nth(0).fill('WrongPassword!')
    pw_inputs.nth(1).fill('NewPass456!')
    pw_inputs.nth(2).fill('NewPass456!')
    page.locator('form button[type=submit]').click()
    time.sleep(2)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/change_pw_error.png')
    print('오류 케이스 캡처 완료')

    # ── 성공 케이스: 올바른 현재 비밀번호 → 변경 → 새 비밀번호로 재로그인 ────
    pw_inputs.nth(0).fill('ChangeMe123!')
    pw_inputs.nth(1).fill('NewPass456!')
    pw_inputs.nth(2).fill('NewPass456!')
    page.locator('form button[type=submit]').click()
    time.sleep(2)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/change_pw_success.png')
    print('성공 케이스 캡처 완료')

    # ── 새 비밀번호로 재로그인 확인 ────────────────────────────────────────────
    page.locator('button:has-text("로그아웃")').click()
    time.sleep(1)
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'NewPass456!')
    page.click('button[type=submit]')
    page.wait_for_selector('button:has-text("로그아웃")', timeout=8000)
    print('새 비밀번호로 재로그인 성공')

    # ── 원래 비밀번호로 복원 ────────────────────────────────────────────────────
    page.goto(f'{BASE}/settings', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)
    pw_inputs2 = page.locator('form input')
    pw_inputs2.nth(0).fill('NewPass456!')
    pw_inputs2.nth(1).fill('ChangeMe123!')
    pw_inputs2.nth(2).fill('ChangeMe123!')
    page.locator('form button[type=submit]').click()
    time.sleep(2)
    print('원래 비밀번호 복원 완료')

    browser.close()
