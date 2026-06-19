import { NavLink, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { clsx } from 'clsx'
import {
  LayoutDashboard, TrendingUp, Search, Newspaper,
  FlaskConical, Settings2, Activity,
  ChevronLeft, ChevronRight, X,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { featuresApi } from '@/api/features'
import { useSidebarStore } from '@/store/sidebar'
import { useIsMobile } from '@/hooks/useMediaQuery'

interface NavItem {
  to:    string
  icon:  React.ReactNode
  label: string
  badge?: string
}

interface NavGroup {
  items: NavItem[]
}

// ── 메뉴 정의 (7항목) ──────────────────────────────────────────────────────
function buildNavGroups(badge?: string): NavGroup[] {
  return [
    {
      items: [
        { to: '/',                icon: <LayoutDashboard size={15} />, label: '대시보드' },
        { to: '/recommendations', icon: <TrendingUp size={15} />,     label: '매매 추천', badge },
        { to: '/intel',           icon: <Newspaper size={15} />,      label: '공시/뉴스' },
        { to: '/search',          icon: <Search size={15} />,         label: '종목 검색' },
        { to: '/rec-journey',     icon: <Activity size={15} />,       label: '성과 추적' },
      ],
    },
    {
      items: [
        { to: '/backtest', icon: <FlaskConical size={15} />, label: '백테스트' },
        { to: '/settings', icon: <Settings2 size={15} />,    label: '설정' },
      ],
    },
  ]
}

export function Sidebar() {
  const { collapsed, toggle, mobileOpen, closeMobile } = useSidebarStore()
  const isMobile = useIsMobile()
  const { pathname } = useLocation()

  useEffect(() => { closeMobile() }, [pathname, closeMobile])

  const { data: summary } = useQuery({
    queryKey: ['today-summary'],
    queryFn:  featuresApi.todaySummary,
    refetchInterval: 30_000,
  })

  const navGroups = buildNavGroups(
    summary && summary.total > 0 ? String(summary.total) : undefined
  )

  if (isMobile) {
    return (
      <>
        {mobileOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            onClick={closeMobile}
          />
        )}
        <aside className={clsx(
          'fixed left-0 top-0 bottom-0 z-50 flex flex-col w-[260px]',
          'bg-[var(--bg)] border-r border-[var(--border)]',
          'transition-transform duration-250',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}>
          <SidebarContent collapsed={false} toggle={closeMobile} navGroups={navGroups} isCloseMobile />
        </aside>
      </>
    )
  }

  return (
    <aside className={clsx(
      'sidebar-full fixed left-0 top-0 bottom-0 z-50 flex flex-col',
      'bg-[var(--bg)] border-r border-[var(--border)]',
      'transition-all duration-200',
      collapsed ? 'w-[56px]' : 'w-[220px]'
    )}>
      <SidebarContent collapsed={collapsed} toggle={toggle} navGroups={navGroups} />
    </aside>
  )
}

function SidebarContent({
  collapsed, toggle, navGroups, isCloseMobile,
}: {
  collapsed: boolean
  toggle: () => void
  navGroups: NavGroup[]
  isCloseMobile?: boolean
}) {
  return (
    <>
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
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent tracking-wide">
              Quant Eye
            </div>
            <div className="text-[10px] text-[var(--muted)] leading-tight">AI의 눈으로 시장을 분석</div>
          </div>
        )}
        {isCloseMobile && (
          <button onClick={toggle} className="p-1 rounded text-[var(--muted)] hover:text-[var(--fg)] ml-auto">
            <X size={16} />
          </button>
        )}
      </div>

      {/* 내비게이션 */}
      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        {navGroups.map((group, idx) => (
          <div key={idx} className="mb-1">
            {idx > 0 && <div className="mx-2 my-2 border-t border-[var(--border)]/50" />}
            {group.items.map((item) => (
              <SidebarNavItem key={item.to} item={item} collapsed={collapsed} />
            ))}
          </div>
        ))}
      </nav>

      {/* 접기 버튼 */}
      {!isCloseMobile && (
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
      )}
    </>
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
        <span className="ml-auto text-xs font-semibold px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400">
          {item.badge}
        </span>
      )}
    </NavLink>
  )
}
