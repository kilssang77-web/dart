import { clsx } from 'clsx'

type Variant = 'green' | 'red' | 'blue' | 'yellow' | 'purple' | 'cyan' | 'gray'

const VARIANT_CLS: Record<Variant, string> = {
  green:  'bg-green-500/10  text-green-400  border-green-500/25  dark:bg-green-500/10  dark:text-green-400',
  red:    'bg-red-500/10    text-red-400    border-red-500/25    dark:bg-red-500/10    dark:text-red-400',
  blue:   'bg-blue-500/10   text-blue-400   border-blue-500/25   dark:bg-blue-500/10   dark:text-blue-400',
  yellow: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/25 dark:bg-yellow-500/10 dark:text-yellow-400',
  purple: 'bg-purple-500/10 text-purple-400 border-purple-500/25 dark:bg-purple-500/10 dark:text-purple-400',
  cyan:   'bg-cyan-500/10   text-cyan-400   border-cyan-500/25   dark:bg-cyan-500/10   dark:text-cyan-400',
  gray:   'bg-zinc-500/10   text-zinc-400   border-zinc-500/25   dark:bg-zinc-500/10   dark:text-zinc-400',
}

// 이벤트 타입 → 뱃지 색상 매핑
const EVENT_COLORS: Record<string, Variant> = {
  VOLUME_SURGE:           'blue',
  AMOUNT_SURGE:           'cyan',
  BREAKOUT_52W:           'green',
  BREAKOUT_26W:           'green',
  BREAKOUT_13W:           'green',
  BREAKOUT_20D:           'yellow',
  VI_TRIGGERED:           'red',
  LONG_WHITE_CANDLE:      'green',
  HAMMER_CANDLE:          'yellow',
  MORNING_STAR:           'purple',
  SUPPLY_ANOMALY:         'cyan',
  POST_DISCLOSURE_SURGE:  'purple',
}

const EVENT_LABELS: Record<string, string> = {
  VOLUME_SURGE:           '거래량급증',
  AMOUNT_SURGE:           '거래대금급증',
  BREAKOUT_52W:           '52주신고가',
  BREAKOUT_26W:           '26주신고가',
  BREAKOUT_13W:           '13주신고가',
  BREAKOUT_20D:           '20일신고가',
  VI_TRIGGERED:           'VI발동',
  LONG_WHITE_CANDLE:      '장대양봉',
  HAMMER_CANDLE:          '망치형',
  MORNING_STAR:           '모닝스타',
  SUPPLY_ANOMALY:         '수급이상',
  POST_DISCLOSURE_SURGE:  '공시후급등',
}

interface BadgeProps {
  variant?: Variant
  eventType?: string
  children?: React.ReactNode
  className?: string
  size?: 'sm' | 'md'
}

export function Badge({ variant, eventType, children, className, size = 'md' }: BadgeProps) {
  const resolvedVariant = variant ?? (eventType ? EVENT_COLORS[eventType] ?? 'gray' : 'gray')
  const label = children ?? (eventType ? EVENT_LABELS[eventType] ?? eventType : '')

  return (
    <span className={clsx(
      'inline-flex items-center border rounded font-semibold whitespace-nowrap',
      size === 'sm' ? 'text-[10px] px-1.5 py-0' : 'text-[11px] px-2 py-0.5',
      VARIANT_CLS[resolvedVariant],
      className
    )}>
      {label}
    </span>
  )
}

export function ActionBadge({ action }: { action: string }) {
  const MAP: Record<string, { variant: Variant; label: string }> = {
    BUY:  { variant: 'green',  label: '매수' },
    WAIT: { variant: 'yellow', label: '대기' },
    SKIP: { variant: 'gray',   label: '제외' },
  }
  const { variant, label } = MAP[action] ?? { variant: 'gray', label: action }
  return <Badge variant={variant}>{label}</Badge>
}

export function SentimentBadge({ category }: { category?: string }) {
  if (!category) return null
  const MAP: Record<string, { variant: Variant; label: string }> = {
    favorable:   { variant: 'green', label: '호재' },
    unfavorable: { variant: 'red',   label: '악재' },
    neutral:     { variant: 'gray',  label: '중립' },
  }
  const { variant, label } = MAP[category] ?? { variant: 'gray', label: category }
  return <Badge variant={variant}>{label}</Badge>
}

export function MarketBadge({ market }: { market?: string }) {
  if (!market) return null
  return (
    <Badge variant={market === 'KOSPI' ? 'blue' : 'purple'}>
      {market}
    </Badge>
  )
}
