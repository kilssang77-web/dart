import { NavLink } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  LayoutDashboard, Zap, DollarSign, FileText, Newspaper,
  Search, Monitor, BarChart2, Activity, Settings, ChevronLeft, ChevronRight,
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

export function Sidebar() {
  const { collapsed, toggle } = useSidebarStore()

  const { data: summary } = useQuery({
    queryKey: ['today-summary'],
    queryFn:  featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const navGroups: { title: string; items: NavItem[] }[] = [
    {
      title: '분석',
      items: [
        { to: '/',               icon: <LayoutDashboard size={15} />, label: '대시보드' },
        { to: '/features',       icon: <Zap size={15} />,            label: '특징주 탐지', badge: summary ? String(summary.total) : undefined },
        { to: '/recommendations',icon: <DollarSign size={15} />,     label: '추천 매매' },
      ],
    },
    {
      title: '정보',
      items: [
        { to: '/disclosures',    icon: <FileText size={15} />,       label: '공시 분석' },
        { to: '/news',           icon: <Newspaper size={15} />,      label: '뉴스/테마' },
        { to: '/search',         icon: <Search size={15} />,         label: '종목 검색' },
      ],
    },
    {
      title: '시스템',
      items: [
        { to: '/hts',            icon: <Monitor size={15} />,        label: 'HTS 시세판' },
        { to: '/backtest',       icon: <BarChart2 size={15} />,      label: '백테스트' },
        { to: '/performance',    icon: <Activity size={15} />,       label: '모델 성능' },
        { to: '/settings',       icon: <Settings size={15} />,       label: '설정' },
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
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-green-400 flex items-center justify-center flex-shrink-0">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
            <path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>
          </svg>
        </div>
        {!collapsed && (
          <div>
            <div className="text-sm font-bold text-[var(--fg)]">특징주 시스템</div>
            <div className="text-[10px] text-[var(--muted)]">KOSPI / KOSDAQ</div>
          </div>
        )}
      </div>

      {/* 내비게이션 */}
      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        {navGroups.map((group) => (
          <div key={group.title} className="mb-1">
            {!collapsed && (
              <div className="px-3 py-2 text-[10px] font-semibold text-[var(--muted)] uppercase tracking-widest">
                {group.title}
              </div>
            )}
            {group.items.map((item) => (
              <NavItem key={item.to} item={item} collapsed={collapsed} />
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

function NavItem({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
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
          'ml-auto text-[10px] font-semibold px-1.5 py-0.5 rounded-full',
          'bg-[var(--border)] text-[var(--muted)]'
        )}>
          {item.badge}
        </span>
      )}
    </NavLink>
  )
}
