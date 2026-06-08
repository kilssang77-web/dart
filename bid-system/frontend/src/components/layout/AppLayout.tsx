import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Home, Search, BookMarked, Swords, Sparkles, ShieldCheck, Users,
  TrendingUp, Handshake, BarChart2, ClipboardList, KeyRound,
  Building2, ShieldAlert, LogOut, Bell, PanelLeftClose, PanelLeftOpen,
  Globe, Activity, Target, Briefcase, LayoutDashboard, PieChart, Gauge,
  ChevronRight, ListChecks, FlaskConical, Radar,
} from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi, notificationsApi } from '@/api'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'

/* ───────────────────────────────────────────────────────────
   NAV 구조
─────────────────────────────────────────────────────────── */
const NAV_GROUPS = [
  {
    label: null,          // 그룹 레이블 없는 최상단 항목
    items: [
      { to: '/today',     label: '오늘의 입찰', icon: Home },
      { to: '/dashboard', label: '대시보드',     icon: LayoutDashboard },
    ],
  },
  {
    label: '공고 센터',
    items: [
      { to: '/bids?tab=recommend', label: '추천 공고', icon: Sparkles },
      { to: '/bids',               label: '전체 공고', icon: Search },
      { to: '/bids?bookmark=1',    label: '관심 공고', icon: BookMarked },
      { to: '/bid-selection',      label: '입찰 선택', icon: Target },
    ],
  },
  {
    label: '투찰 실행',
    items: [
      { to: '/executions',       label: '투찰 관리',     icon: ListChecks },
      { to: '/our-competitors',  label: '자사 경쟁사',   icon: Radar },
      { to: '/backtest',         label: '백테스트',      icon: FlaskConical },
    ],
  },
  {
    label: '입찰 전략',
    items: [
      { to: '/recommend',     label: 'AI 투찰 추천', icon: Swords },
      { to: '/qualification', label: '적격 심사',     icon: ShieldCheck },
      { to: '/competitors',   label: '경쟁사 분석',   icon: Users },
      { to: '/yega',          label: '예가 분석',     icon: TrendingUp },
      { to: '/joint-bid',     label: '파트너 탐색',   icon: Handshake },
    ],
  },
  {
    label: '성과·분석',
    items: [
      { to: '/performance',   label: '수주 현황',       icon: BarChart2 },
      { to: '/kpi-dashboard', label: 'KPI 대시보드',    icon: Gauge },
      { to: '/my-bids',       label: '투찰 이력',       icon: ClipboardList },
      { to: '/statistics',    label: '통계 분석',       icon: PieChart },
      { to: '/market-intel',  label: '시장 인텔리전스', icon: Globe },
      { to: '/agencies',      label: '발주기관',        icon: Building2 },
    ],
  },
  {
    label: '설정',
    items: [
      { to: '/keywords',        label: '키워드 설정',   icon: KeyRound },
      { to: '/company-profile', label: '회사 프로파일', icon: Briefcase },
    ],
  },
]

/* ───────────────────────────────────────────────────────────
   단일 NavItem
─────────────────────────────────────────────────────────── */
function NavItem({
  to,
  label,
  icon: Icon,
  collapsed,
}: {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  collapsed: boolean
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
          ? 'bg-white/[0.12] text-white'
          : 'text-slate-400 hover:bg-white/[0.06] hover:text-slate-200',
      )}
    >
      {/* 활성 좌측 인디케이터 */}
      {isActive && !collapsed && (
        <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-blue-400" />
      )}

      <Icon
        className={cn(
          'shrink-0 transition-colors',
          collapsed ? 'h-[17px] w-[17px]' : 'h-4 w-4',
          isActive ? 'text-blue-400' : 'text-slate-500 group-hover:text-slate-300',
        )}
      />

      {!collapsed && (
        <span className={cn('truncate text-[13px] leading-none', isActive ? 'font-medium' : 'font-normal')}>
          {label}
        </span>
      )}
    </NavLink>
  )
}

/* ───────────────────────────────────────────────────────────
   AppLayout
─────────────────────────────────────────────────────── */
export default function AppLayout() {
  const { setUser, logout } = useAuthStore()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const { data: user } = useQuery({ queryKey: ['me'], queryFn: authApi.me, retry: false })

  const { data: notifData } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 60_000,
    enabled: !!user,
  })
  const unreadCount = notifData?.count ?? 0

  useEffect(() => { if (user) setUser(user) }, [user, setUser])

  const initials = (user?.name || user?.email || 'U').slice(0, 2).toUpperCase()
  const roleLabel =
    user?.role === 'admin' ? '관리자' : user?.role === 'analyst' ? '분석가' : '뷰어'

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
          {/* 로고 아이콘 */}
          <div className="relative shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 shadow-lg shadow-blue-900/40">
              <Activity className="h-[15px] w-[15px] text-white" />
            </div>
            {/* 온라인 인디케이터 */}
            <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-[#0f172a]">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
          </div>

          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-[14px] font-bold text-white leading-none tracking-tight">
                BidAI <span className="text-blue-400">Pro</span>
              </p>
              <p className="text-[10px] text-slate-500 mt-[3px] leading-none">수주율 최적화 시스템</p>
            </div>
          )}
        </div>

        {/* ── 네비게이션 영역 ── */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3">
          {NAV_GROUPS.map((group, gi) => (
            <div key={gi} className={cn('px-2', gi > 0 && 'mt-1')}>

              {/* 그룹 레이블 */}
              {group.label && !collapsed && (
                <div className="flex items-center gap-2 px-2 pt-3 pb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-600 select-none whitespace-nowrap">
                    {group.label}
                  </span>
                  <div className="flex-1 h-px bg-white/[0.04]" />
                </div>
              )}
              {group.label && collapsed && gi > 0 && (
                <div className="my-2 mx-auto h-px w-6 bg-white/[0.08]" />
              )}

              {/* 아이템들 */}
              <div className="space-y-[2px]">
                {group.items.map((item) => (
                  <NavItem key={item.to} {...item} collapsed={collapsed} />
                ))}
              </div>
            </div>
          ))}

          {/* 관리자 메뉴 */}
          {user?.role === 'admin' && (
            <div className="px-2 mt-1">
              {!collapsed && (
                <div className="flex items-center gap-2 px-2 pt-3 pb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-600 select-none">관리</span>
                  <div className="flex-1 h-px bg-white/[0.04]" />
                </div>
              )}
              {collapsed && <div className="my-2 mx-auto h-px w-6 bg-white/[0.08]" />}
              <NavItem to="/admin" label="시스템 관리" icon={ShieldAlert} collapsed={collapsed} />
            </div>
          )}
        </nav>

        {/* ── 하단 사용자 영역 ── */}
        <div className="border-t border-white/[0.06]">

          {/* 알림 + 로그아웃 (축소 모드) */}
          {collapsed ? (
            <div className="flex flex-col items-center gap-1 py-2 px-2">
              <button
                onClick={() => navigate('/notifications')}
                title="알림"
                className="relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-white/[0.06] hover:text-slate-200 transition-colors"
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
                className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-white/[0.06] hover:text-red-400 transition-colors"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="p-3 space-y-1">
              {/* 알림 버튼 */}
              <button
                onClick={() => navigate('/notifications')}
                className="w-full flex items-center gap-3 h-9 px-3 rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-slate-200 transition-colors group"
              >
                <div className="relative shrink-0">
                  <Bell className="h-4 w-4 group-hover:text-slate-300 transition-colors" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1.5 flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none px-0.5">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </div>
                <span className="text-[13px] leading-none">알림</span>
                {unreadCount > 0 && (
                  <span className="ml-auto text-[10px] font-semibold text-red-400">{unreadCount}개</span>
                )}
              </button>

              {/* 사용자 정보 */}
              <div className="flex items-center gap-2.5 h-10 px-2 rounded-lg hover:bg-white/[0.04] transition-colors group">
                <Avatar className="h-7 w-7 shrink-0">
                  <AvatarFallback className="text-[11px] bg-gradient-to-br from-blue-500 to-blue-700 text-white font-semibold">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-medium text-slate-300 truncate leading-none">
                    {user?.name || user?.email}
                  </p>
                  <p className="text-[10px] text-slate-600 mt-[3px] leading-none">{roleLabel}</p>
                </div>
                <button
                  onClick={() => { logout(); navigate('/login') }}
                  title="로그아웃"
                  className="shrink-0 flex h-6 w-6 items-center justify-center rounded-md text-slate-600 hover:bg-white/[0.08] hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── 접기/펼치기 탭 (사이드바 우측 엣지) ── */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
          className={cn(
            'absolute top-[18px] -right-[11px] z-10',
            'flex h-[22px] w-[22px] items-center justify-center rounded-full',
            'bg-[#1e293b] border border-white/[0.12] text-slate-400',
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
