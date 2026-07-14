/**
 * 이력 관리 허브 — 투찰이력 분석 / 나의 투찰 이력 탭 통합
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ClipboardCheck, History } from 'lucide-react'
import { cn } from '@/lib/utils'
import JournalHistoryPage from './JournalHistoryPage'
import MyBidsPage from './MyBidsPage'

const TABS = [
  { key: 'journal', label: '투찰이력 분석', icon: ClipboardCheck },
  { key: 'mybids',  label: '나의 투찰 이력', icon: History },
] as const

type TabKey = typeof TABS[number]['key']

export default function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabKey>(
    (searchParams.get('tab') as TabKey) ?? 'journal'
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
        {activeTab === 'journal' && <JournalHistoryPage />}
        {activeTab === 'mybids'  && <MyBidsPage />}
      </div>
    </div>
  )
}
