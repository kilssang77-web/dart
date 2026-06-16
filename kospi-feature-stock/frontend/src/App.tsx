import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Sidebar } from './components/Layout/Sidebar'
import { TopBar } from './components/Layout/TopBar'
import { SystemBanner } from './components/Layout/SystemBanner'
import { useIsMobile } from './hooks/useMediaQuery'
import { useSidebarStore } from './store/sidebar'
import { useRealtimeStream } from './hooks/useRealtimeStream'
import { marketApi } from './api/market'

const Dashboard      = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const Features       = lazy(() => import('./pages/Features').then((m) => ({ default: m.Features })))
const Recommendations= lazy(() => import('./pages/Recommendations').then((m) => ({ default: m.Recommendations })))
const Intel          = lazy(() => import('./pages/Intel').then((m) => ({ default: m.Intel })))
const StockSearch    = lazy(() => import('./pages/StockSearch').then((m) => ({ default: m.StockSearch })))
const Backtest       = lazy(() => import('./pages/Backtest').then((m) => ({ default: m.Backtest })))
const ModelPerf      = lazy(() => import('./pages/ModelPerformance').then((m) => ({ default: m.ModelPerformance })))
const Settings       = lazy(() => import('./pages/Settings').then((m) => ({ default: m.Settings })))
const StockAnalysis  = lazy(() => import('./pages/StockAnalysis').then((m) => ({ default: m.StockAnalysis })))
const Watchlist      = lazy(() => import('./pages/Watchlist').then((m) => ({ default: m.Watchlist })))
const SystemHealth   = lazy(() => import('./pages/SystemHealth').then((m) => ({ default: m.SystemHealth })))

const META: Record<string, { title: string; subtitle?: string }> = {
  '/':               { title: '대시보드',    subtitle: '실시간 특징주 현황 요약' },
  '/features':       { title: '특징주 탐지', subtitle: '이벤트 기반 특징주 목록' },
  '/recommendations':{ title: '매매 추천',   subtitle: 'ML 기반 매수 신호 및 목표가' },
  '/intel':          { title: '정보 센터',   subtitle: '공시 · 뉴스 · 테마 통합 분석' },
  '/search':         { title: '종목 분석',   subtitle: '종목 상세 정보 · 차트 · 추천 · 유사사례' },
  '/watchlist':      { title: '관심종목',    subtitle: '즐겨찾기 종목 모니터링' },
  '/backtest':       { title: '백테스트',    subtitle: '이벤트 전략 기간별 성과 검증' },
  '/performance':    { title: '모델 성능',   subtitle: 'LightGBM AUC · F1 · 피처 중요도' },
  '/settings':       { title: '설정',        subtitle: '시스템 파라미터 · API 연결 관리' },
  '/analysis':       { title: '종목 분석',   subtitle: '주가 예측 · 매수/매도 전략 추천' },
  '/system-health':  { title: '시스템 헬스', subtitle: 'ML 모델 · DB · Kafka · 데이터 신선도 전체 현황' },
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

function getLastTradingDay(): string {
  // en-CA locale → 'YYYY-MM-DD' 형식으로 서울 기준 날짜 취득
  const seoulDateStr = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
  const [y, m, d] = seoulDateStr.split('-').map(Number)
  const seoulDate = new Date(y, m - 1, d)
  const dow = seoulDate.getDay() // 0=일, 6=토
  const daysBack = dow === 0 ? 2 : dow === 6 ? 1 : 0
  seoulDate.setDate(d - daysBack)
  // 다시 YYYY-MM-DD 형식으로 반환
  return seoulDate.toLocaleDateString('en-CA')
}

function MarketClosedBanner() {
  const { data } = useQuery({
    queryKey:        ['market-summary-banner'],
    queryFn:         marketApi.getSummary,
    staleTime:       600_000,
    refetchInterval: 600_000,
  })
  if (!data?.data_date) return null

  const lastTradingDay = getLastTradingDay()
  if (data.data_date >= lastTradingDay) return null

  // 오늘이 거래일이고 EOD 수집 완료(16:30 KST) 전이면 정상 — 배너 숨김
  const seoulNow    = new Date().toLocaleTimeString('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' })
  const todayIsWeekday = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' }) === lastTradingDay
  if (todayIsWeekday && seoulNow < '16:30') return null

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 border-b border-amber-500/30 text-amber-400 text-sm">
      <AlertTriangle size={14} className="shrink-0" />
      <span>
        일봉 데이터 미갱신 ({data.data_date}). EOD 수집이 지연되고 있습니다.
      </span>
    </div>
  )
}

export default function App() {
  const { pathname }  = useLocation()
  const { collapsed } = useSidebarStore()
  const isMobile      = useIsMobile()
  const meta = META[pathname] ?? { title: pathname.slice(1) || '대시보드' }
  const ml   = isMobile ? 0 : collapsed ? 56 : 220

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      <GlobalRealtimeStream />
      <Sidebar />

      <div
        className="main-content flex-1 flex flex-col min-w-0 transition-all duration-200"
        style={{ marginLeft: ml }}
      >
        <TopBar title={meta.title} subtitle={meta.subtitle} />
        <SystemBanner />
        <MarketClosedBanner />

        <main className="flex-1 overflow-auto">
          <Suspense fallback={<Spinner />}>
            <Routes>
              <Route path="/"                element={<Dashboard />} />
              <Route path="/features"        element={<Features />} />
              <Route path="/recommendations" element={<Recommendations />} />
              <Route path="/intel"           element={<Intel />} />
              <Route path="/search"          element={<StockSearch />} />
              <Route path="/watchlist"       element={<Watchlist />} />
              <Route path="/backtest"        element={<Backtest />} />
              <Route path="/performance"     element={<ModelPerf />} />
              <Route path="/settings"        element={<Settings />} />
              <Route path="/analysis"        element={<StockAnalysis />} />
              <Route path="/system-health"   element={<SystemHealth />} />
              {/* 제거된 라우트 → /intel 리다이렉트 */}
              <Route path="/disclosures"     element={<Navigate to="/intel" replace />} />
              <Route path="/news"            element={<Navigate to="/intel" replace />} />
              <Route path="/themes"          element={<Navigate to="/intel" replace />} />
              <Route path="/similar-cases"         element={<Navigate to="/search" replace />} />
              <Route path="/similar-cases/:eventId" element={<Navigate to="/search" replace />} />
              <Route path="/hts"             element={<Navigate to="/" replace />} />
              <Route path="/notifications"   element={<Navigate to="/" replace />} />
              <Route path="/bootstrap"       element={<Navigate to="/" replace />} />
              <Route path="/tracking"        element={<Navigate to="/" replace />} />
              <Route path="/perf-tracking"   element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  )
}
