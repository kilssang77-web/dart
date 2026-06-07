import { Sun, Moon, Bell, RefreshCw } from 'lucide-react'
import { useThemeStore } from '@/store/theme'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'

interface TopBarProps {
  title:     string
  subtitle?: string
}

export function TopBar({ title, subtitle }: TopBarProps) {
  const { mode, toggle } = useThemeStore()
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  async function handleRefresh() {
    setRefreshing(true)
    await qc.invalidateQueries()
    setTimeout(() => setRefreshing(false), 600)
  }

  return (
    <header className={clsx(
      'sticky top-0 z-40 flex items-center justify-between',
      'px-6 py-3 border-b border-[var(--border)]',
      'bg-[var(--bg)]/85 backdrop-blur-lg'
    )}>
      <div>
        <h1 className="text-sm font-semibold text-[var(--fg)]">{title}</h1>
        {subtitle && <p className="text-xs text-[var(--muted)] mt-0.5">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-1.5">
        {/* 새로고침 */}
        <button
          onClick={handleRefresh}
          className="p-1.5 rounded-md text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors"
          title="전체 데이터 새로고침"
        >
          <RefreshCw size={14} className={clsx(refreshing && 'animate-spin')} />
        </button>

        {/* 알림 */}
        <button className="p-1.5 rounded-md text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors relative">
          <Bell size={14} />
        </button>

        {/* 테마 토글 */}
        <button
          onClick={toggle}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium',
            'border border-[var(--border)] text-[var(--muted)]',
            'hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors'
          )}
          title={mode === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
        >
          {mode === 'dark'
            ? <><Sun size={13} /> 라이트</>
            : <><Moon size={13} /> 다크</>
          }
        </button>
      </div>
    </header>
  )
}
