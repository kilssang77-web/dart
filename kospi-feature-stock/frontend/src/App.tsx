import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Sidebar } from './components/Layout/Sidebar'
import { TopBar } from './components/Layout/TopBar'
import { SystemBanner } from './components/Layout/SystemBanner'
import { useIsMobile } from './hooks/useMediaQuery'
import { useSidebarStore } from './store/sidebar'
import { useRealtimeStream } from './hooks/useRealtimeStream'

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
const SystemHealth         = lazy(() => import('./pages/SystemHealth').then((m) => ({ default: m.SystemHealth })))
const NotificationHistory  = lazy(() => import('./pages/NotificationHistory').then((m) => ({ default: m.NotificationHistory })))
const RecJourney           = lazy(() => import('./pages/RecommendationJourney').then((m) => ({ default: m.RecommendationJourney })))
const SimilarCases         = lazy(() => import('./pages/SimilarCases').then((m) => ({ default: m.SimilarCases })))
const PositionManagement   = lazy(() => import('./pages/PositionManagement').then((m) => ({ default: m.PositionManagement })))

const META: Record<string, { title: string; subtitle?: string }> = {
  '/':               { title: '대시보드',    subtitle: '실시간 특징주 현황 요약' },
  '/features':       { title: '특징주 탐지', subtitle: '이벤트 기반 특징주 목록' },
  '/recommendations':{ title: '매매 추천',   subtitle: 'ML 기반 매수 신호 및 목표가' },
  '/intel':          { title: '공시/뉴스',   subtitle: '공시 · 뉴스 · 테마 통합 분석' },
  '/search':         { title: '종목 검색',   subtitle: '종목 상세 정보 · 차트 · 추천 · 유사사례' },
  '/watchlist':      { title: '관심종목',    subtitle: '즐겨찾기 종목 모니터링' },
  '/backtest':       { title: '백테스트',    subtitle: '이벤트 전략 기간별 성과 검증' },
  '/performance':    { title: '모델 성능',   subtitle: 'LightGBM AUC · F1 · 피처 중요도' },
  '/settings':       { title: '설정',        subtitle: '시스템 파라미터 · API 연결 관리' },
  '/analysis':       { title: '종목 분석',   subtitle: '주가 예측 · 매수/매도 전략 추천' },
  '/system-health':  { title: '시스템 헬스',  subtitle: 'ML 모델 · DB · Kafka · 데이터 신선도 전체 현황' },
  '/notifications':  { title: '발송 이력',   subtitle: '텔레그램 발송 내역 · 매수신호 · 공시' },
  '/rec-journey':    { title: '성과 추적',    subtitle: '매수 추천 시점 이후 시간대별 주가 여정 · ML 재학습 피드백' },
  '/similar-cases':  { title: '유사사례',    subtitle: '과거 동일 패턴 종목 · 이벤트 기준 수익률 비교' },
  '/positions':      { title: '포지션 관리', subtitle: '추적 중 포지션 · 보유/손익 현황' },
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
              <Route path="/notifications"   element={<NotificationHistory />} />
              <Route path="/rec-journey"    element={<RecJourney />} />
              <Route path="/similar-cases"          element={<SimilarCases />} />
              <Route path="/similar-cases/:eventId" element={<SimilarCases />} />
              <Route path="/positions"              element={<PositionManagement />} />
              {/* 제거된 라우트 → 리다이렉트 */}
              <Route path="/disclosures"     element={<Navigate to="/intel" replace />} />
              <Route path="/news"            element={<Navigate to="/intel" replace />} />
              <Route path="/themes"          element={<Navigate to="/intel" replace />} />
              <Route path="/hts"             element={<Navigate to="/" replace />} />
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
