import { Suspense, lazy } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Sidebar } from './components/Layout/Sidebar'
import { TopBar } from './components/Layout/TopBar'
import { useSidebarStore } from './store/sidebar'
import { useRealtimeStream } from './hooks/useRealtimeStream'
import { marketApi } from './api/market'

const Dashboard      = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const Features       = lazy(() => import('./pages/Features').then((m) => ({ default: m.Features })))
const Recommendations= lazy(() => import('./pages/Recommendations').then((m) => ({ default: m.Recommendations })))
const Disclosures    = lazy(() => import('./pages/Disclosures').then((m) => ({ default: m.Disclosures })))
const News           = lazy(() => import('./pages/News').then((m) => ({ default: m.News })))
const StockSearch    = lazy(() => import('./pages/StockSearch').then((m) => ({ default: m.StockSearch })))
const HTS            = lazy(() => import('./pages/HTS').then((m) => ({ default: m.HTS })))
const Backtest       = lazy(() => import('./pages/Backtest').then((m) => ({ default: m.Backtest })))
const ModelPerf      = lazy(() => import('./pages/ModelPerformance').then((m) => ({ default: m.ModelPerformance })))
const Settings       = lazy(() => import('./pages/Settings').then((m) => ({ default: m.Settings })))
const StockAnalysis  = lazy(() => import('./pages/StockAnalysis').then((m) => ({ default: m.StockAnalysis })))
const Watchlist      = lazy(() => import('./pages/Watchlist').then((m) => ({ default: m.Watchlist })))
const NotifHistory   = lazy(() => import('./pages/NotificationHistory').then((m) => ({ default: m.NotificationHistory })))
const Tracking       = lazy(() => import('./pages/Tracking').then((m) => ({ default: m.Tracking })))

const META: Record<string, { title: string; subtitle?: string }> = {
  '/':               { title: '대시보드',    subtitle: '실시간 특징주 현황 요약' },
  '/features':       { title: '특징주 탐지', subtitle: '이벤트 기반 특징주 목록' },
  '/recommendations':{ title: '추천 매매',   subtitle: 'ML 기반 매수 신호 및 목표가' },
  '/disclosures':    { title: '공시 분석',   subtitle: 'DART 공시 감성 분석' },
  '/news':           { title: '뉴스/테마',   subtitle: '뉴스 흐름 & K-Means 테마 클러스터' },
  '/search':         { title: '종목 검색',   subtitle: '종목 상세 정보 · 차트 · 추천' },
  '/analysis':       { title: '종목 분석',   subtitle: '주가 예측 · 매수/매도 전략 추천' },
  '/hts':            { title: 'HTS 시세판',  subtitle: '실시간 호가 · 체결 현황' },
  '/backtest':       { title: '백테스트',    subtitle: '이벤트 전략 기간별 성과 검증' },
  '/performance':    { title: '모델 성능',   subtitle: 'LightGBM AUC · F1 · 피처 중요도' },
  '/watchlist':      { title: '관심종목',  subtitle: '즐겨찾기 종목 모니터링' },
  '/settings':       { title: '설정',        subtitle: '시스템 파라미터 · API 연결 관리' },
  '/notifications':   { title: '텔레그램 이력', subtitle: '알림 발송 이력 조회' },
  '/tracking':         { title: '성과 추적', subtitle: '추천 종목 사후 수익률 · 이벤트별 성공률 분석' },
}

function Spinner() {
  return (
    <div className="flex items-center justify-center h-48 text-[var(--muted)]">
      <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>
  )
}

function GlobalRealtimeStream() {
  useRealtimeStream({ invalidateQueries: true })
  return null
}

function MarketClosedBanner() {
  const { data } = useQuery({
    queryKey:        ['market-summary-banner'],
    queryFn:         marketApi.getSummary,
    staleTime:       600_000,
    refetchInterval: 600_000,
  })
  if (!data?.data_date) return null

  // 서울 기준 오늘 날짜와 비교
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
  if (data.data_date >= today) return null

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 border-b border-amber-500/30 text-amber-400 text-sm">
      <AlertTriangle size={14} className="shrink-0" />
      <span>
        마지막 거래일 기준 데이터입니다 ({data.data_date}). 장 휴장 중이거나 거래 전 시간대일 수 있습니다.
      </span>
    </div>
  )
}

export default function App() {
  const { pathname }  = useLocation()
  const { collapsed } = useSidebarStore()
  const meta = META[pathname] ?? { title: pathname.slice(1) || '대시보드' }
  const ml   = collapsed ? 56 : 220

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      <GlobalRealtimeStream />
      <Sidebar />

      <div
        className="main-content flex-1 flex flex-col min-w-0 transition-all duration-200"
        style={{ marginLeft: ml }}
      >
        <TopBar title={meta.title} subtitle={meta.subtitle} />
        <MarketClosedBanner />

        <main className="flex-1 overflow-auto">
          <Suspense fallback={<Spinner />}>
            <Routes>
              <Route path="/"                element={<Dashboard />} />
              <Route path="/features"        element={<Features />} />
              <Route path="/recommendations" element={<Recommendations />} />
              <Route path="/disclosures"     element={<Disclosures />} />
              <Route path="/news"            element={<News />} />
              <Route path="/search"          element={<StockSearch />} />
              <Route path="/hts"             element={<HTS />} />
              <Route path="/backtest"        element={<Backtest />} />
              <Route path="/performance"     element={<ModelPerf />} />
              <Route path="/analysis"        element={<StockAnalysis />} />
              <Route path="/watchlist"       element={<Watchlist />} />
              <Route path="/settings"        element={<Settings />} />
              <Route path="/notifications"   element={<NotifHistory />} />
              <Route path="/tracking"         element={<Tracking />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  )
}
