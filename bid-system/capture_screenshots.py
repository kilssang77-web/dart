"""
BidAI Pro 전체 화면 캡처 스크립트 (Playwright)
"""
import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:3001"
EMAIL    = "admin@bid.local"
PASSWORD = "admin1234"
OUT_DIR  = r"D:\a2m\atom-harness-g2b\bid-system\frontend\public\screenshots"
VP       = {"width": 1440, "height": 900}

os.makedirs(OUT_DIR, exist_ok=True)
OK, NG = "OK", "NG"

def log(status, msg):
    print(f"  [{status}] {msg}", flush=True)

def shot(page: Page, name: str, full: bool = False):
    path = os.path.join(OUT_DIR, f"{name}.png")
    try:
        page.screenshot(path=path, full_page=full, timeout=15000)
        log(OK, f"{name}.png")
    except Exception as e:
        log(NG, f"{name}: {e}")

def goto(page: Page, path: str, wait_ms: int = 2500):
    try:
        page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(wait_ms)
    except Exception as e:
        log(NG, f"goto {path}: {e}")

def click_if_exists(page: Page, selector: str, wait_ms: int = 1200):
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=3000)
        el.click()
        page.wait_for_timeout(wait_ms)
        return True
    except Exception:
        return False

def login(page: Page):
    goto(page, "/login", 1500)
    shot(page, "01_login")
    try:
        page.fill('input[type="email"]', EMAIL, timeout=8000)
        page.fill('input[type="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=20000)
        page.wait_for_timeout(2500)
        log(OK, "로그인 성공")
    except Exception as e:
        log(NG, f"로그인 실패: {e}")

def expand_nav(page: Page):
    """사이드바 그룹 모두 펼치기"""
    try:
        for btn in page.locator("aside nav button").all():
            try:
                btn.click(timeout=500)
                page.wait_for_timeout(150)
            except Exception:
                pass
    except Exception:
        pass

def capture_all(page: Page):

    # 00. 사이드바 메뉴 전체 펼침
    print("\n[사이드바]")
    goto(page, "/dashboard", 2500)
    expand_nav(page)
    page.wait_for_timeout(800)
    shot(page, "00_sidebar_menu")

    # 01. 대시보드
    print("\n[대시보드]")
    goto(page, "/dashboard", 3500)
    shot(page, "02_dashboard")
    shot(page, "02_dashboard_full", full=True)

    # 02. KPI 대시보드
    print("\n[KPI 대시보드]")
    goto(page, "/kpi-dashboard", 3500)
    shot(page, "03_kpi_dashboard")
    shot(page, "03_kpi_dashboard_full", full=True)

    # 03. 공고센터
    print("\n[공고센터]")
    goto(page, "/bids", 3500)
    shot(page, "04_bids_list")
    click_if_exists(page, "button:has-text('전체공고')", 1500)
    shot(page, "04_bids_all")
    click_if_exists(page, "button:has-text('추천공고')", 2000)
    shot(page, "04_bids_recommended")
    click_if_exists(page, "button:has-text('관심공고')", 1200)
    shot(page, "04_bids_bookmarks")
    shot(page, "04_bids_full", full=True)

    # 04. 공고 상세
    print("\n[공고 상세]")
    goto(page, "/bids/154603", 3500)
    shot(page, "05_bid_detail")
    shot(page, "05_bid_detail_full", full=True)
    click_if_exists(page, "[role='tab']:has-text('AI')", 2500)
    shot(page, "05_bid_detail_ai_tab")
    click_if_exists(page, "[role='tab']:has-text('경쟁사')", 2500)
    shot(page, "05_bid_detail_competitors_tab")
    click_if_exists(page, "[role='tab']:has-text('이력')", 2000)
    shot(page, "05_bid_detail_history_tab")

    # 05. 공고 선별
    print("\n[공고 선별]")
    goto(page, "/bid-selection", 3500)
    shot(page, "06_bid_selection")
    shot(page, "06_bid_selection_full", full=True)

    # 06. 투찰 실행 관리
    print("\n[투찰 실행 관리]")
    goto(page, "/executions", 3500)
    shot(page, "07_executions")
    shot(page, "07_executions_full", full=True)

    # 07. 투찰 결정 분석 — 실제 라우트는 /decision (NOT /tender-decision)
    print("\n[투찰 결정 분석]")
    goto(page, "/decision?bid=154603", 8000)
    shot(page, "08_tender_decision")
    shot(page, "08_tender_decision_full", full=True)
    page.wait_for_timeout(3000)
    shot(page, "08_tender_decision_result")

    # 08. AI 투찰 추천 — 실제 라우트는 /bids/:id/final-recommend
    print("\n[AI 투찰 추천]")
    goto(page, "/recommend", 3000)
    shot(page, "09_recommend")
    goto(page, "/bids/154603/final-recommend", 5000)
    shot(page, "09_tender_recommend")

    # 09. 경쟁사 분석
    print("\n[경쟁사 분석]")
    goto(page, "/competitors", 3500)
    shot(page, "10_competitors")
    shot(page, "10_competitors_full", full=True)

    # 10. Rival Radar — 실제 라우트는 /bids/:id/rival-radar
    print("\n[Rival Radar]")
    goto(page, "/bids/154603/rival-radar", 5000)
    shot(page, "11_rival_radar")
    shot(page, "11_rival_radar_full", full=True)

    # 11. 자사 경쟁사
    print("\n[자사 경쟁사]")
    goto(page, "/our-competitors", 3500)
    shot(page, "12_our_competitors")
    shot(page, "12_our_competitors_full", full=True)

    # 12. 예가 빈도 분석
    print("\n[예가 빈도 분석]")
    goto(page, "/yega", 3500)
    shot(page, "13_yega")
    shot(page, "13_yega_full", full=True)

    # 13. 백테스트 엔진
    print("\n[백테스트 엔진]")
    goto(page, "/backtest", 3500)
    shot(page, "14_backtest")
    click_if_exists(page, "button:has-text('실행')", 5000)
    shot(page, "14_backtest_result")
    shot(page, "14_backtest_full", full=True)

    # 14. 투찰 이력 분석
    print("\n[투찰 이력 분석]")
    goto(page, "/journal-history", 3500)
    shot(page, "15_journal_history")
    shot(page, "15_journal_history_full", full=True)

    # 15. 통계 분석
    print("\n[통계 분석]")
    goto(page, "/statistics", 3500)
    shot(page, "16_statistics")
    shot(page, "16_statistics_full", full=True)

    # 16. 성과센터
    print("\n[성과센터]")
    goto(page, "/performance", 3500)
    shot(page, "17_performance")
    shot(page, "17_performance_full", full=True)

    # 17. 내 입찰 이력
    print("\n[내 입찰 이력]")
    goto(page, "/my-bids", 3500)
    shot(page, "18_my_bids")
    shot(page, "18_my_bids_full", full=True)

    # 18. 포트폴리오
    print("\n[포트폴리오]")
    goto(page, "/portfolio", 3500)
    shot(page, "19_portfolio")
    shot(page, "19_portfolio_full", full=True)

    # 19. 발주기관 분석
    print("\n[발주기관 분석]")
    goto(page, "/agencies", 3500)
    shot(page, "20_agencies")
    shot(page, "20_agencies_full", full=True)
    # 첫 번째 행 클릭
    click_if_exists(page, "table tbody tr:first-child td:first-child", 2500)
    shot(page, "20_agency_detail")
    shot(page, "20_agency_detail_full", full=True)

    # 20. 시장 인텔리전스
    print("\n[시장 인텔리전스]")
    goto(page, "/market-intel", 3500)
    shot(page, "21_market_intel")
    shot(page, "21_market_intel_full", full=True)

    # 21. 적격심사 계산기
    print("\n[적격심사 계산기]")
    goto(page, "/qualification", 3500)
    shot(page, "22_qualification")
    shot(page, "22_qualification_full", full=True)

    # 22. 공동도급 — joint-sim 실제 라우트는 /bids/:id/joint-sim
    print("\n[공동도급]")
    goto(page, "/joint-bid", 3500)
    shot(page, "23_joint_bid")
    goto(page, "/bids/154603/joint-sim", 5000)
    shot(page, "23_joint_sim")

    # 23. 키워드 관리
    print("\n[키워드 관리]")
    goto(page, "/keywords", 3500)
    shot(page, "24_keywords")
    shot(page, "24_keywords_full", full=True)

    # 24. 회사 프로파일
    print("\n[회사 프로파일]")
    goto(page, "/company-profile", 3500)
    shot(page, "25_company_profile")
    shot(page, "25_company_profile_full", full=True)

    # 25. 알림
    print("\n[알림]")
    goto(page, "/notifications", 3000)
    shot(page, "26_notifications")

    # 26. 시스템 관리
    print("\n[시스템 관리]")
    goto(page, "/admin", 3500)
    shot(page, "27_admin")
    click_if_exists(page, "button:has-text('사용자')", 1500)
    shot(page, "27_admin_users")
    click_if_exists(page, "button:has-text('ML')", 1500)
    shot(page, "27_admin_ml")
    click_if_exists(page, "button:has-text('수집')", 1500)
    shot(page, "27_admin_collector")
    shot(page, "27_admin_full", full=True)

    # 27. 오늘의 입찰
    print("\n[오늘의 입찰]")
    goto(page, "/today", 3500)
    shot(page, "28_today")
    shot(page, "28_today_full", full=True)

    # 28. 사용자 매뉴얼 (현재 화면)
    print("\n[사용자 매뉴얼]")
    goto(page, "/manual", 3000)
    shot(page, "29_manual")


if __name__ == "__main__":
    print("BidAI Pro 전체 화면 캡처 시작", flush=True)
    t0 = time.time()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = browser.new_context(viewport=VP, locale="ko-KR", timezone_id="Asia/Seoul")
        page = ctx.new_page()
        page.set_default_timeout(25000)

        print("\n[로그인]", flush=True)
        login(page)
        capture_all(page)
        browser.close()

    files = [f for f in os.listdir(OUT_DIR) if f.endswith(".png")]
    print(f"\n완료: {len(files)}개 스크린샷  ({time.time()-t0:.0f}초)", flush=True)
