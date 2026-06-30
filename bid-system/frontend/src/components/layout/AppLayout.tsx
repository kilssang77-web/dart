import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search, Users,
  TrendingUp, KeyRound,
  ShieldAlert, LogOut, Bell, PanelLeftClose, PanelLeftOpen,
  Activity, Target, Briefcase, LayoutDashboard, PieChart,
  ChevronRight, ChevronDown, ListChecks, FlaskConical,
  ClipboardCheck, BarChart3, Sparkles, BookOpen,
  Zap, Building2, LineChart, Layers, FileSearch, FileText,
} from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi, notificationsApi } from '@/api'
import { silentRefresh, tokenMsRemaining } from '@/api/client'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'

/* ───────────────────────────────────────────────────────────
   NAV 구조 — 낙찰률 극대화 중심 5그룹
─────────────────────────────────────────────────────────── */
const NAV_GROUPS = [
  {
    label: '핵심 업무',
    defaultOpen: true,
    items: [
      { to: '/today',        label: '오늘의 업무',     icon: Sparkles },
      { to: '/decision',     label: 'AI 투찰결정',     icon: Zap,    highlight: true },
      { to: '/kpi-dashboard', label: 'KPI 대시보드',  icon: Activity },
    ],
  },
  {
    label: '공고 관리',
    defaultOpen: false,
    items: [
      { to: '/bids',          label: '공고센터',       icon: Search },
      { to: '/bid-selection', label: '공고 선별',      icon: Target },
      { to: '/executions',    label: '투찰 실행 관리', icon: ListChecks },
      { to: '/portfolio',     label: '포트폴리오',     icon: Layers },
    ],
  },
  {
    label: 'AI 분석',
    defaultOpen: false,
    items: [
      { to: '/agencies',    label: '발주기관 분석',  icon: Building2 },
      { to: '/competitors', label: '경쟁사 분석',    icon: Users },
      { to: '/yega',        label: '예가 빈도 분석', icon: TrendingUp },
      { to: '/market-intel',label: '시장 지능',      icon: LineChart },
      { to: '/backtest',    label: '백테스트 엔진',  icon: FlaskConical },
    ],
  },
  {
    label: '이력 / 성과',
    defaultOpen: false,
    items: [
      { to: '/journal-history', label: '투찰 이력 분석', icon: ClipboardCheck },
      { to: '/performance',     label: '성과센터',        icon: BarChart3 },
      { to: '/statistics',      label: '통계 분석',       icon: PieChart },
      { to: '/pre-spec',        label: '수주 예보',        icon: FileSearch },
      { to: '/budget-surge',    label: '발주 급증 예보',   icon: TrendingUp },
      { to: '/contracts',       label: '계약 실적',        icon: FileText },
    ],
  },
]

const ADMIN_ITEMS = [
  { to: '/company-profile', label: '회사 프로파일', icon: Briefcase },
  { to: '/keywords',        label: '키워드 관리',   icon: KeyRound },
]

const ALL_GROUP_KEYS = [...NAV_GROUPS.map(g => g.label), '관리']

/* ───────────────────────────────────────────────────────────
   단일 NavItem
─────────────────────────────────────────────────────────── */
function NavItem({
  to, label, icon: Icon, collapsed, highlight,
}: {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  collapsed: boolean
  highlight?: boolean
}) {
  const location = useLocation()
  const basePath = to.split('?')[0]
  const isActive =
    location.pathname === basePath ||
    (basePath.length > 1 &&
      location.pathname.startsWith(basePath) &&
      (to.includes('?') ? location.search.includes(to.split('?')[1] ?? '') : true))

  return (
    <NavLink
      to={to}
      title={collapsed ? label : undefined}
      className={cn(
        'group relative flex items-center gap-3 rounded-lg transition-all duration-150 select-none',
        collapsed ? 'h-9 w-9 mx-auto justify-center' : 'h-9 px-3',
        isActive
          ? highlight
            ? 'bg-blue-600/80 text-white shadow-sm shadow-blue-900/40'
            : 'bg-white/[0.12] text-white'
          : highlight
            ? 'text-blue-300 hover:bg-blue-600/50 hover:text-white'
            : 'text-slate-200 hover:bg-white/[0.08] hover:text-white',
      )}
    >
      {isActive && !collapsed && (
        <span className={cn(
          'absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full',
          highlight ? 'bg-yellow-400' : 'bg-blue-400',
        )} />
      )}
      <Icon
        className={cn(
          'shrink-0 transition-colors',
          collapsed ? 'h-[17px] w-[17px]' : 'h-4 w-4',
          isActive
            ? highlight ? 'text-yellow-300' : 'text-blue-400'
            : highlight ? 'text-blue-400 group-hover:text-yellow-300' : 'text-slate-300 group-hover:text-white',
        )}
      />
      {!collapsed && (
        <span className={cn('truncate text-[13px] leading-none', isActive || highlight ? 'font-semibold' : 'font-normal')}>
          {label}
        </span>
      )}
    </NavLink>
  )
}

/* ───────────────────────────────────────────────────────────
   AppLayout
─────────────────────────────────────────────────────────── */
export default function AppLayout() {
  const { setUser, logout } = useAuthStore()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(
    () => Object.fromEntries(ALL_GROUP_KEYS.map(k => {
      const group = NAV_GROUPS.find(g => g.label === k)
      return [k, group?.defaultOpen ?? false]
    }))
  )

  const { data: user } = useQuery({ queryKey: ['me'], queryFn: authApi.me, retry: false })
  const { data: notifData } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 60_000,
    enabled: !!user,
  })
  const unreadCount = notifData?.count ?? 0

  useEffect(() => { if (user) setUser(user) }, [user, setUser])

  /* 토큰 만료 30분 전 자동 갱신 */
  useEffect(() => {
    const schedule = () => {
      const ms = tokenMsRemaining()
      if (ms <= 0) return
      const refreshIn = Math.max(ms - 30 * 60 * 1000, 0)  // 30분 전
      return window.setTimeout(async () => {
        await silentRefresh()
        schedule()  // 갱신 후 다음 타이머 재등록
      }, refreshIn)
    }
    const id = schedule()
    return () => { if (id) window.clearTimeout(id) }
  }, [])

  const initials = (user?.name || user?.email || 'U').slice(0, 2).toUpperCase()
  const roleLabel = user?.role === 'admin' ? '관리자' : user?.role === 'analyst' ? '분석가' : '뷰어'

  const toggleGroup = (key: string) =>
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }))

  const openManual = () =>
    window.open('/manual', '_blank', 'width=1280,height=900,scrollbars=yes,resizable=yes')

  return (
    <div className="flex h-screen overflow-hidden bg-background">

      {/* ══════════════════════════════════════
          사이드바
      ══════════════════════════════════════ */}
      <aside
        className={cn(
          'relative flex flex-col shrink-0 overflow-hidden',
          'bg-[#0f172a] border-r border-white/[0.06]',
          'transition-[width] duration-200 ease-in-out',
          collapsed ? 'w-[56px]' : 'w-[232px]',
        )}
      >

        {/* ── 브랜드 헤더 ── */}
        <div className={cn(
          'flex items-center border-b border-white/[0.06]',
          collapsed ? 'h-14 justify-center' : 'h-14 px-4 gap-3',
        )}>
          <div className="relative shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 shadow-lg shadow-blue-900/40">
              <Activity className="h-[15px] w-[15px] text-white" />
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-[#0f172a]">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-[14px] font-bold text-white leading-none tracking-tight">
                BidAI <span className="text-blue-400">Pro</span>
              </p>
              <p className="text-xs text-slate-400 mt-[3px] leading-none">수주율 최적화 시스템</p>
            </div>
          )}
        </div>

        {/* ── 사용자 매뉴얼 버튼 ── */}
        <div className={cn(
          'border-b border-white/[0.06]',
          collapsed ? 'flex justify-center py-1.5' : 'px-2 py-1.5',
        )}>
          {collapsed ? (
            <button
              onClick={openManual}
              title="사용자 매뉴얼"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 hover:bg-white/[0.08] hover:text-white transition-colors"
            >
              <BookOpen className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={openManual}
              className="w-full flex items-center gap-2.5 h-8 px-3 rounded-lg text-slate-200 hover:bg-white/[0.08] hover:text-white transition-colors"
            >
              <BookOpen className="h-3.5 w-3.5 text-blue-400 shrink-0" />
              <span className="text-[12.5px]">사용자 매뉴얼</span>
            </button>
          )}
        </div>

        {/* ── 네비게이션 영역 ── */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-2">

          {NAV_GROUPS.map((group) => {
            const isOpen = openGroups[group.label]
            return (
              <div key={group.label} className="px-2 mb-0.5">
                {/* 그룹 헤더 */}
                {collapsed ? (
                  <div className="my-1.5 mx-auto h-px w-6 bg-white/[0.08]" />
                ) : (
                  <button
                    onClick={() => toggleGroup(group.label)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/[0.05] transition-colors group"
                  >
                    <span className="flex-1 text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400 group-hover:text-slate-300 select-none whitespace-nowrap">
                      {group.label}
                    </span>
                    {isOpen
                      ? <ChevronDown className="h-3 w-3 text-slate-500 group-hover:text-slate-400 shrink-0" />
                      : <ChevronRight className="h-3 w-3 text-slate-500 group-hover:text-slate-400 shrink-0" />
                    }
                  </button>
                )}

                {/* 아이템 목록 (펼침 상태이거나 축소 모드) */}
                {(isOpen || collapsed) && (
                  <div className="space-y-[2px]">
                    {group.items.map((item) => (
                      <NavItem key={item.to} {...item} collapsed={collapsed} highlight={item.highlight} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {/* ── 관리 그룹 ── */}
          <div className="px-2 mb-0.5">
            {collapsed ? (
              <div className="my-1.5 mx-auto h-px w-6 bg-white/[0.08]" />
            ) : (
              <button
                onClick={() => toggleGroup('관리')}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/[0.05] transition-colors group"
              >
                <span className="flex-1 text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400 group-hover:text-slate-300 select-none">
                  관리
                </span>
                {openGroups['관리']
                  ? <ChevronDown className="h-3 w-3 text-slate-500 group-hover:text-slate-400 shrink-0" />
                  : <ChevronRight className="h-3 w-3 text-slate-500 group-hover:text-slate-400 shrink-0" />
                }
              </button>
            )}
            {(openGroups['관리'] || collapsed) && (
              <div className="space-y-[2px]">
                {ADMIN_ITEMS.map(item => (
                  <NavItem key={item.to} {...item} collapsed={collapsed} />
                ))}
                {user?.role === 'admin' && (
                  <NavItem to="/admin" label="시스템 관리" icon={ShieldAlert} collapsed={collapsed} />
                )}
              </div>
            )}
          </div>
        </nav>

        {/* ── 하단 사용자 영역 ── */}
        <div className="border-t border-white/[0.06]">
          {collapsed ? (
            <div className="flex flex-col items-center gap-1 py-2 px-2">
              <button
                onClick={() => navigate('/notifications')}
                title="알림"
                className="relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-slate-200 transition-colors"
              >
                <Bell className="h-4 w-4" />
                {unreadCount > 0 && (
                  <span className="absolute top-1 right-1 flex h-[14px] w-[14px] items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              <button
                onClick={() => { logout(); navigate('/login') }}
                title="로그아웃"
                className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-red-400 transition-colors"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="p-3 space-y-1">
              <button
                onClick={() => navigate('/notifications')}
                className="w-full flex items-center gap-3 h-9 px-3 rounded-lg text-slate-300 hover:bg-white/[0.06] hover:text-white transition-colors group"
              >
                <div className="relative shrink-0">
                  <Bell className="h-4 w-4 group-hover:text-white transition-colors" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1.5 flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none px-0.5">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </div>
                <span className="text-[13px] leading-none">알림</span>
                {unreadCount > 0 && (
                  <span className="ml-auto text-xs font-semibold text-red-400">{unreadCount}개</span>
                )}
              </button>

              <div className="flex items-center gap-2.5 h-10 px-2 rounded-lg hover:bg-white/[0.04] transition-colors group">
                <Avatar className="h-7 w-7 shrink-0">
                  <AvatarFallback className="text-[11px] bg-gradient-to-br from-blue-500 to-blue-700 text-white font-semibold">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-medium text-slate-200 truncate leading-none">
                    {user?.name || user?.email}
                  </p>
                  <p className="text-xs text-slate-500 mt-[3px] leading-none">{roleLabel}</p>
                </div>
                <button
                  onClick={() => { logout(); navigate('/login') }}
                  title="로그아웃"
                  className="shrink-0 flex h-6 w-6 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.08] hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── 접기/펼치기 탭 ── */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
          className={cn(
            'absolute top-[18px] -right-[11px] z-10',
            'flex h-[22px] w-[22px] items-center justify-center rounded-full',
            'bg-[#1e293b] border border-white/[0.12] text-slate-500',
            'hover:bg-[#334155] hover:text-white hover:border-white/20',
            'transition-all duration-150 shadow-md',
          )}
        >
          {collapsed
            ? <PanelLeftOpen className="h-3 w-3" />
            : <PanelLeftClose className="h-3 w-3" />
          }
        </button>
      </aside>

      {/* ══════════════════════════════════════
          메인 콘텐츠
      ══════════════════════════════════════ */}
      <main className="flex-1 overflow-y-auto bg-slate-50">
        <Outlet />
      </main>
    </div>
  )
}
