import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, FileText, Sparkles, Users, BarChart2, Building2,
  ClipboardList, LogOut, BookMarked, ShieldCheck, TrendingUp, Calculator, Handshake, Bell, Globe,
  Target, ListChecks, Trophy,
} from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi, notificationsApi } from '@/api'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'

const NAV_GROUPS = [
  {
    label: '분석',
    items: [
      { to: '/dashboard',   label: '대시보드',      icon: LayoutDashboard },
      { to: '/statistics',  label: '통계 분석',      icon: BarChart2 },
      { to: '/agencies',    label: '발주처 분석',    icon: Building2 },
    ],
  },
  {
    label: '투찰',
    items: [
      { to: '/recommend',   label: 'AI 투찰률 추천', icon: Sparkles },
      { to: '/my-bids',     label: '투찰 이력',      icon: ClipboardList },
      { to: '/bids',        label: '입찰 현황',      icon: FileText },
      { to: '/joint-bid',   label: '공동도급 탐색',  icon: Handshake },
    ],
  },
  {
    label: '경쟁사',
    items: [
      { to: '/competitors', label: '경쟁사 분석',    icon: Users },
      { to: '/keywords',    label: '키워드 관리',    icon: BookMarked },
    ],
  },
  {
    label: '시장 인텔리전스',
    items: [
      { to: '/market-intel', label: '시장 인텔리전스', icon: Globe },
    ],
  },
  {
    label: '수주율 최적화',
    items: [
      { to: '/kpi-dashboard',   label: 'KPI 대시보드',  icon: Trophy },
      { to: '/bid-selection',   label: 'GO 목록',        icon: ListChecks },
      { to: '/company-profile', label: '회사 프로파일', icon: Target },
    ],
  },
  {
    label: '도구',
    items: [
      { to: '/qualification', label: '적격심사 계산기', icon: Calculator },
      { to: '/yega',          label: '예가 빈도 분석',  icon: TrendingUp },
    ],
  },
]

function NavItem({ to, label, icon: Icon }: { to: string; label: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors',
          isActive
            ? 'bg-sidebar-primary text-sidebar-primary-foreground font-medium'
            : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
        )
      }
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      {label}
    </NavLink>
  )
}

export default function AppLayout() {
  const { setUser, logout } = useAuthStore()
  const navigate = useNavigate()

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
  const roleLabel = user?.role === 'admin' ? '관리자' : user?.role === 'analyst' ? '분석가' : '뷰어'

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 사이드바 */}
      <aside className="w-56 bg-sidebar flex flex-col shrink-0 border-r border-sidebar-border">
        {/* 브랜드 */}
        <div className="flex items-center gap-2.5 px-4 py-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sidebar-primary shrink-0">
            <TrendingUp className="h-3.5 w-3.5 text-sidebar-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-bold text-sidebar-foreground leading-none">입찰 분석</p>
            <p className="text-[10px] text-sidebar-foreground/40 mt-0.5">AI 투찰 추천 시스템</p>
          </div>
        </div>

        <Separator className="bg-sidebar-border" />

        {/* 그룹 네비게이션 */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="px-3 mb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                  {group.label}
                </span>
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavItem key={item.to} {...item} />
                ))}
              </div>
            </div>
          ))}

          {user?.role === 'admin' && (
            <div>
              <div className="px-3 mb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                  관리
                </span>
              </div>
              <NavItem to="/admin" label="시스템 관리" icon={ShieldCheck} />
            </div>
          )}
        </nav>

        {/* 사용자 */}
        <Separator className="bg-sidebar-border" />
        <div className="p-2">
          <div className="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-sidebar-accent/50 transition-colors">
            <Avatar className="h-7 w-7 shrink-0">
              <AvatarFallback className="text-[10px] bg-sidebar-primary text-sidebar-primary-foreground">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-sidebar-foreground truncate leading-none">
                {user?.name || user?.email}
              </p>
              <p className="text-[10px] text-sidebar-foreground/40 mt-0.5">{roleLabel}</p>
            </div>
            <button
              onClick={() => navigate('/notifications')}
              className="relative text-sidebar-foreground/40 hover:text-sidebar-foreground transition-colors p-0.5 rounded"
              title="알림"
            >
              <Bell className="h-3.5 w-3.5" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white leading-none">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>
            <button
              onClick={() => { logout(); navigate('/login') }}
              className="text-sidebar-foreground/40 hover:text-sidebar-foreground transition-colors p-0.5 rounded"
              title="로그아웃"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
