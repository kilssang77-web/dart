# -*- coding: utf-8 -*-
"""Quant Eye 사용자 매뉴얼 HTML 생성 스크립트."""
import sys, os, base64
sys.stdout.reconfigure(encoding='utf-8')

BASE = "D:/a2m/atom-harness-base-Dart/kospi-feature-stock"
SHOT = f"{BASE}/manual_screenshots"
# Vite public/ 디렉토리에 생성 → 빌드 시 outDir로 자동 복사됨
OUT  = f"{BASE}/frontend/public/manual.html"

def img_b64(name: str) -> str | None:
    path = f"{SHOT}/{name}.png"
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

def img_tag(name: str, caption: str) -> str:
    src = img_b64(name)
    if not src:
        return f'<p class="img-missing">[이미지 없음: {name}.png]</p>'
    return f'''
<figure>
  <img src="{src}" alt="{caption}" loading="lazy" />
  <figcaption>{caption}</figcaption>
</figure>'''

# ─── CSS ────────────────────────────────────────────────────────────────────
CSS = """
:root {
  --bg: #0f1117;
  --bg2: #161b27;
  --bg3: #1e2535;
  --fg: #e2e8f0;
  --muted: #8892a4;
  --accent: #3b82f6;
  --accent2: #60a5fa;
  --border: #2d3748;
  --code-bg: #111827;
  --table-head: #1f3050;
  --table-alt: #161b27;
  --sidebar-w: 260px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: 'Malgun Gothic', 'Noto Sans KR', sans-serif;
  background: var(--bg); color: var(--fg);
  font-size: 14px; line-height: 1.75;
  display: flex;
}

/* ── 사이드바 ── */
#sidebar {
  width: var(--sidebar-w);
  height: 100vh;
  position: fixed; top: 0; left: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 24px 0 40px;
  z-index: 10;
}
#sidebar .logo {
  padding: 0 20px 20px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
#sidebar .logo h2 {
  font-size: 18px; font-weight: 700;
  color: var(--accent2); letter-spacing: -0.5px;
}
#sidebar .logo p {
  font-size: 10px; color: var(--muted); margin-top: 2px;
}
#sidebar nav a {
  display: block;
  padding: 6px 20px;
  color: var(--muted);
  text-decoration: none;
  font-size: 12.5px;
  border-left: 2px solid transparent;
  transition: all .15s;
}
#sidebar nav a:hover,
#sidebar nav a.active {
  color: var(--fg);
  border-left-color: var(--accent);
  background: var(--bg3);
}
#sidebar nav .ch-title {
  padding: 14px 20px 4px;
  font-size: 10px; font-weight: 700;
  text-transform: uppercase;
  color: var(--muted); letter-spacing: 1px;
}
#sidebar nav .sub { padding-left: 32px; font-size: 12px; }

/* ── 본문 ── */
#content {
  margin-left: var(--sidebar-w);
  flex: 1;
  max-width: 900px;
  padding: 40px 48px 80px;
}

h1 {
  font-size: 26px; font-weight: 700;
  color: var(--accent2);
  border-bottom: 2px solid var(--border);
  padding-bottom: 12px; margin: 48px 0 24px;
}
h1:first-child { margin-top: 0; }
h2 {
  font-size: 19px; font-weight: 700;
  color: var(--fg);
  margin: 36px 0 14px;
  padding-left: 10px;
  border-left: 3px solid var(--accent);
}
h3 {
  font-size: 15px; font-weight: 700;
  color: var(--accent2);
  margin: 24px 0 10px;
}

p { margin-bottom: 12px; color: var(--fg); }

ul, ol { margin: 8px 0 12px 24px; }
li { margin-bottom: 5px; color: var(--fg); }
li::marker { color: var(--accent); }

/* ── 코드 블록 ── */
pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
  overflow-x: auto;
  font-family: 'Consolas', 'D2Coding', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #a5f3fc;
  margin: 12px 0 20px;
  white-space: pre;
}

/* ── 테이블 ── */
.tbl-wrap { overflow-x: auto; margin: 14px 0 24px; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
thead tr { background: var(--table-head); }
thead th {
  padding: 10px 12px;
  text-align: left;
  color: #fff;
  font-weight: 700;
  border: 1px solid var(--border);
  white-space: nowrap;
}
tbody tr:nth-child(even) { background: var(--table-alt); }
tbody td {
  padding: 8px 12px;
  border: 1px solid var(--border);
  vertical-align: top;
}

/* ── 이미지 ── */
figure {
  margin: 20px 0 28px;
  text-align: center;
}
figure img {
  max-width: 100%;
  border-radius: 8px;
  border: 1px solid var(--border);
  box-shadow: 0 4px 24px rgba(0,0,0,.5);
}
figcaption {
  margin-top: 8px;
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}
.img-missing {
  background: var(--bg3);
  border: 1px dashed var(--border);
  padding: 16px; border-radius: 6px;
  color: var(--muted); text-align: center;
  font-size: 12px;
}

/* ── 커버 ── */
#cover {
  text-align: center;
  padding: 60px 0 80px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 48px;
}
#cover h1 {
  font-size: 48px; border: none; margin: 0 0 12px;
  background: linear-gradient(135deg, var(--accent2), #a78bfa);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
#cover .sub {
  font-size: 16px; color: var(--muted); margin-bottom: 8px;
}
#cover .ver {
  font-size: 13px; color: var(--muted)/70;
  margin-top: 24px;
}
.badge {
  display: inline-block;
  background: var(--accent)/20;
  color: var(--accent2);
  border: 1px solid var(--accent)/40;
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 12px; font-weight: 600;
  margin: 0 4px;
}

/* ── 알림 박스 ── */
.note {
  background: rgba(59,130,246,.08);
  border-left: 3px solid var(--accent);
  padding: 12px 16px; border-radius: 0 6px 6px 0;
  margin: 12px 0 20px;
  font-size: 13px;
}
.warn {
  background: rgba(245,158,11,.08);
  border-left: 3px solid #f59e0b;
  padding: 12px 16px; border-radius: 0 6px 6px 0;
  margin: 12px 0 20px;
  font-size: 13px;
}

/* ── 스크롤바 ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg2); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }

@media (max-width: 768px) {
  #sidebar { display: none; }
  #content { margin-left: 0; padding: 24px 20px 60px; }
}
"""

# ─── JS (스크롤 하이라이트) ─────────────────────────────────────────────────
JS = """
const links = document.querySelectorAll('#sidebar nav a[href^="#"]');
const sections = [];
links.forEach(a => {
  const el = document.querySelector(a.getAttribute('href'));
  if (el) sections.push({ el, a });
});
window.addEventListener('scroll', () => {
  let cur = null;
  for (const { el, a } of sections) {
    if (el.getBoundingClientRect().top <= 80) cur = a;
  }
  links.forEach(a => a.classList.remove('active'));
  if (cur) cur.classList.add('active');
}, { passive: true });
"""

# ─── 사이드바 내비게이션 ──────────────────────────────────────────────────────
SIDEBAR = """
<div id="sidebar">
  <div class="logo">
    <h2>📊 Quant Eye</h2>
    <p>사용자 매뉴얼 v1.0</p>
  </div>
  <nav>
    <div class="ch-title">시스템 개요</div>
    <a href="#ch1">1장. 시스템 개요</a>
    <a href="#s1-1" class="sub">1.1 소개 및 목적</a>
    <a href="#s1-2" class="sub">1.2 주요 기능 요약</a>
    <a href="#s1-3" class="sub">1.3 시스템 구성도</a>
    <a href="#s1-4" class="sub">1.4 데이터 흐름도</a>
    <a href="#s1-5" class="sub">1.5 용어 정의</a>

    <div class="ch-title">설치 및 실행</div>
    <a href="#ch2">2장. 설치 및 실행</a>
    <a href="#s2-1" class="sub">2.1 사전 요구사항</a>
    <a href="#s2-2" class="sub">2.2 다른 PC 독립 실행</a>
    <a href="#s2-3" class="sub">2.3 초기 데이터 적재</a>

    <div class="ch-title">화면별 기능</div>
    <a href="#ch3">3장. 화면별 기능</a>
    <a href="#s3-1" class="sub">3.1 대시보드</a>
    <a href="#s3-2" class="sub">3.2 특징주 탐지</a>
    <a href="#s3-3" class="sub">3.3 매매 추천</a>
    <a href="#s3-4" class="sub">3.4 종목 검색</a>
    <a href="#s3-5" class="sub">3.5 성과 추적</a>
    <a href="#s3-6" class="sub">3.6 모델 성능</a>
    <a href="#s3-7" class="sub">3.7 스크리너</a>
    <a href="#s3-8" class="sub">3.8 백테스트</a>
    <a href="#s3-9" class="sub">3.9 시스템 헬스</a>
    <a href="#s3-10" class="sub">3.10 인텔리전스</a>
    <a href="#s3-11" class="sub">3.11 자동매매</a>
    <a href="#s3-12" class="sub">3.12 관심종목</a>
    <a href="#s3-13" class="sub">3.13 알림</a>
    <a href="#s3-14" class="sub">3.14 랭킹</a>
    <a href="#s3-15" class="sub">3.15 설정</a>

    <div class="ch-title">알고리즘</div>
    <a href="#ch4">4장. 점수·추천 알고리즘</a>
    <a href="#s4-1" class="sub">4.1 특징주 탐지</a>
    <a href="#s4-2" class="sub">4.2 rec_score 계산식</a>
    <a href="#s4-3" class="sub">4.3 ML 확률 모델</a>
    <a href="#s4-4" class="sub">4.4 시장 국면 판단</a>
    <a href="#s4-5" class="sub">4.5 리스크 스코어</a>
    <a href="#s4-6" class="sub">4.6 확률 캡</a>

    <div class="ch-title">시나리오</div>
    <a href="#ch5">5장. 사용 시나리오</a>
    <a href="#s5-1" class="sub">5.1 일반 투자자</a>
    <a href="#s5-2" class="sub">5.2 단타 트레이더</a>
    <a href="#s5-3" class="sub">5.3 시스템 관리자</a>
    <a href="#s5-4" class="sub">5.4 데이터 관리자</a>

    <div class="ch-title">참고</div>
    <a href="#ch6">6장. FAQ / 문제 해결</a>
    <a href="#ch7">7장. 부록</a>
    <a href="#appA" class="sub">A. API 엔드포인트</a>
    <a href="#appB" class="sub">B. 환경변수</a>
    <a href="#appC" class="sub">C. 이벤트 타입</a>
    <a href="#appD" class="sub">D. Redis 채널</a>
    <a href="#appE" class="sub">E. Docker 프로파일</a>
  </nav>
</div>
"""

# ─── 본문 ─────────────────────────────────────────────────────────────────────
def build_body() -> str:
    parts = []

    # ── 표지 ──
    parts.append("""
<div id="cover">
  <h1>Quant Eye</h1>
  <p class="sub">KOSPI/KOSDAQ 실시간 특징주 탐지 및 매매 추천 시스템</p>
  <br/>
  <span class="badge">v1.0</span>
  <span class="badge">2026-07-09</span>
  <p class="ver">Real-time Feature Stock Detection &amp; AI Recommendation System</p>
</div>
""")

    # ══════════════════════════════════════════════
    # 1장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch1">1장. 시스템 개요</h1>')

    parts.append('<h2 id="s1-1">1.1 시스템 소개 및 목적</h2>')
    parts.append('<p>Quant Eye는 KOSPI/KOSDAQ 종목의 실시간 시세, 수급, 공시, 뉴스, 재무 데이터를 종합 수집·분석해 <strong>\'특징주\'를 탐지</strong>하고, ML 기반 매매 신호(추천)를 산출·추적하는 종합 트레이딩 어시스턴트 시스템입니다.</p>')
    parts.append('<ul>'
        '<li>장중 급등·거래량 폭발·수급 이상·공시 후 반응 등을 초 단위로 포착</li>'
        '<li>9년치(2018~) 유사 사례 검색 + LightGBM 확률 모델로 성공 확률 계산</li>'
        '<li>시장 국면(강세/중립/약세)을 반영한 리스크 조정 매매 추천</li>'
        '<li>KIS(한국투자증권) API를 통한 자동 매매 실행 (모의/실전)</li>'
        '<li>추천 이후 1일/3일/5일/10일 성과를 자동 추적해 모델을 재학습</li>'
        '</ul>')

    parts.append('<h2 id="s1-2">1.2 주요 기능 요약</h2>')
    parts.append('<div class="tbl-wrap"><table>'
        '<thead><tr><th>카테고리</th><th>기능</th><th>설명</th></tr></thead><tbody>'
        '<tr><td>시장 관측</td><td>대시보드</td><td>지수·상승/하락 상위·섹터 히트맵·신고가·수급 상위 실시간</td></tr>'
        '<tr><td>시장 관측</td><td>인텔리전스</td><td>테마·뉴스·공시·이슈를 통합해 오늘의 시장 스토리 제공</td></tr>'
        '<tr><td>시장 관측</td><td>랭킹</td><td>거래대금·급등·이벤트 발생 종목 순위</td></tr>'
        '<tr><td>탐지</td><td>특징주 이벤트</td><td>14종 이벤트 실시간 탐지·시그널 점수화</td></tr>'
        '<tr><td>탐지</td><td>스크리너</td><td>RSI·52W신고가·거래량·수급·ML확률·PER/ROE AND 조합 검색</td></tr>'
        '<tr><td>추천</td><td>매매 추천</td><td>ML 확률+유사사례+리스크로 rec_score(1~100)·success_prob 계산</td></tr>'
        '<tr><td>추천</td><td>관심종목</td><td>지정 종목에 대한 시그널·가격 알림 관리</td></tr>'
        '<tr><td>실행</td><td>자동매매(Trader)</td><td>KIS API를 통한 모의/실전 주문·포지션 관리</td></tr>'
        '<tr><td>실행</td><td>알림</td><td>텔레그램/이메일로 추천·이벤트 발생 시 즉시 전송</td></tr>'
        '<tr><td>평가</td><td>성과 추적</td><td>추천 이후 1d/3d/5d/10d 수익률·손절/익절 히트 추적</td></tr>'
        '<tr><td>평가</td><td>모델 성능</td><td>AUC·정밀도·재현율·이벤트 유형별 승률 대시보드</td></tr>'
        '<tr><td>평가</td><td>백테스트</td><td>과거 데이터로 특징주+추천 규칙 시뮬레이션</td></tr>'
        '<tr><td>관리</td><td>시스템 헬스</td><td>각 마이크로서비스 상태·수집 지연·큐잉 실시간 모니터링</td></tr>'
        '<tr><td>관리</td><td>설정</td><td>임계값·알림·API 키·재학습 옵션 관리</td></tr>'
        '</tbody></table></div>')

    parts.append('<h2 id="s1-3">1.3 시스템 구성도</h2>')
    parts.append('<p>Quant Eye는 마이크로서비스 아키텍처를 채택하고, 모든 컨테이너는 docker-compose로 오케스트레이션됩니다.</p>')
    parts.append('''<pre>
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Quant Eye 시스템 구성                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  [외부 데이터]       [수집 레이어]        [처리 레이어]       [서비스 레이어]│
│                                                                             │
│  KIS OpenAPI ─────► collector-tick ──┐                                      │
│  (WebSocket)         (틱/호가)       │                                      │
│                                      ├──► detector ──┐   ┌── api :8000     │
│  KIS REST    ─────► collector-daily ─┤    (14종 탐지) │   │   (FastAPI)     │
│  (일봉/재무)         (일봉/기술지표) │                │   │        ▲        │
│                                      ├──► analyzer ──┤   │        │        │
│  KIND/DART   ─────► collector-news  ─┤    (유사사례)  │   │  [브라우저]     │
│  (공시)                              │                │   │  React SPA      │
│                                      ├──► ml :8001 ──┤   │  (localhost:8000│
│  뉴스 RSS    ─────► collector-supply┤   (LightGBM)   │   │        )        │
│                       (수급 30분)   │                │   │                 │
│                                      ├──► recommender─┴──►│                │
│  금융위 API  ─────► collector-govdata│   (rec_score)      │                │
│  (시총 EOD)         (일 1회 18:00)   │                     │                │
│                                                            │                │
│                     [저장 레이어]                     ├──► trader :8004 ──►│
│                     PostgreSQL 16 + TimescaleDB       │    (KIS 주문 API)  │
│                       + pgvector (유사사례)           │        │           │
│                     Redis 7 (실시간/캐시/Pub-Sub)     │        ▼           │
│                                                       └──► notifier :8003  │
│                     [비동기 채널]                          (Telegram 알림) │
│                     ch:recommendation  ch:feature                          │
└─────────────────────────────────────────────────────────────────────────────┘</pre>''')

    parts.append('<h2 id="s1-4">1.4 데이터 흐름도</h2>')
    parts.append('<p>전형적인 신호 발생 흐름:</p>')
    parts.append('''<pre>
1) KIS WebSocket → collector-tick   : 초 단위 호가·체결 저장 (Redis)
2) 30분 배치       → collector-supply : supply_demand 테이블 갱신
3) 이벤트 탐지     → detector          : feature_events 삽입, ch:feature 발행
4) 유사 사례 검색  → analyzer          : pgvector cosine top-K + LightGBM 확률
5) 추천 산출       → recommender       : rec_score + regime 보정 → recommendations
6) 사용자 노출     → api → 프론트엔드  : 대시보드 / 추천 화면
7) 자동 매매(선택)→ trader             : action='BUY' → KIS 주문
8) 성과 추적       → tracking          : 1d/3d/5d/10d 수익률 자동 계산
9) 재학습          → ml-autoretrain    : 14일·28일 00:00 KST 자동 재학습</pre>''')

    parts.append('<h2 id="s1-5">1.5 용어 정의</h2>')
    parts.append('<div class="tbl-wrap"><table>'
        '<thead><tr><th>용어</th><th>설명</th></tr></thead><tbody>'
        '<tr><td><strong>특징주(Feature Event)</strong></td><td>거래량 급증·신고가·수급 이상 등 시장 참여자 관심을 끌 만한 이벤트</td></tr>'
        '<tr><td>signal_score</td><td>이벤트별 원시 점수 (0~1). 값이 클수록 강한 신호</td></tr>'
        '<tr><td>rec_score</td><td>매매 추천 종합 점수 (1~100). ML+유사사례+리스크 종합</td></tr>'
        '<tr><td>success_prob</td><td>추천 성공 확률 (0~0.95). 캡=0.95 (과신 방지)</td></tr>'
        '<tr><td>regime</td><td>시장 국면: bull(강세) / neutral(중립) / bear(약세) — KOSPI MA20 기준</td></tr>'
        '<tr><td>risk_score</td><td>리스크 점수 (0~1). 값이 클수록 위험 신호(변동성·수급 악화 등)</td></tr>'
        '<tr><td>r_1d/3d/5d/10d</td><td>추천 시점 대비 1일/3일/5일/10일 종가 수익률</td></tr>'
        '<tr><td>hit_target</td><td>목표가 도달 여부(익절)</td></tr>'
        '<tr><td>hit_stop</td><td>손절가 도달 여부</td></tr>'
        '<tr><td>dedupe</td><td>종목당 최고 점수 1건만 표시 옵션</td></tr>'
        '<tr><td>walk-forward</td><td>시간 순 재학습·검증 방식 (실전 유사)</td></tr>'
        '<tr><td>Similar Case</td><td>pgvector로 검색한 과거 유사 이벤트 top-K</td></tr>'
        '</tbody></table></div>')

    # ══════════════════════════════════════════════
    # 2장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch2">2장. 시스템 설치 및 실행</h1>')

    parts.append('<h2 id="s2-1">2.1 사전 요구사항</h2>')
    parts.append('<div class="tbl-wrap"><table>'
        '<thead><tr><th>항목</th><th>최소 사양</th><th>권장 사양</th></tr></thead><tbody>'
        '<tr><td>OS</td><td>Windows 10 (WSL2) / Ubuntu 22.04 / macOS 12</td><td>Windows 11 + WSL2 / Ubuntu 24.04</td></tr>'
        '<tr><td>CPU</td><td>4 코어</td><td>8 코어 이상</td></tr>'
        '<tr><td>메모리</td><td>8 GB</td><td>16 GB 이상</td></tr>'
        '<tr><td>디스크</td><td>50 GB SSD</td><td>200 GB NVMe SSD</td></tr>'
        '<tr><td>Docker</td><td>Docker Desktop 4.30 이상</td><td>최신 안정 버전</td></tr>'
        '<tr><td>Python</td><td>3.12 (관리 스크립트 사용 시)</td><td>3.12.x</td></tr>'
        '<tr><td>Node.js</td><td>선택 (프론트 재빌드 시)</td><td>20 LTS</td></tr>'
        '<tr><td>네트워크</td><td>KIS/DART/KIND/금융위 API 접근 가능</td><td>고정 IP + 방화벽 규칙</td></tr>'
        '</tbody></table></div>')

    parts.append('<h2 id="s2-2">2.2 다른 PC에서 독립 실행하는 방법</h2>')
    parts.append('<p>빈 PC에 시스템을 새로 설치·실행하는 표준 절차입니다. 순서대로 진행하십시오.</p>')

    parts.append('<h3>Step 1. Docker Desktop 설치</h3>')
    parts.append('<ol>'
        '<li>https://www.docker.com/products/docker-desktop 에서 OS에 맞는 설치 파일 다운로드</li>'
        '<li>설치 실행 → WSL2 백엔드 사용 옵션 체크 (Windows)</li>'
        '<li>설치 완료 후 재부팅, Docker Desktop 실행</li>'
        '<li>Settings → Resources → Memory: 7GB 이상 / CPUs: 4 이상 설정</li>'
        '</ol>')

    parts.append('<h3>Step 2. 프로젝트 소스 복사</h3>')
    parts.append('<ul>'
        '<li>방법 A (Git): <code>git clone &lt;repository-url&gt; kospi-feature-stock</code></li>'
        '<li>방법 B (ZIP): USB/네트워크 공유로 kospi-feature-stock 폴더 전체 복사</li>'
        '</ul>')
    parts.append('<pre>cd kospi-feature-stock</pre>')

    parts.append('<h3>Step 3. 환경 변수(.env) 파일 설정</h3>')
    parts.append('<p>프로젝트 루트에 <code>.env</code> 파일을 생성하고 아래 항목을 채웁니다.</p>')
    parts.append('''<pre>
# ── PostgreSQL ─────────────────────────────
POSTGRES_DB=fstock
POSTGRES_USER=fstock
POSTGRES_PASSWORD=&lt;임의의 강력한 비밀번호&gt;
POSTGRES_PORT=5432

# ── Redis ─────────────────────────────────
REDIS_PORT=6379

# ── API/Trader 포트 ───────────────────────
API_PORT=8000
ML_API_PORT=8001
NOTIFIER_PORT=8003
TRADER_PORT=8004

# ── KIS OpenAPI (한국투자증권) ────────────
KIS_APP_KEY=&lt;KIS 앱키&gt;
KIS_APP_SECRET=&lt;KIS 앱시크릿&gt;
KIS_ACCOUNT_NO=&lt;계좌번호 8자리&gt;
KIS_ACCOUNT_CD=01
KIS_BASE_URL=https://openapi.koreainvestment.com:9443
KIS_MODE=paper   # paper(모의) / live(실전)

# ── 외부 데이터 ───────────────────────────
DART_API_KEY=&lt;금감원 DART 키&gt;
KIND_API_KEY=&lt;KIND 키&gt;
GOVDATA_API_KEY=&lt;금융위 시가총액 API 키&gt;

# ── 알림 ──────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── ML/추천 임계값 ────────────────────────
REC_COOLDOWN_MINUTES=60
REC_PERF_MIN_PROB=0.236
REGIME_BEAR_THRESHOLD=-3.0
REGIME_BULL_THRESHOLD=-0.5
REGIME_BEAR_SUPPRESS=true</pre>''')

    parts.append('<h3>Step 4. Docker Compose로 시스템 기동</h3>')
    parts.append('''<pre>
# 1) 이미지 빌드 + 컨테이너 기동 (백그라운드)
docker compose up -d --build

# 2) 서비스 상태 확인
docker compose ps

# 3) 헬스 체크
curl http://localhost:8000/api/health
curl http://localhost:8001/health   # ML
curl http://localhost:8004/health   # Trader</pre>''')
    parts.append('<ul>'
        '<li>fstock-postgres, fstock-redis (인프라)</li>'
        '<li>fstock-collector-tick / -daily / -supply / -news / -batch / -financials / -govdata (수집)</li>'
        '<li>fstock-detector, fstock-analyzer, fstock-ml, fstock-recommender (처리)</li>'
        '<li>fstock-api, fstock-trader, fstock-notifier (서비스)</li>'
        '</ul>')

    parts.append('<h3>Step 5. 초기 데이터 부트스트랩 (최초 1회)</h3>')
    parts.append('''<pre>
# 종목 마스터 + 최근 일봉 + 재무 초기 로드
python setup_bootstrap.py

# (선택) 9년치 일봉 백필
docker compose --profile backfill up collector-bars-backfill

# (선택) ML 모델 학습
docker compose --profile tools run --rm ml-train</pre>''')

    parts.append('<h3>Step 6. 브라우저 접속</h3>')
    parts.append('<ul>'
        '<li>동일 PC: <strong>http://localhost:8000</strong></li>'
        '<li>동일 네트워크 다른 PC: http://&lt;서버IP&gt;:8000 (예: http://192.168.1.100:8000)</li>'
        '</ul>')
    parts.append('<p>사이드바에 15개 메뉴가 표시되면 정상 설치 완료입니다.</p>')

    parts.append('<h3>Step 7. 시스템 종료/재시작</h3>')
    parts.append('''<pre>
# 정지 (컨테이너 유지)
docker compose stop

# 완전 종료 + 컨테이너 제거
docker compose down

# 완전 종료 + 데이터 삭제 (주의: DB 데이터 소실)
docker compose down -v

# 재기동
docker compose up -d</pre>''')

    parts.append('<h2 id="s2-3">2.3 초기 설정 및 데이터 적재</h2>')
    parts.append('<ol>'
        '<li>종목 마스터 등록: scripts/init_stocks.py 실행 (KOSPI/KOSDAQ 전 종목)</li>'
        '<li>일봉 백필: docker compose --profile backfill up collector-bars-backfill</li>'
        '<li>수급 백필: scripts/backfill_supply.py --days 207</li>'
        '<li>재무 수집: docker compose exec collector-financials python entrypoints/financials_worker.py --once</li>'
        '<li>시가총액 백필: collector-govdata 워커 수동 실행</li>'
        '<li>ML 학습: docker compose --profile tools run --rm ml-train</li>'
        '<li>장 시작 시각까지 약 10~20분 대기 (Redis 캐시 워밍업)</li>'
        '</ol>')

    # ══════════════════════════════════════════════
    # 3장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch3">3장. 화면별 기능 설명</h1>')

    screens = [
        ("s3-1", "3.1 대시보드 (Dashboard)", "01_dashboard", "그림 3-1. 대시보드 화면",
         '<p>대시보드는 시장 전체 현황과 오늘의 핵심 신호를 한 페이지에 요약합니다.</p>'
         '<p><strong>표시 항목:</strong></p><ul>'
         '<li>KOSPI/KOSDAQ 실시간 지수 (KIS API → 30초 캐시, 실패 시 daily_bars 폴백)</li>'
         '<li>시장 국면 배지: bull(강세) / neutral(중립) / bear(약세) — KOSPI MA20 대비 %</li>'
         '<li>상승/하락 상위 5개 종목 (실시간 호가 보정)</li>'
         '<li>섹터 히트맵: 섹터별 평균 등락률 + 상위 종목 top-5</li>'
         '<li>신고가 종목: 최근 24시간 내 52W/26W/20D 신고가 이벤트</li>'
         '<li>외국인/기관 순매수 상위 10개 (supply_demand + daily_bars 병합)</li>'
         '</ul>'
         '<div class="note">💡 <strong>사용 팁:</strong> 지수 배지가 bear일 때는 추천 확률이 자동으로 0.75배로 감쇄됩니다. 섹터 히트맵의 셀 클릭 시 해당 섹터 종목 목록으로 필터링됩니다.</div>'),

        ("s3-2", "3.2 특징주 탐지 (Feature Events)", "02_features", "그림 3-2. 특징주 탐지 화면",
         '<p>실시간으로 탐지된 특징주 이벤트를 시그널 점수(signal_score) 순으로 조회합니다.</p>'
         '<p><strong>주요 필터:</strong></p><ul>'
         '<li>이벤트 타입: 14종 중 선택</li>'
         '<li>종목 코드 / 시장(KOSPI/KOSDAQ)</li>'
         '<li>최소 시그널 점수 (기본 0.5)</li>'
         '<li>조회 기간 (시간 단위, 최대 168)</li>'
         '<li>dedupe: 종목당 최고 점수 1건만 표시</li>'
         '</ul>'
         '<div class="tbl-wrap"><table><thead><tr><th>이벤트 타입</th><th>설명</th><th>핵심 조건</th></tr></thead><tbody>'
         '<tr><td>VOLUME_SURGE</td><td>거래량 급증</td><td>당일 거래량 ÷ 20일 평균 ≥ 3</td></tr>'
         '<tr><td>AMOUNT_SURGE</td><td>거래대금 급증</td><td>당일 거래대금 ÷ 20일 평균 ≥ 3</td></tr>'
         '<tr><td>BREAKOUT_52W</td><td>52주 신고가</td><td>당일 고가 ≥ 최근 252 거래일 최고가</td></tr>'
         '<tr><td>BREAKOUT_26W</td><td>26주 신고가</td><td>당일 고가 ≥ 최근 126 거래일 최고가</td></tr>'
         '<tr><td>BREAKOUT_13W</td><td>13주 신고가</td><td>당일 고가 ≥ 최근 63 거래일 최고가</td></tr>'
         '<tr><td>BREAKOUT_20D</td><td>20일 신고가</td><td>당일 고가 ≥ 최근 20 거래일 최고가</td></tr>'
         '<tr><td>VI_TRIGGERED</td><td>변동성완화장치 발동</td><td>10% 이상 등락 후 2분 정지</td></tr>'
         '<tr><td>LONG_WHITE_CANDLE</td><td>장대양봉</td><td>몸통 > 5%, 종가 근접 고가</td></tr>'
         '<tr><td>HAMMER_CANDLE</td><td>망치형</td><td>아래꼬리 > 몸통×2</td></tr>'
         '<tr><td>MORNING_STAR</td><td>샛별형</td><td>3봉 반전 패턴</td></tr>'
         '<tr><td>SUPPLY_ANOMALY</td><td>수급 이상</td><td>외국인+기관 대량 순매수</td></tr>'
         '<tr><td>POST_DISCLOSURE_SURGE</td><td>공시 후 급등</td><td>공시 시각 이후 30분 내 5%↑</td></tr>'
         '<tr><td>SHORT_SURGE</td><td>공매도 급증</td><td>공매도 잔고 급등</td></tr>'
         '<tr><td>DUAL_BUY_STREAK</td><td>외인+기관 연속 순매수</td><td>N일 연속 동반 매수</td></tr>'
         '</tbody></table></div>'),

        ("s3-3", "3.3 매매 추천 (Recommendations)", "03_recommendations", "그림 3-3. 매매 추천 화면",
         '<p>탐지된 특징주 이벤트를 recommender 서비스가 ML 확률과 유사사례로 재평가해 산출한 매매 추천 목록입니다.</p>'
         '<p><strong>주요 필터:</strong></p><ul>'
         '<li>액션: ALL / BUY / SELL / SKIP</li>'
         '<li>시장 / 종목 코드</li>'
         '<li>최소 성공 확률(min_prob, 기본 0.30)</li>'
         '<li>조회 기간 (시간 단위, 최대 168)</li>'
         '<li>dedupe: 종목당 최고 확률 1건만 표시 (기본 ON)</li>'
         '</ul>'
         '<p><strong>각 추천 카드 정보:</strong></p><ul>'
         '<li>종목 코드/이름/시장, 액션(BUY/SELL/SKIP)</li>'
         '<li>성공 확률 success_prob (0.95 캡 적용)</li>'
         '<li>예상 수익률 expected_return, 예상 보유일 expected_hold_days</li>'
         '<li>진입가·목표가·손절가, 리스크/보상 비율 risk_reward_ratio</li>'
         '<li>리스크 점수 risk_score, 총 점수 rec_score(1~100)</li>'
         '<li>판단 근거 rationale (ML 확률·패턴 매칭·수급·시장국면)</li>'
         '</ul>'
         '<p><strong>등급 기준:</strong></p><ul>'
         '<li>🅐 A등급 (rec_score ≥ 80): 높은 신뢰도 — 3요소 모두 강력</li>'
         '<li>🅑 B등급 (60~79): 보통 — 대부분의 매수 신호</li>'
         '<li>🅒 C등급 (40~59): 낮음 — 유사사례 부족 경고</li>'
         '<li>🅓 D등급 (&lt;40): 매우 낮음 — 참고용</li>'
         '</ul>'),

        ("s3-4", "3.4 종목 검색 (Stock Search)", "04_stock_search", "그림 3-4. 종목 검색 화면",
         '<p>종목명 또는 코드로 검색하여 해당 종목의 상세 정보를 조회합니다.</p>'
         '<ul>'
         '<li>기본 정보: 코드·이름·시장·업종·상장주식수·시가총액</li>'
         '<li>일봉 차트 (최근 6개월 캔들 + 20일/60일 이동평균)</li>'
         '<li>실시간 호가 (KIS WebSocket 캐시)</li>'
         '<li>재무 요약: PER·PBR·ROE·EPS (최근 분기 기준)</li>'
         '<li>이벤트 이력: 해당 종목에서 발생한 최근 특징주 이벤트 목록</li>'
         '<li>추천 이력: 해당 종목의 매매 추천 이력과 성과 (1d/3d/5d/10d)</li>'
         '<li>관심종목 추가/삭제 버튼</li>'
         '</ul>'),

        ("s3-5", "3.5 성과 추적 (Performance Tracking)", "05_performance_tracking", "그림 3-5. 성과 추적 화면",
         '<p>모든 매매 추천의 성과를 추적하고 승률·수익률을 집계합니다.</p>'
         '<p><strong>탭 구성:</strong></p><ul>'
         '<li>활성 추적 (Active): tracking_complete=FALSE인 추천 — 진행 중</li>'
         '<li>완료 이력 (History): r_5d NOT NULL인 완료된 추천</li>'
         '<li>요약 통계 (Summary): 승률·평균수익률·목표가 도달률·손절률</li>'
         '<li>이벤트별 성과 (By Event): 이벤트 유형별 승률·평균 수익률</li>'
         '</ul>'
         '<p><strong>각 행 항목:</strong></p><ul>'
         '<li>추천 시점, 종목, 액션, 진입가·목표가·손절가, 성공확률</li>'
         '<li>r_1d / r_3d / r_5d / r_10d: 각 기간 종가 수익률(%)</li>'
         '<li>max_return: 진입 후 최고 수익률</li>'
         '<li>hit_target: 목표가 도달(익절) 여부, hit_stop: 손절가 도달 여부</li>'
         '</ul>'),

        ("s3-6", "3.6 모델 성능 (Model Performance)", "06_model_performance", "그림 3-6. 모델 성능 화면",
         '<p>ML(LightGBM) 모델의 예측 성능을 시각화합니다.</p>'
         '<ul>'
         '<li>AUC (Area Under ROC): 최근 학습 시 검증 AUC (예: 0.6091)</li>'
         '<li>정밀도(Precision) / 재현율(Recall) / F1 스코어</li>'
         '<li>예측 확률 캘리브레이션 곡선</li>'
         '<li>피처 중요도 상위 20개</li>'
         '<li>학습 이력: 재학습 시각·데이터 기간·AUC 추이</li>'
         '<li>이벤트 유형별 정밀도 (14종)</li>'
         '</ul>'
         '<div class="note">💡 재학습은 매 14일·28일 00:00 KST에 auto_retrain.py가 자동 실행합니다.</div>'),

        ("s3-7", "3.7 종목 스크리너 (Screener)", "07_screener", "그림 3-7. 종목 스크리너 화면",
         '<p>다중 조건 AND 조합으로 종목을 필터링합니다. 결과는 2분 캐시됩니다.</p>'
         '<div class="tbl-wrap"><table><thead><tr><th>필터</th><th>타입</th><th>설명</th></tr></thead><tbody>'
         '<tr><td>RSI 최솟값/최댓값</td><td>0~100</td><td>Wilder\'s RSI 14일 기준</td></tr>'
         '<tr><td>52W 신고가 N% 이내</td><td>0~100</td><td>종가가 52주 최고가의 N% 이내</td></tr>'
         '<tr><td>거래량 비율 최솟값</td><td>float</td><td>당일 거래량 ÷ 20일 평균</td></tr>'
         '<tr><td>외국인 N일 연속 순매수</td><td>1~20</td><td>supply_demand.foreign_net > 0</td></tr>'
         '<tr><td>ML 확률 최솟값</td><td>0~1</td><td>signal_data.ml_prob</td></tr>'
         '<tr><td>이벤트 타입</td><td>다중선택</td><td>최근 30일 내 발생</td></tr>'
         '<tr><td>시장</td><td>ALL/KOSPI/KOSDAQ</td><td></td></tr>'
         '<tr><td>PER 상한 / ROE 하한</td><td>float</td><td>재무 기반 필터</td></tr>'
         '</tbody></table></div>'),

        ("s3-8", "3.8 백테스트 (Backtest)", "08_backtest", "그림 3-8. 백테스트 화면",
         '<p>과거 데이터로 특징주 탐지 + 추천 규칙을 시뮬레이션하여 전략을 검증합니다.</p>'
         '<p><strong>입력 파라미터:</strong></p><ul>'
         '<li>기간(시작·종료 날짜)</li>'
         '<li>이벤트 유형 (선택 다중)</li>'
         '<li>최소 시그널 점수 / 최소 ML 확률</li>'
         '<li>포지션 사이즈(원)·최대 동시 포지션 수</li>'
         '<li>익절/손절 정책 (%p 또는 rec 값 사용)</li>'
         '<li>수수료·세금 (bp) — 매수·매도 각 4bp / 매도 세금 20bp 기본</li>'
         '</ul>'
         '<p><strong>출력:</strong></p><ul>'
         '<li>누적 손익 그래프, 자본 곡선</li>'
         '<li>총 거래·승률·평균 수익률·최대 낙폭(MDD)·샤프 지수</li>'
         '<li>이벤트 유형별 성과 breakdown</li>'
         '</ul>'
         '<div class="note">⚡ pandas 핫루프 제거 최적화로 3년치 백테스트가 약 1~2초에 완료됩니다 (84× 개선).</div>'),

        ("s3-9", "3.9 시스템 헬스 (System Health)", "09_system_health", "그림 3-9. 시스템 헬스 화면",
         '<p>각 마이크로서비스의 상태·최근 활동·큐 지연을 실시간으로 확인합니다.</p>'
         '<ul>'
         '<li>컨테이너 상태 (healthy/unhealthy/exited)</li>'
         '<li>각 서비스의 마지막 이벤트 시각 (heartbeat)</li>'
         '<li>Redis Pub/Sub 채널별 최근 메시지 수</li>'
         '<li>DB 커넥션 풀 사용률</li>'
         '<li>수집 지연: 마지막 틱/일봉/뉴스 저장 시각</li>'
         '<li>오류 카운트 (최근 1시간)</li>'
         '</ul>'),

        ("s3-10", "3.10 인텔리전스 (Intel)", "10_intel", "그림 3-10. 인텔리전스 화면",
         '<p>오늘의 시장 스토리를 테마·뉴스·공시로 통합해 보여줍니다.</p>'
         '<ul>'
         '<li>테마 순위: 최근 상승률·거래대금 기준 상위 테마 + 대표 종목</li>'
         '<li>역전 테마: 최근 5일 대비 오늘 순위 급상승 테마</li>'
         '<li>핵심 공시: 유가증권·코스닥 정정공시·주요 사업보고서</li>'
         '<li>뉴스 하이라이트: 언급 종목 클러스터링 + 감성 분석</li>'
         '<li>이슈 발생 종목: 뉴스+공시+이벤트 3중 겹침 종목</li>'
         '</ul>'),

        ("s3-11", "3.11 자동매매 (Trader)", "11_trader", "그림 3-11. 자동매매 화면",
         '<p>KIS OpenAPI를 통한 자동 주문 실행 및 포지션 관리 화면입니다.</p>'
         '<p><strong>탭 구성:</strong></p><ul>'
         '<li>포지션(Position): 현재 보유 종목·평가 손익·목표/손절 도달 여부</li>'
         '<li>주문 이력(Orders): 오늘 발주된 주문·체결 상태</li>'
         '<li>설정: KIS 모드(paper/live)·최대 동시 포지션·1건당 금액 한도</li>'
         '<li>리스크 가드: 일 손실 한도·연속 손실 후 자동 정지</li>'
         '</ul>'
         '<div class="warn">⚠️ <strong>주의:</strong> KIS_MODE=live 설정 시 실계좌로 실제 주문이 발주됩니다. 반드시 paper 모드로 충분히 검증 후 전환하십시오.</div>'),

        ("s3-12", "3.12 관심종목 (Watchlist)", "12_watchlist", "그림 3-12. 관심종목 화면",
         '<p>사용자가 지정한 종목을 별도 리스트로 관리하고 알림을 설정합니다.</p>'
         '<ul>'
         '<li>관심 종목 추가/삭제 (다중 폴더 지원)</li>'
         '<li>종목별 알림 조건: 가격 도달·이벤트 발생·추천 발생</li>'
         '<li>일괄 조회: 현재가·등락률·오늘의 이벤트·최근 추천</li>'
         '<li>메모 필드: 매매 아이디어·근거 기록</li>'
         '</ul>'),

        ("s3-13", "3.13 알림 (Notifications)", "13_notifications", "그림 3-13. 알림 화면",
         '<p>시스템이 발송한 모든 알림 이력을 조회합니다.</p>'
         '<ul>'
         '<li>알림 시각·채널(telegram/email)·수신자·상태(전송/실패)</li>'
         '<li>알림 유형: 매매 추천·특징주 이벤트·시스템 경고·리스크 가드 발동</li>'
         '<li>내용 미리보기 + 원본 페이로드</li>'
         '<li>재전송 버튼 (실패 알림 대상)</li>'
         '</ul>'),

        ("s3-14", "3.14 랭킹 (Ranking)", "14_ranking", "그림 3-14. 랭킹 화면",
         '<p>다양한 지표별 종목 순위를 제공합니다.</p>'
         '<ul>'
         '<li>거래대금 상위 / 거래량 상위</li>'
         '<li>상승률 상위 / 하락률 상위</li>'
         '<li>이벤트 발생 건수 상위 (최근 24시간)</li>'
         '<li>외국인 순매수 상위 / 기관 순매수 상위</li>'
         '<li>ML 확률 상위 / rec_score 상위</li>'
         '</ul>'),

        ("s3-15", "3.15 설정 (Settings)", "15_settings", "그림 3-15. 설정 화면",
         '<p>시스템 파라미터를 관리자 화면에서 조정합니다.</p>'
         '<ul>'
         '<li>탐지 임계값: 이벤트별 시그널 점수 최소치·감쇄 계수</li>'
         '<li>추천 옵션: min_prob·쿨다운(분)·시장국면 감쇄 배율</li>'
         '<li>알림: 텔레그램 봇 토큰/채팅 ID·이메일 SMTP·수신 조건</li>'
         '<li>자동매매: KIS 앱키·계좌·모드·일 손실 한도</li>'
         '<li>재학습: 자동 재학습 요일(14일·28일)·AUC 임계 (0.57)</li>'
         '<li>데이터 관리: 백필 트리거·재수집·오래된 데이터 정리</li>'
         '</ul>'
         '<div class="note">💡 변경한 설정은 즉시 Redis에 반영되어 재기동 없이 적용됩니다.</div>'),
    ]

    for (sec_id, sec_title, img_name, img_cap, body_html) in screens:
        parts.append(f'<h2 id="{sec_id}">{sec_title}</h2>')
        parts.append(img_tag(img_name, img_cap))
        parts.append(body_html)

    # ══════════════════════════════════════════════
    # 4장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch4">4장. 점수 계산 및 추천 알고리즘</h1>')

    parts.append('<h2 id="s4-1">4.1 특징주 탐지 알고리즘</h2>')
    parts.append('<p>각 이벤트는 detector 서비스의 rules/ 모듈에서 독립적으로 평가됩니다.</p>')
    parts.append('''<pre>
VOLUME_SURGE       : today.volume / avg20 >= VOLUME_SURGE_RATIO(default 3.0)
                    AND today.volume >= VOLUME_MIN_ABS(default 100,000)
AMOUNT_SURGE       : today.amount / avg20_amount >= AMOUNT_SURGE_RATIO(default 3.0)
BREAKOUT_52W/26W/13W/20D
                    : today.high >= MAX(high[len_days])
LONG_WHITE_CANDLE  : (close - open)/open >= 0.05 AND (high - close)/close < 0.01
HAMMER_CANDLE      : lower_shadow > 2 * body_size AND upper_shadow < body_size
MORNING_STAR       : 3봉 반전 (하락봉 → 도지 → 강한 상승봉)
VI_TRIGGERED       : KIS VI 알림 수신 시 즉시
SUPPLY_ANOMALY     : abs(foreign_net + inst_net) >= SUPPLY_STD_MULT(3) × σ
POST_DISCLOSURE_SURGE : 공시 후 30분 이내 change_rate >= 5%
SHORT_SURGE        : short_balance / avg30 >= 2.0
DUAL_BUY_STREAK    : N일 연속 foreign_net>0 AND inst_net>0</pre>''')
    parts.append('<p><strong>signal_score(0~1) 구성요소:</strong></p><ul>'
        '<li>기본 조건 초과 비율 (예: 거래량 3배 → 0.5, 5배 → 0.75, 10배 → 1.0)</li>'
        '<li>가격 반응 (change_rate 절대값 클수록 점수↑)</li>'
        '<li>수급 강도 (외국인/기관 순매수 규모)</li>'
        '<li>규모 보정 (log(market_cap) 기반 가중)</li>'
        '</ul>')

    parts.append('<h2 id="s4-2">4.2 매매 추천 점수 계산식 (rec_score)</h2>')
    parts.append('<p>recommender 서비스의 entry_recommender._compute_rec_score() 로직:</p>')
    parts.append('''<pre>
rec_score = ml_component + pattern_component + return_adj − risk_penalty
            (최종 정수, 1~100 사이로 clip)

① ml_component      = (ml_prob / 0.95) × 55                     # 최대 55점
② pattern_component = (min(sim_prob_raw, 0.93) / 0.93) × 30 × w  # 최대 30점
                     w = min(1.0, n_cases / 30.0)   # 유사사례 30건 이상 = 풀 가중
③ return_adj                                                     # -20 ~ +15
     avg_sim_return ≥ 5.0%   → +15
     avg_sim_return ≥ 0.0%   → +8
     avg_sim_return ≥ -3.0%  → 0
     avg_sim_return ≥ -7.0%  → -10
     그 외 (매우 나쁨)        → -20
④ risk_penalty      = min(30, len(risk_factors) × 10)            # 최대 -30점</pre>''')

    parts.append('<h2 id="s4-3">4.3 ML 확률 모델</h2>')
    parts.append('<ul>'
        '<li>알고리즘: LightGBM (gradient boosting)</li>'
        '<li>학습: walk-forward (train 2020~2023 / val 2024 / test 2025)</li>'
        '<li>레이블: 이벤트 발생 후 5일 수익률이 KOSPI 대비 +2%p 이상</li>'
        '<li>피처 수: 71개 (2026-07 기준)</li>'
        '<li>SMOTE로 클래스 불균형 완화</li>'
        '<li>Optuna 30 trial 하이퍼파라미터 튜닝</li>'
        '<li><strong>최근 검증 AUC: 0.6091</strong></li>'
        '</ul>')
    parts.append('''<pre>
가격/거래량: close, open, high, low, volume, amount, change_rate,
              volume_ratio_20, amount_ratio_20, gap_pct
기술 지표:    rsi_14, ma5, ma20, ma60, ma_ratio, macd, bollinger_pos, atr
수급:         foreign_net_5d, foreign_net_20d, inst_net_5d, inst_net_20d,
              retail_net_5d, foreign_hold_rate, short_ratio
재무:         per, pbr, roe, eps_growth, log_market_cap, sector_onehot
시장 국면:    kospi_ma20_dist, vix_kr, regime_dummies
공시/뉴스:    days_since_disclosure, news_sentiment, news_count_7d
과거 이벤트:  event_count_30d, prior_success_rate, similar_case_avg_ret</pre>''')

    parts.append('<h2 id="s4-4">4.4 시장 국면 판단 (KOSPI MA20 기준)</h2>')
    parts.append('''<pre>
pct_from_ma20 = (kospi_close − ma20) / ma20 × 100

phase = 'bear'    if pct_from_ma20 &lt;  REGIME_BEAR_THRESHOLD (-3.0)
      = 'neutral' if pct_from_ma20 &lt;  REGIME_BULL_THRESHOLD (-0.5)
      = 'bull'    otherwise

# 국면별 성공 확률 감쇄
success_prob × 1.00 (bull)
             × 0.88 (neutral)   # REGIME_NEUTRAL_PROB_MULT
             × 0.75 (bear)      # REGIME_BEAR_PROB_MULT

# REGIME_BEAR_SUPPRESS=true → bear 국면에서 추천 발행 자체를 건너뜀</pre>''')

    parts.append('<h2 id="s4-5">4.5 리스크 스코어 계산</h2>')
    parts.append('<p>risk_score(0~1)는 다음 요소를 합산 후 정규화합니다:</p><ul>'
        '<li>변동성(ATR 20일) / 가격 × 100</li>'
        '<li>외국인/기관 순매도 강도</li>'
        '<li>공매도 잔고 급증</li>'
        '<li>최근 5일 최대 낙폭</li>'
        '<li>테마 과열 지표 (연관 종목 동시 급등 후 조정)</li>'
        '<li>재무 취약 (PBR>10 or 부채비율>200%)</li>'
        '</ul>')
    parts.append('<p><code>risk_reward_ratio = (target − entry) / (entry − stop_loss)</code> — 2.0 미만이면 SKIP 처리</p>')

    parts.append('<h2 id="s4-6">4.6 성공 확률 캡 (0.95)</h2>')
    parts.append('<p>과신 방지를 위해 모든 success_prob 값은 하한 0.0, 상한 0.95로 clip됩니다.</p>')
    parts.append('<pre>\n_MAX_PROB = 0.95   # recommendation_service.py\nsuccess_prob = min(_MAX_PROB, float(raw_prob))</pre>')

    # ══════════════════════════════════════════════
    # 5장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch5">5장. 사용 시나리오</h1>')

    parts.append('<h2 id="s5-1">5.1 일반 투자자 시나리오 (아침 루틴)</h2>')
    parts.append('<p>장 개시 전(오전 8:30~9:00)에 시장 상황을 파악하고 오늘 관심 종목을 선정하는 흐름입니다.</p>')
    parts.append('<ol>'
        '<li>브라우저에서 http://localhost:8000 접속 → 대시보드 확인</li>'
        '<li>지수 배지(bull/neutral/bear) 및 섹터 히트맵으로 오늘 강세/약세 섹터 파악</li>'
        '<li>\'신고가 종목\' 카드에서 어제 종가 기준 신고가 이벤트 확인</li>'
        '<li>\'매매 추천\' 메뉴 → dedupe ON, min_prob=0.40, action=BUY 필터</li>'
        '<li>rec_score 80점 이상(A등급) 종목 3~5개를 관심종목으로 등록</li>'
        '<li>장 시작 후 관심종목 화면에서 실시간 등락 관찰</li>'
        '<li>익절/손절 도달 시 알림(텔레그램) 수신 → 판단</li>'
        '</ol>')

    parts.append('<h2 id="s5-2">5.2 단타 트레이더 시나리오</h2>')
    parts.append('<p>장중 실시간 이벤트를 포착해 짧은 호흡의 매매를 진행합니다.</p>')
    parts.append('<ol>'
        '<li>\'특징주 탐지\' 화면 → hours=1, min_score=0.7로 최근 1시간 강한 신호만 조회</li>'
        '<li>VOLUME_SURGE + BREAKOUT_20D가 동시에 발생한 종목 우선 확인</li>'
        '<li>이벤트 클릭 → 유사사례 5건의 이후 15일 차트 검토</li>'
        '<li>매매 추천 화면에서 해당 종목의 추천 상세 확인</li>'
        '<li>risk_reward_ratio ≥ 2.5, success_prob ≥ 0.55 이면 진입 고려</li>'
        '<li>자동매매 사용 중이라면 trader가 자동으로 주문 발주</li>'
        '<li>성과 추적 화면에서 실시간 손익 확인, 목표/손절 도달 시 자동 청산</li>'
        '</ol>')

    parts.append('<h2 id="s5-3">5.3 시스템 관리자 시나리오</h2>')
    parts.append('<ol>'
        '<li>매일 오전 시스템 헬스 대시보드 확인 → 모든 서비스 healthy 상태 검증</li>'
        '<li>수집 지연 5분 초과 시 해당 collector 재시작: docker compose restart collector-xxx</li>'
        '<li>매주 월요일 모델 성능 화면에서 AUC 하락(&lt;0.57) 여부 점검</li>'
        '<li>AUC 하락 시 수동 재학습: docker compose --profile tools run --rm ml-train</li>'
        '<li>매월 백테스트 화면에서 최근 30일 파라미터 검증</li>'
        '<li>설정 화면에서 임계값 미세 조정 후 A/B 비교</li>'
        '</ol>')

    parts.append('<h2 id="s5-4">5.4 데이터 관리자 시나리오</h2>')
    parts.append('<ol>'
        '<li>시스템 헬스에서 특정 종목 last_date가 오래된 경우 확인</li>'
        '<li>개별 재수집: docker compose exec collector-daily python entrypoints/daily_bar_worker.py --code 005930 --once</li>'
        '<li>전체 백필: docker compose --profile backfill up collector-bars-backfill</li>'
        '<li>재무 재수집: docker compose exec collector-financials python entrypoints/financials_worker.py --once</li>'
        '<li>DB 진단: docker compose exec postgres psql -U fstock -d fstock -c "SELECT COUNT(*) FROM daily_bars;"</li>'
        '</ol>')

    # ══════════════════════════════════════════════
    # 6장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch6">6장. FAQ 및 문제 해결</h1>')
    parts.append('<div class="tbl-wrap"><table>'
        '<thead><tr><th>증상</th><th>원인</th><th>해결</th></tr></thead><tbody>'
        '<tr><td>대시보드에 데이터가 표시되지 않음</td><td>초기 데이터 미적재 또는 collector 미기동</td><td>python setup_bootstrap.py 실행 후 docker compose ps 확인</td></tr>'
        '<tr><td>/api/health가 500 오류</td><td>postgres/redis 준비 중</td><td>docker compose logs postgres | tail, 30초~1분 대기 후 재시도</td></tr>'
        '<tr><td>추천이 하나도 뜨지 않음</td><td>bear 국면 + REGIME_BEAR_SUPPRESS=true</td><td>.env에서 false로 변경 후 recommender 재시작</td></tr>'
        '<tr><td>ML 확률이 0.5에 몰림</td><td>모델 미학습 또는 피처 결측</td><td>docker compose --profile tools run --rm ml-train 실행</td></tr>'
        '<tr><td>자동매매가 주문을 내지 않음</td><td>KIS 토큰 만료 또는 리스크 가드 발동</td><td>trader 로그 확인, 필요시 KIS 앱키 재발급 → .env 갱신</td></tr>'
        '<tr><td>섹터 히트맵이 비어 있음</td><td>stocks.sector 미기입</td><td>scripts/refresh_sector.py 실행</td></tr>'
        '<tr><td>프론트엔드 빌드와 불일치</td><td>assets 파일 삭제/이동</td><td>cd frontend && npm run build 재실행</td></tr>'
        '<tr><td>백테스트가 매우 느림</td><td>pandas 핫루프 잔존</td><td>최신 코드(pull) 확인, 커밋 dff88bd 이후 84× 최적화 반영됨</td></tr>'
        '<tr><td>Redis 메모리 부족</td><td>실시간 틱 캐시 폭증</td><td>redis.conf의 maxmemory 상향 또는 collector-tick TTL 조정</td></tr>'
        '<tr><td>Postgres OOM</td><td>shared_buffers 부족</td><td>docker-compose.yml의 postgres 리소스 limits 상향</td></tr>'
        '</tbody></table></div>')

    # ══════════════════════════════════════════════
    # 7장
    # ══════════════════════════════════════════════
    parts.append('<h1 id="ch7">7장. 부록</h1>')

    parts.append('<h2 id="appA">부록 A. 주요 API 엔드포인트</h2>')
    endpoints = [
        ("/api/health", "GET", "API 헬스체크"),
        ("/api/market/summary", "GET", "KOSPI/KOSDAQ 등락 요약"),
        ("/api/market/movers?limit=10", "GET", "상승/하락 상위"),
        ("/api/market/foreign-flow", "GET", "외국인/기관 순매수 상위"),
        ("/api/market/index-live", "GET", "실시간 지수 (KIS)"),
        ("/api/market/sector-heatmap", "GET", "섹터 히트맵"),
        ("/api/market/new-highs?hours=24", "GET", "신고가 종목"),
        ("/api/market/overview", "GET", "대시보드 종합 응답 (통합)"),
        ("/api/features?event_type=&hours=72", "GET", "특징주 이벤트 목록"),
        ("/api/features/types", "GET", "지원 이벤트 타입 14종"),
        ("/api/features/today/summary", "GET", "오늘의 이벤트 요약"),
        ("/api/features/{id}/similar?top_k=10", "GET", "유사 사례"),
        ("/api/features/{id}/similar-with-bars", "GET", "유사 사례 + 캔들"),
        ("/api/recommendations?dedupe=true", "GET", "매매 추천 목록"),
        ("/api/recommendations/buy", "GET", "BUY 추천 최근 20건"),
        ("/api/recommendations/{code}/signals", "GET", "종목별 신호 이력"),
        ("/api/screener/run", "POST", "스크리너 실행"),
        ("/api/stocks/search?q=삼성", "GET", "종목 검색"),
        ("/api/stocks/{code}", "GET", "종목 상세"),
        ("/api/tracking/*", "GET", "성과 추적"),
        ("/api/ml/status", "GET", "모델 상태"),
        ("/api/backtest/run", "POST", "백테스트 실행"),
        ("/api/watchlist", "*", "관심종목 CRUD"),
        ("/api/notifications", "GET", "알림 이력"),
        ("/api/ranking/{type}", "GET", "랭킹"),
        ("/api/trader/positions", "GET", "보유 포지션"),
        ("/api/themes/*", "GET", "테마 정보"),
        ("/api/disclosures", "GET", "공시 목록"),
        ("/api/news", "GET", "뉴스 목록"),
        ("/api/settings/*", "*", "설정 관리"),
    ]
    rows = "".join(f"<tr><td><code>{e}</code></td><td>{m}</td><td>{d}</td></tr>" for e, m, d in endpoints)
    parts.append(f'<div class="tbl-wrap"><table><thead><tr><th>엔드포인트</th><th>메서드</th><th>설명</th></tr></thead><tbody>{rows}</tbody></table></div>')

    parts.append('<h2 id="appB">부록 B. 주요 환경변수</h2>')
    envs = [
        ("POSTGRES_DB / _USER / _PASSWORD", "-", "DB 접속 정보"),
        ("POSTGRES_PORT", "5432", "DB 포트"),
        ("REDIS_PORT", "6379", "Redis 포트"),
        ("API_PORT", "8000", "API + 프론트엔드 포트"),
        ("KIS_APP_KEY / _APP_SECRET", "-", "KIS OpenAPI 인증"),
        ("KIS_ACCOUNT_NO / _CD", "-", "계좌번호/상품코드"),
        ("KIS_MODE", "paper", "paper(모의) / live(실전)"),
        ("DART_API_KEY", "-", "금감원 DART API 키"),
        ("KIND_API_KEY", "-", "KIND API 키"),
        ("GOVDATA_API_KEY", "-", "금융위 시가총액 API 키"),
        ("TELEGRAM_BOT_TOKEN / CHAT_ID", "-", "텔레그램 알림"),
        ("REC_COOLDOWN_MINUTES", "60", "동일 종목 재추천 쿨다운(분)"),
        ("REGIME_BEAR_THRESHOLD", "-3.0", "약세 국면 임계값(%)"),
        ("REGIME_BULL_THRESHOLD", "-0.5", "강세 국면 임계값(%)"),
        ("REGIME_BEAR_SUPPRESS", "true", "약세 국면 추천 억제"),
        ("REGIME_BEAR_PROB_MULT", "0.75", "약세 국면 확률 배수"),
        ("REGIME_NEUTRAL_PROB_MULT", "0.88", "중립 국면 확률 배수"),
        ("ML_MIN_AUC_THRESHOLD", "0.57", "재학습 배포 최소 AUC"),
        ("ML_RETRAIN_DAYS", "14,28", "자동 재학습 일자(월중)"),
        ("BARS_BACKFILL_DAYS", "3285", "일봉 백필 일수(9년)"),
    ]
    rows = "".join(f"<tr><td><code>{k}</code></td><td>{v}</td><td>{d}</td></tr>" for k, v, d in envs)
    parts.append(f'<div class="tbl-wrap"><table><thead><tr><th>환경변수</th><th>기본값</th><th>설명</th></tr></thead><tbody>{rows}</tbody></table></div>')

    parts.append('<h2 id="appC">부록 C. 지원 이벤트 타입 (14종)</h2>')
    parts.append('<pre>\nEVENT_TYPES = [\n  \'VOLUME_SURGE\', \'AMOUNT_SURGE\',\n  \'BREAKOUT_52W\', \'BREAKOUT_26W\', \'BREAKOUT_13W\', \'BREAKOUT_20D\',\n  \'VI_TRIGGERED\', \'LONG_WHITE_CANDLE\', \'HAMMER_CANDLE\', \'MORNING_STAR\',\n  \'SUPPLY_ANOMALY\', \'POST_DISCLOSURE_SURGE\',\n  \'SHORT_SURGE\', \'DUAL_BUY_STREAK\',\n]</pre>')

    parts.append('<h2 id="appD">부록 D. Redis Pub/Sub 채널</h2>')
    parts.append('<div class="tbl-wrap"><table>'
        '<thead><tr><th>채널</th><th>발행자</th><th>구독자</th><th>페이로드</th></tr></thead><tbody>'
        '<tr><td>ch:feature</td><td>detector</td><td>analyzer, api</td><td>feature_event_id, code, event_type, signal_score</td></tr>'
        '<tr><td>ch:recommendation</td><td>recommender</td><td>trader, notifier, api</td><td>rec_id, code, action, success_prob, prices</td></tr>'
        '<tr><td>ch:trade_result</td><td>trader</td><td>recommender, api</td><td>order_id, code, status, filled_qty, price</td></tr>'
        '<tr><td>ch:alert</td><td>notifier</td><td>—</td><td>channel, target, message, ts</td></tr>'
        '</tbody></table></div>')

    parts.append('<h2 id="appE">부록 E. Docker Compose 프로파일</h2>')
    parts.append('<div class="tbl-wrap"><table>'
        '<thead><tr><th>프로파일</th><th>실행 명령</th><th>용도</th></tr></thead><tbody>'
        '<tr><td>(기본)</td><td><code>docker compose up -d</code></td><td>상시 운영 서비스</td></tr>'
        '<tr><td>backfill</td><td><code>docker compose --profile backfill up</code></td><td>9년치 일봉 재백필</td></tr>'
        '<tr><td>tools</td><td><code>docker compose --profile tools run --rm ml-train</code></td><td>ML 학습·수동 백필</td></tr>'
        '<tr><td>monitoring</td><td><code>docker compose --profile monitoring up -d</code></td><td>Prometheus + Grafana</td></tr>'
        '</tbody></table></div>')

    return "\n".join(parts)


# ─── HTML 조립 ────────────────────────────────────────────────────────────────
body = build_body()
html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Quant Eye 사용자 매뉴얼 v1.0</title>
<style>{CSS}</style>
</head>
<body>
{SIDEBAR}
<div id="content">
{body}
</div>
<script>{JS}</script>
</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(OUT) / 1024
print(f"OK: {OUT}")
print(f"크기: {size_kb:.1f} KB")
