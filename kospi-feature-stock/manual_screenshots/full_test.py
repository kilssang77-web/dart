# -*- coding: utf-8 -*-
"""계정 관리 전수 테스트 — API + UI"""
import sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
import requests
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8000'
PASS = {'results': [], 'fails': []}

def ok(name):
    PASS['results'].append(f'  [PASS] {name}')
    print(f'  [PASS] {name}')

def fail(name, reason=''):
    PASS['fails'].append(f'  [FAIL] {name}: {reason}')
    print(f'  [FAIL] {name}: {reason}')

# ══════════════════════════════════════════════════════
# 1. API 직접 테스트
# ══════════════════════════════════════════════════════
print('\n[1] API 직접 테스트')

# 1-1. 로그인 성공
r = requests.post(f'{BASE}/api/v1/auth/login', json={'username':'admin','password':'ChangeMe123!'})
if r.status_code == 200 and 'access_token' in r.json():
    TOKEN = r.json()['access_token']
    ok('로그인 성공 (200)')
else:
    fail('로그인 성공', f'status={r.status_code}'); TOKEN=''

H = {'Authorization': f'Bearer {TOKEN}'}

# 1-2. 로그인 실패 (틀린 비밀번호)
r = requests.post(f'{BASE}/api/v1/auth/login', json={'username':'admin','password':'WrongPass'})
if r.status_code == 401:
    ok('로그인 실패 — 틀린 비밀번호 (401)')
else:
    fail('로그인 실패', f'status={r.status_code}')

# 1-3. 토큰 없이 API 접근 → 401
r = requests.get(f'{BASE}/api/v1/auth/users')
if r.status_code == 401:
    ok('미인증 접근 차단 (401)')
else:
    fail('미인증 접근 차단', f'status={r.status_code}')

# 1-4. 사용자 목록 조회
r = requests.get(f'{BASE}/api/v1/auth/users', headers=H)
if r.status_code == 200 and isinstance(r.json(), list):
    users_before = r.json()
    ok(f'사용자 목록 조회 (200) — {len(users_before)}명')
else:
    fail('사용자 목록 조회', f'status={r.status_code}')
    users_before = []

# 1-5. 사용자 추가
r = requests.post(f'{BASE}/api/v1/auth/users', headers=H,
    json={'username':'testapi','password':'ApiTest123!','display_name':'API테스트'})
if r.status_code == 201 and r.json().get('username') == 'testapi':
    ok('사용자 추가 (201)')
else:
    fail('사용자 추가', f'status={r.status_code} body={r.text[:80]}')

# 1-6. 중복 아이디 추가 → 400
r = requests.post(f'{BASE}/api/v1/auth/users', headers=H,
    json={'username':'testapi','password':'ApiTest123!'})
if r.status_code == 400:
    ok('중복 아이디 거부 (400)')
else:
    fail('중복 아이디 거부', f'status={r.status_code}')

# 1-7. 비밀번호 8자 미만 → 422
r = requests.post(f'{BASE}/api/v1/auth/users', headers=H,
    json={'username':'shortpw','password':'abc'})
if r.status_code == 422:
    ok('짧은 비밀번호 거부 (422)')
else:
    fail('짧은 비밀번호 거부', f'status={r.status_code}')

# 1-8. 사용자 수정 (표시이름 변경)
r = requests.put(f'{BASE}/api/v1/auth/users/testapi', headers=H,
    json={'display_name':'수정된이름'})
if r.status_code == 200 and r.json().get('display_name') == '수정된이름':
    ok('사용자 수정 — 표시이름 (200)')
else:
    fail('사용자 수정', f'status={r.status_code}')

# 1-9. 비활성화
r = requests.put(f'{BASE}/api/v1/auth/users/testapi', headers=H,
    json={'is_active': False})
if r.status_code == 200 and r.json().get('is_active') == False:
    ok('사용자 비활성화 (200)')
else:
    fail('사용자 비활성화', f'status={r.status_code}')

# 1-10. 비활성 계정 로그인 불가
r = requests.post(f'{BASE}/api/v1/auth/login', json={'username':'testapi','password':'ApiTest123!'})
if r.status_code == 401:
    ok('비활성 계정 로그인 차단 (401)')
else:
    fail('비활성 계정 로그인 차단', f'status={r.status_code}')

# 1-11. 재활성화
r = requests.put(f'{BASE}/api/v1/auth/users/testapi', headers=H, json={'is_active': True})
if r.status_code == 200 and r.json().get('is_active') == True:
    ok('사용자 재활성화 (200)')
else:
    fail('사용자 재활성화', f'status={r.status_code}')

# 1-12. 비밀번호 재설정 (관리자)
r = requests.put(f'{BASE}/api/v1/auth/users/testapi', headers=H,
    json={'new_password':'NewApiPass123!'})
if r.status_code == 200:
    ok('비밀번호 재설정 (200)')
else:
    fail('비밀번호 재설정', f'status={r.status_code}')

# 1-13. 새 비밀번호로 로그인
r = requests.post(f'{BASE}/api/v1/auth/login',
    json={'username':'testapi','password':'NewApiPass123!'})
if r.status_code == 200:
    ok('재설정 비밀번호로 로그인 성공')
else:
    fail('재설정 비밀번호로 로그인', f'status={r.status_code}')

# 1-14. 자신 삭제 방지
r = requests.delete(f'{BASE}/api/v1/auth/users/admin', headers=H)
if r.status_code == 400:
    ok('자신 계정 삭제 방지 (400)')
else:
    fail('자신 계정 삭제 방지', f'status={r.status_code}')

# 1-15. 비밀번호 변경 — 현재 비밀번호 틀림
r = requests.post(f'{BASE}/api/v1/auth/change-password', headers=H,
    json={'current_password':'WRONG','new_password':'NewAdmin123!'})
if r.status_code == 400:
    ok('비밀번호 변경 — 현재 비밀번호 오류 (400)')
else:
    fail('비밀번호 변경 오류 검증', f'status={r.status_code}')

# 1-16. 비밀번호 변경 성공
r = requests.post(f'{BASE}/api/v1/auth/change-password', headers=H,
    json={'current_password':'ChangeMe123!','new_password':'AdminNew123!'})
if r.status_code == 200:
    ok('비밀번호 변경 성공 (200)')
else:
    fail('비밀번호 변경 성공', f'status={r.status_code} {r.text}')

# 1-17. 원래 비밀번호로 복원
r = requests.post(f'{BASE}/api/v1/auth/login',
    json={'username':'admin','password':'AdminNew123!'})
if r.status_code == 200:
    H2 = {'Authorization': f'Bearer {r.json()["access_token"]}'}
    r2 = requests.post(f'{BASE}/api/v1/auth/change-password', headers=H2,
        json={'current_password':'AdminNew123!','new_password':'ChangeMe123!'})
    if r2.status_code == 200:
        ok('비밀번호 복원 완료')
    else:
        fail('비밀번호 복원', f'{r2.status_code}')
else:
    fail('변경된 비밀번호 로그인', f'{r.status_code}')

# 1-18. testapi 삭제
r = requests.delete(f'{BASE}/api/v1/auth/users/testapi', headers=H)
if r.status_code == 204:
    ok('사용자 삭제 (204)')
else:
    fail('사용자 삭제', f'status={r.status_code}')

# 1-19. 삭제 후 없는 사용자 삭제 → 404
r = requests.delete(f'{BASE}/api/v1/auth/users/testapi', headers=H)
if r.status_code == 404:
    ok('없는 사용자 삭제 방지 (404)')
else:
    fail('없는 사용자 삭제 방지', f'status={r.status_code}')

# ══════════════════════════════════════════════════════
# 2. DB 직접 확인
# ══════════════════════════════════════════════════════
print('\n[2] DB 확인 (사용자 목록)')
r = requests.get(f'{BASE}/api/v1/auth/users', headers=H)
if r.status_code == 200:
    users = r.json()
    ok(f'DB 최종 사용자 수: {len(users)}명')
    for u in users:
        print(f'     · {u["username"]} | {u["display_name"]} | is_active={u["is_active"]} | last_login={u["last_login"]}')
else:
    fail('DB 사용자 목록 최종 확인', f'{r.status_code}')

# ══════════════════════════════════════════════════════
# 3. UI 테스트 (Playwright)
# ══════════════════════════════════════════════════════
print('\n[3] UI 테스트 (Playwright)')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})

    # UI-1. 로그인
    page.goto(f'{BASE}/login', wait_until='domcontentloaded', timeout=15000)
    time.sleep(1.5)
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'ChangeMe123!')
    page.click('button[type=submit]')
    try:
        page.wait_for_selector('button:has-text("로그아웃")', timeout=8000)
        ok('UI — 로그인 성공 → 대시보드')
    except:
        fail('UI — 로그인')

    # UI-2. 계정 관리 메뉴 클릭
    page.click('a[href="/account"]')
    time.sleep(1.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/final_account.png')
    if '계정 관리' in page.content():
        ok('UI — 계정 관리 페이지 진입')
    else:
        fail('UI — 계정 관리 페이지')

    # UI-3. 사용자 추가 모달
    page.click('button:has-text("사용자 추가")')
    time.sleep(0.5)
    if page.locator('.fixed input').count() >= 3:
        ok('UI — 사용자 추가 모달 열림')
    else:
        fail('UI — 사용자 추가 모달')

    inputs = page.locator('.fixed input')
    inputs.nth(0).fill('uiuser')
    inputs.nth(1).fill('UI테스터')
    inputs.nth(2).fill('UiPass123!')
    page.locator('.fixed button:has-text("추가")').click()
    time.sleep(1.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/final_user_added.png')
    if page.locator('text=uiuser').count() > 0:
        ok('UI — 사용자 추가 후 목록에 표시')
    else:
        fail('UI — 사용자 추가 확인')

    # UI-4. 활성 토글 (비활성화)
    uiuser_row = page.locator('tr', has=page.locator('text=uiuser'))
    active_btn = uiuser_row.locator('button:has-text("활성")')
    active_btn.click()
    time.sleep(1)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/final_deactivated.png')
    if uiuser_row.locator('button:has-text("비활성")').count() > 0:
        ok('UI — 사용자 비활성화 토글')
    else:
        fail('UI — 비활성화 토글')

    # UI-5. 재활성화
    uiuser_row.locator('button:has-text("비활성")').click()
    time.sleep(1)
    if uiuser_row.locator('button:has-text("활성")').count() > 0:
        ok('UI — 사용자 재활성화 토글')
    else:
        fail('UI — 재활성화 토글')

    # UI-6. 수정 모달
    uiuser_row.locator('button[title="수정"]').click()
    time.sleep(0.5)
    edit_inputs = page.locator('.fixed input')
    edit_inputs.nth(1).fill('UI수정완료')
    page.locator('.fixed button:has-text("저장")').click()
    time.sleep(1.5)
    if page.locator('text=UI수정완료').count() > 0:
        ok('UI — 사용자 표시이름 수정')
    else:
        fail('UI — 표시이름 수정 확인')

    # UI-7. 삭제 확인 모달
    uiuser_row2 = page.locator('tr', has=page.locator('text=uiuser'))
    uiuser_row2.locator('button[title="삭제"]').click()
    time.sleep(0.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/final_delete_confirm.png')
    if page.locator('text=삭제합니다').count() > 0:
        ok('UI — 삭제 확인 모달 표시')
    else:
        fail('UI — 삭제 확인 모달')

    page.locator('button:has-text("삭제")').last.click()
    time.sleep(1.5)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/final_after_delete.png')
    if page.locator('text=uiuser').count() == 0:
        ok('UI — 사용자 삭제 후 목록에서 제거')
    else:
        fail('UI — 삭제 후 확인')

    # UI-8. 비밀번호 변경 성공
    pw_form = page.locator('form').first
    pw_form.locator('input').nth(0).fill('ChangeMe123!')
    pw_form.locator('input').nth(1).fill('AdminUI123!')
    pw_form.locator('input').nth(2).fill('AdminUI123!')
    pw_form.locator('button[type=submit]').click()
    time.sleep(2)
    page.screenshot(path='D:/a2m/atom-harness-base-Dart/kospi-feature-stock/manual_screenshots/final_pw_changed.png')
    if page.locator('text=비밀번호가 변경되었습니다').count() > 0:
        ok('UI — 비밀번호 변경 성공 메시지')
    else:
        fail('UI — 비밀번호 변경 성공')

    # UI-9. 로그아웃 → 로그인 화면
    page.locator('button:has-text("로그아웃")').click()
    time.sleep(1.5)
    if page.locator('text=로그인').count() > 0:
        ok('UI — 로그아웃 → 로그인 화면')
    else:
        fail('UI — 로그아웃')

    # UI-10. 새 비밀번호로 재로그인
    page.fill('input[type=text]', 'admin')
    page.fill('input[type=password]', 'AdminUI123!')
    page.click('button[type=submit]')
    try:
        page.wait_for_selector('button:has-text("로그아웃")', timeout=6000)
        ok('UI — 변경된 비밀번호로 재로그인')
    except:
        fail('UI — 변경된 비밀번호 재로그인')

    # 원래 비밀번호 복원
    page.goto(f'{BASE}/account', wait_until='domcontentloaded', timeout=15000)
    time.sleep(1.5)
    pw_form2 = page.locator('form').first
    pw_form2.locator('input').nth(0).fill('AdminUI123!')
    pw_form2.locator('input').nth(1).fill('ChangeMe123!')
    pw_form2.locator('input').nth(2).fill('ChangeMe123!')
    pw_form2.locator('button[type=submit]').click()
    time.sleep(2)
    if page.locator('text=비밀번호가 변경되었습니다').count() > 0:
        ok('비밀번호 원복 완료')
    else:
        fail('비밀번호 원복')

    browser.close()

# ══════════════════════════════════════════════════════
# 결과 요약
# ══════════════════════════════════════════════════════
total  = len(PASS['results']) + len(PASS['fails'])
passed = len(PASS['results'])
failed = len(PASS['fails'])

print(f'\n{"="*55}')
print(f'자가점검 결과: {passed}/{total} 통과  |  실패: {failed}건')
print('='*55)
for r in PASS['results']:
    print(r)
for f in PASS['fails']:
    print(f)
print('='*55)
