import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import AppLayout from '@/components/layout/AppLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import BidsPage from '@/pages/BidsPage'
import BidDetailPage from '@/pages/BidDetailPage'
import RecommendPage from '@/pages/RecommendPage'
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
// 수주율 최적화 시스템 신규 페이지
import CompanyProfilePage from '@/pages/CompanyProfilePage'
import BidSelectionPage   from '@/pages/BidSelectionPage'
import KPIDashboardPage   from '@/pages/KPIDashboardPage'
import TodayPage          from '@/pages/TodayPage'
import PerformancePage    from '@/pages/PerformancePage'
import ExecutionsPage        from '@/pages/ExecutionsPage'
import OurCompetitorsPage   from '@/pages/OurCompetitorsPage'
import BacktestPage         from '@/pages/BacktestPage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <AppLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/today" replace />} />
          <Route path="dashboard"    element={<DashboardPage />} />
          <Route path="today"        element={<TodayPage />} />
          <Route path="performance"  element={<PerformancePage />} />
          <Route path="bids"                       element={<BidsPage />} />
          <Route path="bids/:id"                 element={<BidDetailPage />} />
          <Route path="bids/:id/final-recommend" element={<TenderRecommendPage />} />
          <Route path="bids/:id/joint-sim"      element={<JointSimPage />} />
          <Route path="recommend"   element={<RecommendPage />} />
          <Route path="competitors" element={<CompetitorPage />} />
          <Route path="statistics"  element={<StatisticsPage />} />
          <Route path="keywords"    element={<KeywordsPage />} />
          <Route path="admin"       element={<AdminPage />} />
          <Route path="agencies"     element={<AgenciesPage />} />
          <Route path="agencies/:id" element={<AgencyDetailPage />} />
          <Route path="my-bids"        element={<MyBidsPage />} />
          <Route path="qualification" element={<QualificationPage />} />
          <Route path="joint-bid"     element={<JointBidPage />} />
          <Route path="yega"          element={<YegaPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="bids/:id/rival-radar" element={<RivalRadarPage />} />
          <Route path="market-intel"          element={<MarketIntelPage />} />
          {/* 수주율 최적화 시스템 */}
          <Route path="company-profile" element={<CompanyProfilePage />} />
          <Route path="bid-selection"   element={<BidSelectionPage />} />
          <Route path="kpi-dashboard"   element={<KPIDashboardPage />} />
          <Route path="executions"        element={<ExecutionsPage />} />
          <Route path="our-competitors"  element={<OurCompetitorsPage />} />
          <Route path="backtest"         element={<BacktestPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}