import { clsx } from 'clsx'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

export function Card({ children, className, ...rest }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border bg-[var(--card)] border-[var(--border)] overflow-hidden',
        className
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx('px-5 pt-5 pb-0', className)}>
      {children}
    </div>
  )
}

export function CardTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx('text-[0.9375rem] font-semibold text-[var(--fg)] leading-tight', className)}>
      {children}
    </div>
  )
}

export function CardDesc({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-[var(--muted)] mt-1">{children}</div>
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('px-5 pb-5 pt-4', className)}>{children}</div>
}

interface StatCardProps {
  label:       string
  value:       React.ReactNode
  sub?:        React.ReactNode
  valueColor?: string
  onClick?:    () => void
}

export function StatCard({ label, value, sub, valueColor, onClick }: StatCardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border bg-[var(--card)] border-[var(--border)] p-5 transition-all duration-150',
        onClick && 'cursor-pointer ring-1 ring-transparent hover:ring-cyan-400/40 hover:border-cyan-500/40'
      )}
      onClick={onClick}
    >
      <div className="text-[0.8125rem] font-medium text-[var(--muted)] leading-none">{label}</div>
      <div
        className={clsx(
          'text-[1.875rem] font-bold mt-2.5 leading-none tabular',
          valueColor ?? 'text-[var(--fg)]',
        )}
      >
        {value}
      </div>
      {sub && <div className="text-[0.8125rem] text-[var(--muted)] mt-2">{sub}</div>}
    </div>
  )
}
