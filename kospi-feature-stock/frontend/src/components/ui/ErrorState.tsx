import { AlertCircle, RefreshCw } from 'lucide-react'

interface ErrorStateProps {
  error?: Error | null
  message?: string
  retry?: () => void
}

export function ErrorState({ error, message, retry }: ErrorStateProps) {
  const msg = message ?? error?.message ?? '데이터를 불러오지 못했습니다'
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-[var(--muted)]">
      <AlertCircle size={28} className="text-red-400 opacity-80" />
      <p className="text-sm text-center max-w-xs">{msg}</p>
      {retry && (
        <button
          onClick={retry}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-[var(--border)] rounded-lg hover:bg-[var(--border)] transition-colors text-[var(--fg)]"
        >
          <RefreshCw size={12} />
          다시 시도
        </button>
      )}
    </div>
  )
}
