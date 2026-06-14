import { clsx } from 'clsx'
import { Clock, AlertTriangle } from 'lucide-react'

interface DataFreshnessProps {
  updatedAt?: string | null | number
  staleAfterMs?: number
  className?: string
}

function formatAge(ms: number): string {
  if (ms < 60_000)    return `${Math.floor(ms / 1000)}초 전`
  if (ms < 3600_000)  return `${Math.floor(ms / 60_000)}분 전`
  if (ms < 86400_000) return `${Math.floor(ms / 3600_000)}시간 전`
  return `${Math.floor(ms / 86400_000)}일 전`
}

export function DataFreshness({
  updatedAt,
  staleAfterMs = 300_000,
  className,
}: DataFreshnessProps) {
  if (!updatedAt) return null

  const ts   = typeof updatedAt === 'number' ? updatedAt : new Date(updatedAt).getTime()
  const age  = Date.now() - ts
  const stale = age > staleAfterMs

  return (
    <span className={clsx(
      'inline-flex items-center gap-1 text-[10px]',
      stale ? 'text-yellow-400' : 'text-[var(--muted)]',
      className,
    )}>
      {stale ? <AlertTriangle size={9} /> : <Clock size={9} />}
      {formatAge(age)}
    </span>
  )
}
