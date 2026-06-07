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
  return <div className={clsx('px-5 pt-5 pb-0', className)}>{children}</div>
}

export function CardTitle({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-semibold text-[var(--fg)]">{children}</div>
}

export function CardDesc({ children }: { children: React.ReactNode }) {
  return <div className="text-xs text-[var(--muted)] mt-0.5">{children}</div>
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
    <div className="rounded-xl border bg-[var(--card)] border-[var(--border)] p-5">
      <div className="text-xs font-medium text-[var(--muted)]">{label}</div>
      <div
        className={clsx(
          'text-3xl font-bold mt-1.5 leading-none tabular',
          valueColor ?? 'text-[var(--fg)]',
          onClick && 'cursor-pointer hover:opacity-70 underline-offset-4 hover:underline'
        )}
        onClick={onClick}
      >
        {value}
      </div>
      {sub && <div className="text-xs text-[var(--muted)] mt-1.5">{sub}</div>}
    </div>
  )
}
