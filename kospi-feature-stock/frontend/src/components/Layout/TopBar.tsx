import { Sun, Moon, Bell, RefreshCw, Menu } from 'lucide-react'
import { useThemeStore } from '@/store/theme'
import { useRealtimeStore } from '@/store/realtime'
import { useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { clsx } from 'clsx'
import { useSidebarStore } from '@/store/sidebar'
import { useIsMobile } from '@/hooks/useMediaQuery'

interface TopBarProps {
  title:     string
  subtitle?: string
}

export function TopBar({ title, subtitle }: TopBarProps) {
  const { mode, toggle }     = useThemeStore()
  const isConnected          = useRealtimeStore((s) => s.isConnected)
  const qc                   = useQueryClient()
  const { toggle: toggleSidebar, openMobile } = useSidebarStore()
  const isMobile = useIsMobile()
  const [refreshing, setRefreshing] = useState(false)
  const [colorblind, setColorblind] = useState(() => localStorage.getItem('colorblind') === '1')

  useEffect(() => {
    document.body.classList.toggle('colorblind-mode', colorblind)
    localStorage.setItem('colorblind', colorblind ? '1' : '0')
  }, [colorblind])

  async function handleRefresh() {
    setRefreshing(true)
    await qc.invalidateQueries()
    setTimeout(() => setRefreshing(false), 600)
  }

  return (
    <header className={clsx(
      'sticky top-0 z-40 flex items-center justify-between',
      'px-4 md:px-6 py-3.5 border-b border-[var(--border)]',
      'bg-[var(--bg)]/85 backdrop-blur-lg'
    )}>
      {/* 모바일 햄버거 */}
      <button
        onClick={isMobile ? openMobile : toggleSidebar}
        className="md:hidden p-2 rounded-md text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors mr-2"
      >
        <Menu size={16} />
      </button>

      <div className="min-w-0 flex-1">
        <h1 className="text-base font-semibold text-[var(--fg)] truncate">{title}</h1>
        {subtitle && <p className="text-xs text-[var(--muted)] mt-0.5 truncate hidden sm:block">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-1 ml-2">
        {/* 실시간 연결 상태 */}
        <div
          className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-md"
          title={isConnected ? '실시간 스트림 연결됨' : '실시간 스트림 연결 중...'}
        >
          <span className={clsx(
            'inline-block w-1.5 h-1.5 rounded-full',
            isConnected ? 'bg-green-400 animate-pulse' : 'bg-[var(--muted)]/40'
          )} />
          <span className={clsx(
            'text-xs font-medium',
            isConnected ? 'text-green-400' : 'text-[var(--muted)]/60'
          )}>
            {isConnected ? 'LIVE' : '—'}
          </span>
        </div>

        {/* 새로고침 */}
        <button
          onClick={handleRefresh}
          className="p-2 rounded-md text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors"
          title="전체 데이터 새로고침"
        >
          <RefreshCw size={14} className={clsx(refreshing && 'animate-spin')} />
        </button>

        {/* 색맹 모드 토글 */}
        <button
          onClick={() => setColorblind((v) => !v)}
          className={clsx(
            'hidden sm:flex p-1.5 rounded-md text-xs font-bold transition-colors',
            colorblind
              ? 'bg-blue-500/20 text-blue-400'
              : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
          )}
          title={colorblind ? '색맹 모드 ON — 클릭하여 해제' : '색맹 안전 모드 활성화'}
        >
          CB
        </button>

        {/* 알림 */}
        <button className="p-1.5 rounded-md text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors relative">
          <Bell size={14} />
        </button>

        {/* 테마 토글 */}
        <button
          onClick={toggle}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium',
            'border border-[var(--border)] text-[var(--muted)]',
            'hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors'
          )}
          title={mode === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
        >
          {mode === 'dark'
            ? <><Sun size={13} /></>
            : <><Moon size={13} /></>
          }
        </button>
      </div>
    </header>
  )
}
