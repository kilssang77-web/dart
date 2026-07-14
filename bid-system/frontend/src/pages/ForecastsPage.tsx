/**
 * 예보센터 허브 — 수주 예보 / 발주 급증 예보 탭 통합
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FileSearch, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import PreSpecPage from './PreSpecPage'
import AgencyBudgetSurgePage from './AgencyBudgetSurgePage'

const TABS = [
  { key: 'prespec',  label: '수주 예보',       icon: FileSearch },
  { key: 'budget',   label: '발주 급증 예보',   icon: TrendingUp },
] as const

type TabKey = typeof TABS[number]['key']

export default function ForecastsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabKey>(
    (searchParams.get('tab') as TabKey) ?? 'prespec'
  )

  const switchTab = (key: TabKey) => {
    setActiveTab(key)
    setSearchParams({ tab: key }, { replace: true })
  }

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
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

      <div className="flex-1">
        {activeTab === 'prespec' && <PreSpecPage />}
        {activeTab === 'budget'  && <AgencyBudgetSurgePage />}
      </div>
    </div>
  )
}
