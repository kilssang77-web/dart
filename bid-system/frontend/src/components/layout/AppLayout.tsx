import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Home, Search, BookMarked, Swords, Sparkles, ShieldCheck, Users,
  TrendingUp, Handshake, BarChart2, ClipboardList, Settings, KeyRound,
  Building2, ShieldAlert, LogOut, Bell, ChevronRight, Globe, Activity,
  Target, Briefcase, LayoutDashboard, PieChart, Gauge,
} from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi, notificationsApi } from '@/api'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'

/* ── Nav 데이터 ──────────────────────────────────────────── */
const NAV_GROUPS = [
  {
    label: '홈',
    items: [
      { to: '/today',      label: '오늘의 입찰',   icon: Home,         description: '일일 브리핑' },
      { to: '/dashboard',  label: '대시보드',       icon: LayoutDashboard, description: '시장 개요' },
    ],
  },
  {
    label: '공고센터',
    items: [
      { to: '/bids?tab=recommend', label: '추천 공고',  icon: Sparkles,   description: 'AI 추천' },
      { to: '/bids',               label: '전체 공고',  icon: Search,     description: '공고 검색' },
      { to: '/bids?bookmark=1',    label: '관심 공고',  icon: BookMarked, description: '북마크' },
      { to: '/bid-selection',      label: '입찰 선택',  icon: Target,     description: 'GO/WATCH/NO_GO' },
    ],
  },
  {
    label: '입찰 전략',
    items: [
      { to: '/recommend',     label: 'AI 투찰 추천',  icon: Swords,       description: '투찰률 추천' },
      { to: '/qualification', label: '적격 심사',     icon: ShieldCheck,  description: '심사 계산기' },
      { to: '/competitors',   label: '경쟁사 분석',   icon: Users,        description: '경쟁사 조회' },
      { to: '/yega',          label: '예가 분석',     icon: TrendingUp,   description: '복수예가 분석' },
    ],
  },
  {
    label: '공동도급',
    items: [
      { to: '/joint-bid', label: '파트너 탐색', icon: Handshake, description: '협력사 탐색' },
    ],
  },
  {
    label: '성과 센터',
    items: [
      { to: '/performance',  label: '수주 현황',  icon: BarChart2,     description: 'KPI 현황' },
      { to: '/kpi-dashboard',label: 'KPI 대시보드', icon: Gauge,       description: '목표 추적' },
      { to: '/my-bids',      label: '투찰 이력',  icon: ClipboardList, description: '이력 관리' },
    ],
  },
  {
    label: '시장 분석',
    items: [
      { to: '/statistics',   label: '통계 분석',     icon: PieChart,   description: '낙찰 통계' },
      { to: '/market-intel', label: '시장 인텔리전스', icon: Globe,     description: '경쟁 동향' },
      { to: '/agencies',     label: '발주기관',       icon: Building2, description: '기관 분석' },
    ],
  },
  {
    label: '설정',
    items: [
      { to: '/keywords',        label: '키워드 설정',   icon: KeyRound,  description: '감시 키워드' },
      { to: '/company-profile', label: '회사 프로파일', icon: Briefcase, description: '회사 정보' },
    ],
  },
]

/* ── NavItem ─────────────────────────────────────────────── */
function NavItem({
  to, label, icon: Icon,
}: {
  to: string; label: string; icon: React.ComponentType<{ className?: string }>
}) {
  const location = useLocation()
  const path = to.split('?')[0]
  const isActive = location.pathname === path ||
    (path !== '/' && location.pathname.startsWith(path) &&
     (to.includes('?') ? location.search.includes(to.split('?')[1] ?? '') : true))

  return (
    <NavLink
      to={to}
      className={cn(
        'group flex items-center gap-2.5 px-3 py-[7px] rounded-md text-[13px] transition-all duration-150',
        isActive
          ? 'bg-sidebar-primary/20 text-sidebar-primary font-semibold border-l-2 border-sidebar-primary pl-[10px]'
          : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground border-l-2 border-transparent',
      )}
    >
      <Icon className={cn('h-[15px] w-[15px] shrink-0 transition-colors',
        isActive ? 'text-sidebar-primary' : 'text-sidebar-muted group-hover:text-sidebar-foreground/80')} />
      <span className="truncate">{label}</span>
    </NavLink>
  )
}

/* ── AppLayout ───────────────────────────────────────────── */
export default function AppLayout() {
  const { setUser, logout } = useAuthStore()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const { data: user } = useQuery({
    queryKey: ['me'],
    queryFn: authApi.me,
    retry: false,
  })

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
    user?.role === 'admin' ? '관리자' :
    user?.role === 'analyst' ? '분석가' : '뷰어'
  const roleColor =
    user?.role === 'admin' ? 'bg-red-500/20 text-red-300' :
    user?.role === 'analyst' ? 'bg-blue-500/20 text-blue-300' : 'bg-slate-500/20 text-slate-400'

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* ── 사이드바 ── */}
      <aside
        className={cn(
          'flex flex-col shrink-0 bg-[hsl(var(--sidebar-background))] border-r border-sidebar-border transition-all duration-200',
          collapsed ? 'w-[52px]' : 'w-[220px]',
        )}
      >
        {/* 브랜드 헤더 */}
        <div className="flex items-center gap-2.5 px-3 py-3.5 border-b border-sidebar-border">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary">
            <Activity className="h-4 w-4 text-white" />
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-bold text-sidebar-foreground leading-none tracking-tight">
                BidAI Pro
              </p>
              <p className="text-[10px] text-sidebar-muted mt-0.5 leading-none">수주율 최적화 시스템</p>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="ml-auto text-sidebar-muted hover:text-sidebar-foreground transition-colors p-0.5 rounded shrink-0"
          >
            <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', collapsed ? '' : 'rotate-180')} />
          </button>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-1">
              {!collapsed && (
                <div className="px-3 pt-3 pb-1">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-sidebar-muted/60 select-none">
                    {group.label}
                  </span>
                </div>
              )}
              {collapsed && <div className="border-t border-sidebar-border/40 my-1.5 mx-1" />}
              <div className="space-y-px">
                {group.items.map((item) =>
                  collapsed ? (
                    <div key={item.to} title={item.label}>
                      <NavLink
                        to={item.to}
                        className={({ isActive }) =>
                          cn(
                            'flex items-center justify-center h-9 w-9 mx-auto rounded-md transition-colors',
                            isActive
                              ? 'bg-sidebar-primary/20 text-sidebar-primary'
                              : 'text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground',
                          )
                        }
                      >
                        <item.icon className="h-4 w-4" />
                      </NavLink>
                    </div>
                  ) : (
                    <NavItem key={item.to} {...item} />
                  )
                )}
              </div>
            </div>
          ))}

          {/* 관리자 메뉴 */}
          {user?.role === 'admin' && (
            <div className="mb-1">
              {!collapsed && (
                <div className="px-3 pt-3 pb-1">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-sidebar-muted/60">관리</span>
                </div>
              )}
              {collapsed ? (
                <div title="시스템 관리">
                  <NavLink
                    to="/admin"
                    className={({ isActive }) =>
                      cn('flex items-center justify-center h-9 w-9 mx-auto rounded-md transition-colors',
                        isActive ? 'bg-sidebar-primary/20 text-sidebar-primary' : 'text-sidebar-muted hover:bg-sidebar-accent')
                    }
                  >
                    <ShieldAlert className="h-4 w-4" />
                  </NavLink>
                </div>
              ) : (
                <NavItem to="/admin" label="시스템 관리" icon={ShieldAlert} />
              )}
            </div>
          )}
        </nav>

        {/* 사용자 섹션 */}
        <div className="border-t border-sidebar-border p-2">
          {collapsed ? (
            <div className="flex flex-col items-center gap-1.5">
              <button
                onClick={() => navigate('/notifications')}
                className="relative flex h-8 w-8 items-center justify-center rounded-md text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                title="알림"
              >
                <Bell className="h-4 w-4" />
                {unreadCount > 0 && (
                  <span className="absolute top-0.5 right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              <button
                onClick={() => { logout(); navigate('/login') }}
                className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                title="로그아웃"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-sidebar-accent transition-colors">
              <Avatar className="h-7 w-7 shrink-0">
                <AvatarFallback className="text-[11px] bg-sidebar-primary text-white font-semibold">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <p className="text-[12px] font-medium text-sidebar-foreground truncate leading-tight">
                  {user?.name || user?.email}
                </p>
                <span className={cn('text-[9px] font-semibold px-1.5 py-0.5 rounded-full', roleColor)}>
                  {roleLabel}
                </span>
              </div>
              <div className="flex items-center gap-0.5 shrink-0">
                <button
                  onClick={() => navigate('/notifications')}
                  className="relative flex h-6 w-6 items-center justify-center rounded text-sidebar-muted hover:text-sidebar-foreground transition-colors"
                  title="알림"
                >
                  <Bell className="h-3.5 w-3.5" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => { logout(); navigate('/login') }}
                  className="flex h-6 w-6 items-center justify-center rounded text-sidebar-muted hover:text-sidebar-foreground transition-colors"
                  title="로그아웃"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* ── 메인 콘텐츠 ── */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
