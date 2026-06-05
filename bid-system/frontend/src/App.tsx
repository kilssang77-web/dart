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
import YegaPage from '@/pages/YegaPage'
import TenderRecommendPage from '@/pages/TenderRecommendPage'

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
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard"   element={<DashboardPage />} />
          <Route path="bids"                       element={<BidsPage />} />
          <Route path="bids/:id"                 element={<BidDetailPage />} />
          <Route path="bids/:id/final-recommend" element={<TenderRecommendPage />} />
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
        </Route>
      </Routes>
    </BrowserRouter>
  )
}