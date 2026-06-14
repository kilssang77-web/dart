import { type LucideIcon, Inbox } from 'lucide-react'
import { clsx } from 'clsx'

interface EmptyStateProps {
  icon?: LucideIcon
  title?: string
  description?: string
  action?: React.ReactNode
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export function EmptyState({
  icon: Icon = Inbox,
  title = '데이터 없음',
  description,
  action,
  className,
  size = 'md',
}: EmptyStateProps) {
  const iconSize  = size === 'sm' ? 28 : size === 'lg' ? 52 : 40
  const padding   = size === 'sm' ? 'py-8' : size === 'lg' ? 'py-20' : 'py-14'
  const titleSize = size === 'sm' ? 'text-sm' : 'text-base'

  return (
    <div className={clsx(
      'flex flex-col items-center justify-center gap-3 text-center',
      padding, className,
    )}>
      <Icon size={iconSize} className="text-[var(--muted)] opacity-30" />
      <div className="space-y-1">
        <p className={clsx('font-medium text-[var(--muted)]', titleSize)}>{title}</p>
        {description && (
          <p className="text-xs text-[var(--muted)] opacity-70 max-w-xs">{description}</p>
        )}
      </div>
      {action}
    </div>
  )
}
