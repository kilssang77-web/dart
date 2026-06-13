import { NavLink } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  LayoutDashboard, Zap, DollarSign, FileText, Newspaper,
  Monitor, BarChart2, Settings, ChevronLeft, ChevronRight, LineChart,
  Activity, Star, Bell, Layers, Search, TrendingUp,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { featuresApi } from '@/api/features'
import { useSidebarStore } from '@/store/sidebar'

interface NavItem {
  to:    string
  icon:  React.ReactNode
  label: string
  badge?: string
}

interface NavGroup {
  title: string
  items: NavItem[]
}

export function Sidebar() {
  const { collapsed, toggle } = useSidebarStore()

  const { data: summary } = useQuery({
    queryKey: ['today-summary'],
    queryFn:  featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const navGroups: NavGroup[] = [
    {
      title: '실시간',
      items: [
        { to: '/',         icon: <LayoutDashboard size={15} />, label: '대시보드' },
        { to: '/features', icon: <Zap size={15} />,            label: '특징주 탐지', badge: summary ? String(summary.total) : undefined },
        { to: '/hts',      icon: <Monitor size={15} />,        label: 'HTS 시세판' },
      ],
    },
    {
      title: '분석',
      items: [
        { to: '/recommendations', icon: <DollarSign size={15} />, label: '추천 매매' },
        { to: '/search',          icon: <Search size={15} />,     label: '종목 검색' },
        { to: '/analysis',        icon: <LineChart size={15} />,  label: '종목 분석' },
        { to: '/disclosures',     icon: <FileText size={15} />,   label: '공시 분석' },
        { to: '/news',            icon: <Newspaper size={15} />,  label: '뉴스/테마' },
        { to: '/themes',          icon: <Layers size={15} />,     label: '테마 추적' },
      ],
    },
    {
      title: '전략',
      items: [
        { to: '/backtest',    icon: <BarChart2 size={15} />,  label: '백테스트' },
        { to: '/performance', icon: <Activity size={15} />,   label: '모델 성능' },
        { to: '/tracking',    icon: <TrendingUp size={15} />, label: '성과 추적' },
      ],
    },
    {
      title: '관리',
      items: [
        { to: '/watchlist',      icon: <Star size={15} />,     label: '관심종목' },
        { to: '/notifications',  icon: <Bell size={15} />,     label: '알림 이력' },
        { to: '/settings',       icon: <Settings size={15} />, label: '설정' },
      ],
    },
  ]

  return (
    <aside className={clsx(
      'sidebar-full fixed left-0 top-0 bottom-0 z-50 flex flex-col',
      'bg-[var(--bg)] border-r border-[var(--border)]',
      'transition-all duration-200',
      collapsed ? 'w-[56px]' : 'w-[220px]'
    )}>
      {/* 로고 */}
      <div className={clsx(
        'flex items-center gap-2.5 p-4 border-b border-[var(--border)] flex-shrink-0',
        collapsed && 'justify-center'
      )}>
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center flex-shrink-0 shadow-lg shadow-cyan-500/20">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2">
            <circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="9" strokeDasharray="3 2"/>
            <line x1="12" y1="3" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="21"/>
            <line x1="3" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="21" y2="12"/>
          </svg>
        </div>
        {!collapsed && (
          <div>
            <div className="text-sm font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent tracking-wide">
              Quant Eye
            </div>
            <div className="text-[10px] text-[var(--muted)] leading-tight">AI의 눈으로 시장을 분석</div>
          </div>
        )}
      </div>

      {/* 내비게이션 */}
      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        {navGroups.map((group) => (
          <div key={group.title} className="mb-1">
            {!collapsed && (
              <div className="px-3 pt-3 pb-1 text-[10px] font-semibold text-[var(--muted)] uppercase tracking-widest">
                {group.title}
              </div>
            )}
            {collapsed && <div className="mx-2 my-1 border-t border-[var(--border)]/50" />}
            {group.items.map((item) => (
              <SidebarNavItem key={item.to} item={item} collapsed={collapsed} />
            ))}
          </div>
        ))}
      </nav>

      {/* 상태 표시 + 접기 버튼 */}
      <div className="border-t border-[var(--border)] p-3 flex items-center justify-between flex-shrink-0">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
            <span className="text-xs text-[var(--muted)]">실시간 연결됨</span>
          </div>
        )}
        <button
          onClick={toggle}
          className="p-1 rounded hover:bg-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] transition-colors ml-auto"
          title={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </aside>
  )
}

function SidebarNavItem({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) => clsx(
        'flex items-center gap-2.5 mx-1.5 px-2.5 py-2 rounded-md text-sm font-medium transition-colors',
        'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]',
        isActive && 'bg-[var(--border)] text-[var(--fg)]',
        collapsed && 'justify-center'
      )}
      title={collapsed ? item.label : undefined}
    >
      <span className="flex-shrink-0">{item.icon}</span>
      {!collapsed && <span className="truncate">{item.label}</span>}
      {!collapsed && item.badge && item.badge !== '0' && (
        <span className={clsx(
          'ml-auto text-xs font-semibold px-1.5 py-0.5 rounded-full',
          'bg-cyan-500/15 text-cyan-400'
        )}>
          {item.badge}
        </span>
      )}
    </NavLink>
  )
}
