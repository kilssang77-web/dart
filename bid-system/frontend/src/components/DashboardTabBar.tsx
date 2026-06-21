import { NavLink } from 'react-router-dom'
import { LayoutDashboard, BarChart2, Activity } from 'lucide-react'
import { cn } from '@/lib/utils'

const TABS = [
  { to: '/dashboard',     label: '현황 개요', icon: LayoutDashboard },
  { to: '/kpi-dashboard', label: 'KPI 성과',  icon: BarChart2       },
  { to: '/performance',   label: 'ML 성능',   icon: Activity        },
]

export default function DashboardTabBar() {
  return (
    <div className="bg-white border-b px-4 flex gap-0 shrink-0">
      {TABS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) => cn(
            'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
            isActive
              ? 'border-blue-600 text-blue-700'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          )}
        >
          <Icon className="w-3.5 h-3.5" />
          {label}
        </NavLink>
      ))}
    </div>
  )
}
