import { Sun, Moon, Bell, RefreshCw, Menu, Database, BookOpen, X } from 'lucide-react'
import { useThemeStore } from '@/store/theme'
import { useRealtimeStore } from '@/store/realtime'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import { useState, useEffect, useCallback } from 'react'
import { clsx } from 'clsx'
import { useSidebarStore } from '@/store/sidebar'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { adminApi, type SystemStatus } from '@/api/admin'

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
  const [showManual, setShowManual] = useState(false)

  const closeManual = useCallback(() => setShowManual(false), [])

  useEffect(() => {
    if (!showManual) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeManual() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showManual, closeManual])

  const { data: sysStatus } = useQuery<SystemStatus>({
    queryKey:        ['system-status'],
    queryFn:         adminApi.getSystemStatus,
    refetchInterval: 300_000,
    retry:           false,
  })
  const latestBar = sysStatus?.data.latest_daily_bar?.slice(0, 10) ?? null

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

        {/* 일봉 마지막 갱신 */}
        {latestBar && (
          <div
            className="hidden md:flex items-center gap-1 px-2 py-1 rounded-md text-[var(--muted)]"
            title="최신 일봉 데이터 날짜"
          >
            <Database size={11} />
            <span className="text-xs">{latestBar}</span>
          </div>
        )}

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

        {/* 매뉴얼 */}
        <button
          onClick={() => setShowManual(true)}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium',
            'border border-[var(--border)] text-[var(--muted)]',
            'hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors'
          )}
          title="사용자 매뉴얼"
        >
          <BookOpen size={13} />
        </button>
      </div>

      {/* 매뉴얼 모달 */}
      {showManual && (
        <div
          className="fixed inset-0 z-[9999] flex flex-col bg-black/60 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) closeManual() }}
        >
          <div className="relative flex flex-col w-full h-full max-w-[1400px] mx-auto my-4 rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--bg)] shadow-2xl">
            {/* 모달 헤더 */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)] bg-[var(--bg2)] shrink-0">
              <div className="flex items-center gap-2">
                <BookOpen size={16} className="text-blue-400" />
                <span className="font-semibold text-[var(--fg)] text-sm">Quant Eye 사용자 매뉴얼 v1.0</span>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href="/manual.html"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--border)]"
                >
                  새 탭에서 열기
                </a>
                <button
                  onClick={closeManual}
                  className="p-1.5 rounded-md text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors"
                  title="닫기 (Esc)"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            {/* iframe */}
            <iframe
              src="/manual.html"
              className="flex-1 w-full border-0"
              title="사용자 매뉴얼"
            />
          </div>
        </div>
      )}
    </header>
  )
}
