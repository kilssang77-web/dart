import { Suspense, lazy } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { Sidebar } from './components/Layout/Sidebar'
import { TopBar } from './components/Layout/TopBar'
import { useSidebarStore } from './store/sidebar'

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

const META: Record<string, { title: string; subtitle?: string }> = {
  '/':               { title: '대시보드',    subtitle: '실시간 특징주 현황 요약' },
  '/features':       { title: '특징주 탐지', subtitle: '이벤트 기반 특징주 목록' },
  '/recommendations':{ title: '추천 매매',   subtitle: 'ML 기반 매수 신호 및 목표가' },
  '/disclosures':    { title: '공시 분석',   subtitle: 'DART 공시 감성 분석' },
  '/news':           { title: '뉴스/테마',   subtitle: '뉴스 흐름 & K-Means 테마 클러스터' },
  '/search':         { title: '종목 검색',   subtitle: '종목 상세 정보 · 차트 · 추천' },
  '/hts':            { title: 'HTS 시세판',  subtitle: '실시간 호가 · 체결 현황' },
  '/backtest':       { title: '백테스트',    subtitle: '이벤트 전략 기간별 성과 검증' },
  '/performance':    { title: '모델 성능',   subtitle: 'LightGBM AUC · F1 · 피처 중요도' },
  '/settings':       { title: '설정',        subtitle: '시스템 파라미터 · API 연결 관리' },
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

export default function App() {
  const { pathname }  = useLocation()
  const { collapsed } = useSidebarStore()
  const meta = META[pathname] ?? { title: pathname.slice(1) || '대시보드' }
  const ml   = collapsed ? 56 : 220

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <div
        className="main-content flex-1 flex flex-col min-w-0 transition-all duration-200"
        style={{ marginLeft: ml }}
      >
        <TopBar title={meta.title} subtitle={meta.subtitle} />

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
              <Route path="/settings"        element={<Settings />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  )
}
