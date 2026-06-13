import { clsx } from 'clsx'

type Variant = 'green' | 'red' | 'blue' | 'yellow' | 'purple' | 'cyan' | 'gray'

const VARIANT_CLS: Record<Variant, string> = {
  green:  'bg-green-500/10  text-green-400  border-green-500/25',
  red:    'bg-red-500/10    text-red-400    border-red-500/25',
  blue:   'bg-blue-500/10   text-blue-400   border-blue-500/25',
  yellow: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/25',
  purple: 'bg-purple-500/10 text-purple-400 border-purple-500/25',
  cyan:   'bg-cyan-500/10   text-cyan-400   border-cyan-500/25',
  gray:   'bg-zinc-500/10   text-zinc-400   border-zinc-500/25',
}

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

export const EVENT_LABELS: Record<string, string> = {
  VOLUME_SURGE:           '거래량 급증',
  AMOUNT_SURGE:           '거래대금 급증',
  BREAKOUT_52W:           '52주 신고가',
  BREAKOUT_26W:           '26주 신고가',
  BREAKOUT_13W:           '분기 신고가',
  BREAKOUT_20D:           '20일 신고가',
  VI_TRIGGERED:           'VI(변동성) 발동',
  LONG_WHITE_CANDLE:      '장대 양봉',
  HAMMER_CANDLE:          '망치형 반전',
  MORNING_STAR:           '모닝스타 패턴',
  SUPPLY_ANOMALY:         '수급 이상',
  POST_DISCLOSURE_SURGE:  '공시 후 급등',
  PRICE_SURGE:            '가격 급등',
  BREAKOUT:               '박스권 돌파',
  GOLDEN_CROSS:           '골든크로스',
  OVERSOLD_REVERSAL:      '과매도 반전',
  FOREIGN_BUY:            '외국인 매수',
  INST_BUY:               '기관 매수',
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
      'inline-flex items-center border rounded font-medium whitespace-nowrap tracking-tight',
      size === 'sm' ? 'text-[11px] px-1.5 py-0.5' : 'text-xs px-2 py-1',
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
  if (!market || market === 'UNKNOWN' || market === '-' || market === 'ETC') return null
  const variant: Variant = market === 'KOSPI' ? 'blue' : market === 'KONEX' ? 'gray' : 'purple'
  return <Badge variant={variant} size="sm">{market}</Badge>
}
