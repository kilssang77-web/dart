/**
 * 성과 분석 허브 — KPI / 성과센터 / 통계 분석 탭 통합
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, BarChart3, PieChart } from 'lucide-react'
import { cn } from '@/lib/utils'
import KPIDashboardPage from './KPIDashboardPage'
import PerformancePage from './PerformancePage'
import StatisticsPage from './StatisticsPage'

const TABS = [
  { key: 'kpi',         label: 'KPI 대시보드',   icon: Activity },
  { key: 'performance', label: '성과센터',         icon: BarChart3 },
  { key: 'statistics',  label: '통계 분석',        icon: PieChart },
] as const

type TabKey = typeof TABS[number]['key']

export default function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabKey>(
    (searchParams.get('tab') as TabKey) ?? 'kpi'
  )

  const switchTab = (key: TabKey) => {
    setActiveTab(key)
    setSearchParams({ tab: key }, { replace: true })
  }

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
      {/* 탭 바 */}
      <div className="sticky top-0 z-10 bg-white border-b border-slate-200">
        <div className="flex items-center gap-1 px-6 pt-3 pb-0">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => switchTab(key)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-all -mb-px',
                activeTab === key
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300',
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 탭 콘텐츠 */}
      <div className="flex-1">
        {activeTab === 'kpi'         && <KPIDashboardPage />}
        {activeTab === 'performance' && <PerformancePage />}
        {activeTab === 'statistics'  && <StatisticsPage />}
      </div>
    </div>
  )
}
