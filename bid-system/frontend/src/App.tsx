import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import AppLayout from '@/components/layout/AppLayout'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import LoginPage from '@/pages/LoginPage'
import BidsPage from '@/pages/BidsPage'
import BidDetailPage from '@/pages/BidDetailPage'
import CompetitorPage from '@/pages/CompetitorPage'
import StatisticsPage from '@/pages/StatisticsPage'
import KeywordsPage from '@/pages/KeywordsPage'
import AdminPage from '@/pages/AdminPage'
import AgencyDetailPage from '@/pages/AgencyDetailPage'
import AgenciesPage from '@/pages/AgenciesPage'
import MyBidsPage from '@/pages/MyBidsPage'
import QualificationPage from '@/pages/QualificationPage'
import JointBidPage from '@/pages/JointBidPage'
import JointSimPage from '@/pages/JointSimPage'
import YegaPage from '@/pages/YegaPage'
import TenderRecommendPage from '@/pages/TenderRecommendPage'
import NotificationsPage from '@/pages/NotificationsPage'
import RivalRadarPage from '@/pages/RivalRadarPage'
import MarketIntelPage from '@/pages/MarketIntelPage'
import CompanyProfilePage from '@/pages/CompanyProfilePage'
import BidSelectionPage   from '@/pages/BidSelectionPage'
import KPIDashboardPage   from '@/pages/KPIDashboardPage'
import TodayPage          from '@/pages/TodayPage'
import PerformancePage    from '@/pages/PerformancePage'
import ExecutionsPage     from '@/pages/ExecutionsPage'
import OurCompetitorsPage from '@/pages/OurCompetitorsPage'
import BacktestPage       from '@/pages/BacktestPage'
import PortfolioPage      from '@/pages/PortfolioPage'
import ManualPage         from '@/pages/ManualPage'
import TenderDecisionPage from '@/pages/TenderDecisionPage'
import JournalHistoryPage from '@/pages/JournalHistoryPage'
import PreSpecPage        from '@/pages/PreSpecPage'
import ContractsPage      from '@/pages/ContractsPage'
import AgencyBudgetSurgePage from '@/pages/AgencyBudgetSurgePage'
// 통합 허브 페이지
import AnalyticsPage  from '@/pages/AnalyticsPage'
import HistoryPage    from '@/pages/HistoryPage'
import ForecastsPage  from '@/pages/ForecastsPage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <ErrorBoundary>
    <BrowserRouter>
      <Routes>
        <Route path="/login"  element={<LoginPage />} />
        <Route path="/manual" element={<ManualPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <AppLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/today" replace />} />
          {/* 레거시 → 리다이렉트 */}
          <Route path="dashboard"    element={<Navigate to="/today" replace />} />
          <Route path="recommend"    element={<Navigate to="/today" replace />} />
          <Route path="kpi-dashboard" element={<Navigate to="/analytics?tab=kpi" replace />} />
          <Route path="performance"   element={<Navigate to="/analytics?tab=performance" replace />} />
          <Route path="statistics"    element={<Navigate to="/analytics?tab=statistics" replace />} />
          <Route path="journal-history" element={<Navigate to="/history?tab=journal" replace />} />
          <Route path="my-bids"         element={<Navigate to="/history?tab=mybids" replace />} />
          <Route path="pre-spec"        element={<Navigate to="/forecasts?tab=prespec" replace />} />
          <Route path="budget-surge"    element={<Navigate to="/forecasts?tab=budget" replace />} />

          {/* 핵심 업무 */}
          <Route path="today"    element={<TodayPage />} />
          <Route path="decision" element={<TenderDecisionPage />} />

          {/* 공고 관리 */}
          <Route path="bids"                       element={<BidsPage />} />
          <Route path="bids/:id"                   element={<BidDetailPage />} />
          <Route path="bids/:id/final-recommend"   element={<TenderRecommendPage />} />
          <Route path="bids/:id/joint-sim"         element={<JointSimPage />} />
          <Route path="bids/:id/rival-radar"       element={<RivalRadarPage />} />
          <Route path="bid-selection"              element={<BidSelectionPage />} />
          <Route path="executions"                 element={<ExecutionsPage />} />
          <Route path="portfolio"                  element={<PortfolioPage />} />

          {/* AI 분석 */}
          <Route path="agencies"       element={<AgenciesPage />} />
          <Route path="agencies/:id"   element={<AgencyDetailPage />} />
          <Route path="competitors"    element={<CompetitorPage />} />
          <Route path="our-competitors" element={<OurCompetitorsPage />} />
          <Route path="yega"           element={<YegaPage />} />
          <Route path="market-intel"   element={<MarketIntelPage />} />
          <Route path="backtest"       element={<BacktestPage />} />

          {/* 통합 허브 (탭) */}
          <Route path="analytics"  element={<AnalyticsPage />} />
          <Route path="history"    element={<HistoryPage />} />
          <Route path="forecasts"  element={<ForecastsPage />} />

          {/* 계약 실적 */}
          <Route path="contracts"  element={<ContractsPage />} />

          {/* 관리 */}
          <Route path="company-profile" element={<CompanyProfilePage />} />
          <Route path="keywords"        element={<KeywordsPage />} />
          <Route path="admin"           element={<AdminPage />} />

          {/* 기타 유틸리티 */}
          <Route path="notifications"  element={<NotificationsPage />} />
          <Route path="qualification"  element={<QualificationPage />} />
          <Route path="joint-bid"      element={<JointBidPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
    </ErrorBoundary>
  )
}
