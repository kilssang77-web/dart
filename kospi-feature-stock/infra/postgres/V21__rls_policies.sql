-- ══════════════════════════════════════════════════════════════
-- V21: Row-Level Security 활성화 (Supabase 보안 취약점 해소)
--
-- 목적: Supabase REST API(PostgREST)를 통한 anon 직접 접근 차단
--
-- 접근 모델:
--   - 백엔드(asyncpg, postgres role) → BYPASSRLS → 영향 없음
--   - Supabase PostgREST(anon/authenticated) → RLS 적용 → 기본 거부
--
-- 정책 없음(no POLICY) = 해당 역할에서 모든 접근 거부 (Supabase 기본값)
-- 백엔드는 postgres superuser로 연결하므로 이 변경에 영향받지 않음
-- ══════════════════════════════════════════════════════════════

-- ── 시장 데이터 ───────────────────────────────────────────────
ALTER TABLE IF EXISTS stocks               ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS daily_bars           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS minute_bars          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tick_data            ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS supply_demand        ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS financials           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS kr_holidays          ENABLE ROW LEVEL SECURITY;

-- ── 공시 / 뉴스 ──────────────────────────────────────────────
ALTER TABLE IF EXISTS disclosures          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS disclosure_filters   ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS news                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS news_stock_links     ENABLE ROW LEVEL SECURITY;

-- ── 탐지 / 추천 ──────────────────────────────────────────────
ALTER TABLE IF EXISTS feature_events               ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS recommendations              ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS recommendation_performance   ENABLE ROW LEVEL SECURITY;

-- ── 트레이더 (민감 — 매매 설정·주문·포지션) ─────────────────
ALTER TABLE IF EXISTS trader_settings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS orders               ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS positions            ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS daily_pnl            ENABLE ROW LEVEL SECURITY;

-- ── 사용자 데이터 ─────────────────────────────────────────────
ALTER TABLE IF EXISTS watchlist            ENABLE ROW LEVEL SECURITY;

-- ── 시스템 / 운영 ─────────────────────────────────────────────
ALTER TABLE IF EXISTS ml_models            ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS system_logs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS telegram_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS redis_stats_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS backfill_history     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS backtest_results     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS theme_snapshots      ENABLE ROW LEVEL SECURITY;
