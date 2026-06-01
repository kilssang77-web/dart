import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, FileText, Sparkles, Users, BarChart2, Building2, ClipboardList,
  LogOut, BookMarked, ShieldCheck, TrendingUp
} from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'

const NAV = [
  { to: '/dashboard',   label: '대시보드',      icon: LayoutDashboard },
  { to: '/bids',        label: '입찰 현황',      icon: FileText },
  { to: '/recommend',   label: 'AI 투찰률 추천', icon: Sparkles },
  { to: '/competitors', label: '경쟁사 분석',    icon: Users },
  { to: '/statistics',  label: '통계 분석',      icon: BarChart2 },
  { to: '/agencies',    label: '발주처 분석',    icon: Building2 },
  { to: '/my-bids',     label: '투찰 이력',      icon: ClipboardList },
  { to: '/keywords',    label: '키워드 관리',    icon: BookMarked },
]

export default function AppLayout() {
  const { setUser, logout } = useAuthStore()
  const navigate = useNavigate()

  const { data: user } = useQuery({
    queryKey: ['me'],
    queryFn: authApi.me,
    retry: false,
  })

  useEffect(() => { if (user) setUser(user) }, [user, setUser])

  const initials = (user?.name || user?.email || 'U').slice(0, 2).toUpperCase()
  const roleLabel = user?.role === 'admin' ? '관리자' : user?.role === 'analyst' ? '분석가' : '뷰어'

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 사이드바 */}
      <aside className="w-60 bg-sidebar flex flex-col shrink-0 border-r border-sidebar-border">
        {/* 브랜드 */}
        <div className="flex items-center gap-3 px-4 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sidebar-primary">
            <TrendingUp className="h-4 w-4 text-sidebar-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-semibold text-sidebar-foreground leading-none">입찰 분석</p>
            <p className="text-xs text-sidebar-foreground/50 mt-0.5">로컬 AI 추천 시스템</p>
          </div>
        </div>

        <Separator className="bg-sidebar-border" />

        {/* 내비게이션 */}
        <nav className="flex-1 space-y-0.5 p-2 mt-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                  isActive
                    ? 'bg-sidebar-primary text-sidebar-primary-foreground font-medium'
                    : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}

          {user?.role === 'admin' && (
            <>
              <Separator className="bg-sidebar-border my-2" />
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                    isActive
                      ? 'bg-sidebar-primary text-sidebar-primary-foreground font-medium'
                      : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                  )
                }
              >
                <ShieldCheck className="h-4 w-4 shrink-0" />
                관리자
              </NavLink>
            </>
          )}
        </nav>

        {/* 사용자 */}
        <Separator className="bg-sidebar-border" />
        <div className="p-3">
          <div className="flex items-center gap-3 px-1 py-2 rounded-md">
            <Avatar className="h-8 w-8">
              <AvatarFallback className="text-xs bg-sidebar-primary text-sidebar-primary-foreground">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-sidebar-foreground truncate">
                {user?.name || user?.email}
              </p>
              <p className="text-xs text-sidebar-foreground/50">{roleLabel}</p>
            </div>
            <button
              onClick={() => { logout(); navigate('/login') }}
              className="text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors p-1 rounded"
              title="로그아웃"
            >
              <LogOut className="h-4 w-4" />
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