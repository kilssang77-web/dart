"""
경량 웹 대시보드 — FastAPI + Jinja2 (GCP e2-micro 단독 실행)
포트: 8080 (systemd: dashboard.service)

라우트:
  GET /           — 최근 추천 목록
  GET /performance — 30일 성과 요약
  GET /status      — 시스템 상태
  GET /api/recs    — JSON (Telegram봇 동일 데이터)
  GET /api/status  — JSON

실행: python dashboard.py  또는  uvicorn dashboard:app --host 0.0.0.0 --port 8080
환경변수: POSTGRES_DSN, DASHBOARD_SECRET (설정 시 ?key= 쿼리 인증)
"""
import asyncio
import asyncpg
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dashboard")

KST    = timezone(timedelta(hours=9))
DSN    = os.environ["POSTGRES_DSN"]
SECRET = os.environ.get("DASHBOARD_SECRET", "")  # 빈 문자열 = 인증 없음

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DSN, min_size=1, max_size=3, statement_cache_size=0,
        )
    return _pool


@asynccontextmanager
async def lifespan(application: FastAPI):
    await get_pool()
    log.info("DB 풀 초기화 완료")
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="KOSPI Quant Dashboard", lifespan=lifespan, docs_url=None, redoc_url=None)


# ── 인증 ─────────────────────────────────────────────────────

def check_auth(request: Request) -> None:
    if not SECRET:
        return
    key = request.query_params.get("key", "")
    if key != SECRET:
        raise HTTPException(status_code=403, detail="인증 필요 (?key=...)")


# ── HTML 공통 ─────────────────────────────────────────────────

_CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif;
       background: #0f172a; color: #e2e8f0; min-height: 100vh; }
header { background: #1e293b; padding: 1rem 2rem; border-bottom: 1px solid #334155;
         display: flex; align-items: center; gap: 1rem; }
header h1 { font-size: 1.2rem; font-weight: 700; color: #38bdf8; }
nav a { color: #94a3b8; text-decoration: none; margin-left: 1.5rem; font-size: 0.9rem; }
nav a:hover { color: #e2e8f0; }
.container { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 0.75rem;
        padding: 1.5rem; margin-bottom: 1.5rem; }
.card h2 { font-size: 1rem; font-weight: 600; color: #94a3b8; margin-bottom: 1rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th { text-align: left; padding: 0.5rem 0.75rem; color: #64748b;
     border-bottom: 1px solid #334155; font-weight: 500; }
td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b; }
tr:hover td { background: #0f172a; }
.badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 0.25rem;
         font-size: 0.75rem; font-weight: 600; }
.up   { color: #4ade80; }
.down { color: #f87171; }
.prob-hi { background: #064e3b; color: #4ade80; }
.prob-md { background: #1e3a5f; color: #60a5fa; }
.prob-lo { background: #3f2a0a; color: #fbbf24; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; }
.stat-box { background: #0f172a; border-radius: 0.5rem; padding: 1rem; text-align: center; }
.stat-box .val { font-size: 1.8rem; font-weight: 700; color: #38bdf8; }
.stat-box .lbl { font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }
footer { text-align: center; color: #475569; font-size: 0.75rem; padding: 2rem; }
</style>
"""

_NAV = """
<header>
  <h1>📈 KOSPI Quant</h1>
  <nav>
    <a href="/{q}">추천 목록</a>
    <a href="/performance{q}">성과</a>
    <a href="/status{q}">상태</a>
  </nav>
</header>
"""


def _page(title: str, body: str, request: Request) -> str:
    q = f"?key={SECRET}" if SECRET else ""
    nav = _NAV.replace("{q}", q)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — KOSPI Quant</title>{_CSS}</head>
<body>
{nav}
<div class="container">{body}</div>
<footer>Auto-refresh 60s &nbsp;|&nbsp; {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}</footer>
<script>setTimeout(()=>location.reload(), 60000);</script>
</body></html>"""


def _prob_class(p: float) -> str:
    if p >= 0.50: return "prob-hi"
    if p >= 0.35: return "prob-md"
    return "prob-lo"


# ── DB 조회 ───────────────────────────────────────────────────

async def q_recs(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT r.code, COALESCE(s.name, r.code) AS name,
                   r.success_prob, r.risk_score, r.entry_price,
                   r.actual_return, r.is_success,
                   r.created_at AT TIME ZONE 'Asia/Seoul' AS kst_time
            FROM recommendations r
            LEFT JOIN stocks s ON s.code = r.code
            WHERE r.action = 'BUY'
              AND r.created_at >= NOW() - INTERVAL '48 hours'
            ORDER BY r.created_at DESC
            LIMIT 50
        """)
    return [dict(r) for r in rows]


async def q_perf(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*)                                             AS total,
                SUM(CASE WHEN is_success THEN 1 ELSE 0 END)        AS success_cnt,
                AVG(actual_return)                                   AS avg_ret,
                MAX(actual_return)                                   AS max_ret,
                MIN(actual_return)                                   AS min_ret,
                SUM(CASE WHEN actual_return IS NULL THEN 1 ELSE 0 END) AS pending_cnt
            FROM recommendations
            WHERE action = 'BUY'
              AND created_at >= NOW() - INTERVAL '30 days'
        """)
        recent = await conn.fetch("""
            SELECT r.code, COALESCE(s.name, r.code) AS name,
                   r.actual_return, r.is_success,
                   r.created_at AT TIME ZONE 'Asia/Seoul' AS kst_time
            FROM recommendations r
            LEFT JOIN stocks s ON s.code = r.code
            WHERE r.action = 'BUY' AND r.actual_return IS NOT NULL
              AND r.created_at >= NOW() - INTERVAL '30 days'
            ORDER BY r.created_at DESC
            LIMIT 20
        """)
    return {"stats": dict(row), "recent": [dict(r) for r in recent]}


async def q_status(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        last_rec = await conn.fetchval(
            "SELECT MAX(created_at) AT TIME ZONE 'Asia/Seoul' FROM recommendations WHERE action='BUY'"
        )
        bar_cnt  = await conn.fetchval("SELECT COUNT(*) FROM daily_bars")
        rec_cnt  = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE action='BUY'")
        stk_cnt  = await conn.fetchval("SELECT COUNT(*) FROM stocks WHERE is_active=true")
        pending  = await conn.fetchval(
            "SELECT COUNT(*) FROM recommendations WHERE action='BUY' AND actual_return IS NULL AND created_at < NOW() - INTERVAL '5 days'"
        )
    dyn_cfg = Path(os.path.expanduser("~/quant/dynamic_config.json"))
    thr_info = {}
    if dyn_cfg.exists():
        try:
            thr_info = json.loads(dyn_cfg.read_text())
        except Exception:
            pass
    return {
        "last_rec":   last_rec.strftime("%Y-%m-%d %H:%M") if last_rec else "없음",
        "bar_cnt":    bar_cnt,
        "rec_cnt":    rec_cnt,
        "stk_cnt":    stk_cnt,
        "pending":    pending,
        "threshold":  thr_info.get("score_threshold", "—"),
        "recent_rate": thr_info.get("recent_rate"),
    }


# ── 라우트 ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def page_recs(request: Request):
    check_auth(request)
    pool = await get_pool()
    recs = await q_recs(pool)

    rows_html = ""
    for r in recs:
        t     = r["kst_time"].strftime("%m/%d %H:%M")
        prob  = r["success_prob"]
        risk  = r["risk_score"]
        ret   = r["actual_return"]
        price = r["entry_price"]
        ret_html = (
            f'<span class="{"up" if ret >= 0 else "down"}">{ret:+.1f}%</span>'
            if ret is not None else '<span style="color:#64748b">평가중</span>'
        )
        rows_html += f"""
        <tr>
          <td>{t}</td>
          <td><b>{r['name']}</b></td>
          <td style="color:#94a3b8">{r['code']}</td>
          <td><span class="badge {_prob_class(prob)}">{prob:.1%}</span></td>
          <td style="color:#fbbf24">{risk:.0%}</td>
          <td>₩{price:,}</td>
          <td>{ret_html}</td>
        </tr>"""

    body = f"""
    <div class="card">
      <h2>최근 48시간 BUY 추천 ({len(recs)}건)</h2>
      <table>
        <thead><tr>
          <th>시각</th><th>종목</th><th>코드</th>
          <th>성공확률</th><th>위험</th><th>매수가</th><th>수익률</th>
        </tr></thead>
        <tbody>{rows_html if rows_html else '<tr><td colspan="7" style="text-align:center;color:#64748b;padding:2rem">추천 없음</td></tr>'}</tbody>
      </table>
    </div>"""
    return HTMLResponse(_page("추천 목록", body, request))


@app.get("/performance", response_class=HTMLResponse)
async def page_perf(request: Request):
    check_auth(request)
    pool = await get_pool()
    data = await q_perf(pool)
    s    = data["stats"]
    total   = int(s["total"] or 0)
    success = int(s["success_cnt"] or 0)
    pending = int(s["pending_cnt"] or 0)
    evaluated = total - pending
    rate    = success / evaluated if evaluated > 0 else 0
    avg_r   = float(s["avg_ret"] or 0)
    max_r   = float(s["max_ret"] or 0)
    min_r   = float(s["min_ret"] or 0)

    rows_html = ""
    for r in data["recent"]:
        ret  = r["actual_return"]
        ok   = r["is_success"]
        icon = "✅" if ok else "❌"
        rows_html += f"""
        <tr>
          <td>{r['kst_time'].strftime('%m/%d')}</td>
          <td><b>{r['name']}</b> ({r['code']})</td>
          <td><span class="{"up" if ret >= 0 else "down"}">{ret:+.2f}%</span></td>
          <td>{icon}</td>
        </tr>"""

    body = f"""
    <div class="card">
      <h2>최근 30일 성과 요약</h2>
      <div class="stat-grid">
        <div class="stat-box"><div class="val">{total}</div><div class="lbl">총 추천</div></div>
        <div class="stat-box"><div class="val">{evaluated}</div><div class="lbl">평가 완료</div></div>
        <div class="stat-box"><div class="val" style="color:#4ade80">{rate:.0%}</div><div class="lbl">성공률</div></div>
        <div class="stat-box"><div class="val" style="color:{'#4ade80' if avg_r>=0 else '#f87171'}">{avg_r:+.2f}%</div><div class="lbl">평균 수익</div></div>
        <div class="stat-box"><div class="val" style="color:#4ade80">{max_r:+.2f}%</div><div class="lbl">최대</div></div>
        <div class="stat-box"><div class="val" style="color:#f87171">{min_r:+.2f}%</div><div class="lbl">최소</div></div>
      </div>
    </div>
    <div class="card">
      <h2>최근 결산 내역</h2>
      <table>
        <thead><tr><th>날짜</th><th>종목</th><th>수익률</th><th>결과</th></tr></thead>
        <tbody>{rows_html if rows_html else '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:2rem">데이터 없음</td></tr>'}</tbody>
      </table>
    </div>"""
    return HTMLResponse(_page("성과", body, request))


@app.get("/status", response_class=HTMLResponse)
async def page_status(request: Request):
    check_auth(request)
    pool = await get_pool()
    d    = await q_status(pool)

    rate_str = f"{d['recent_rate']:.0%}" if d["recent_rate"] is not None else "—"
    body = f"""
    <div class="card">
      <h2>시스템 상태</h2>
      <div class="stat-grid">
        <div class="stat-box"><div class="val" style="color:#4ade80">✅</div><div class="lbl">DB 연결</div></div>
        <div class="stat-box"><div class="val">{d['stk_cnt']:,}</div><div class="lbl">활성 종목</div></div>
        <div class="stat-box"><div class="val">{d['bar_cnt']:,}</div><div class="lbl">일봉 행수</div></div>
        <div class="stat-box"><div class="val">{d['rec_cnt']:,}</div><div class="lbl">총 추천</div></div>
        <div class="stat-box"><div class="val">{d['pending']:,}</div><div class="lbl">성과 평가 대기</div></div>
      </div>
    </div>
    <div class="card">
      <h2>운영 정보</h2>
      <table>
        <tbody>
          <tr><td style="color:#64748b;width:180px">마지막 추천</td><td>{d['last_rec']} KST</td></tr>
          <tr><td style="color:#64748b">ML 임계값</td><td>{d['threshold']}</td></tr>
          <tr><td style="color:#64748b">최근 30일 성공률</td><td>{rate_str}</td></tr>
          <tr><td style="color:#64748b">현재 시각</td><td>{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}</td></tr>
        </tbody>
      </table>
    </div>"""
    return HTMLResponse(_page("상태", body, request))


# ── JSON API ────────────────────────────────────────────────

@app.get("/api/recs")
async def api_recs(request: Request):
    check_auth(request)
    pool = await get_pool()
    recs = await q_recs(pool)
    return JSONResponse([
        {
            "code":         r["code"],
            "name":         r["name"],
            "success_prob": r["success_prob"],
            "risk_score":   r["risk_score"],
            "entry_price":  r["entry_price"],
            "actual_return": r["actual_return"],
            "is_success":   r["is_success"],
            "kst_time":     r["kst_time"].isoformat(),
        }
        for r in recs
    ])


@app.get("/api/status")
async def api_status(request: Request):
    check_auth(request)
    pool = await get_pool()
    return JSONResponse(await q_status(pool))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
