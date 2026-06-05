import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react'

interface RiskCardProps {
  level: 'LOW' | 'MEDIUM' | 'HIGH'
  score: number
  factors?: string[]
}

const CONFIG = {
  LOW: {
    border: 'border-green-400',
    bg: 'bg-green-50',
    text: 'text-green-700',
    Icon: CheckCircle,
    iconColor: 'text-green-500',
    label: '낮음',
    bar: 'bg-green-400',
  },
  MEDIUM: {
    border: 'border-amber-400',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    Icon: AlertTriangle,
    iconColor: 'text-amber-500',
    label: '보통',
    bar: 'bg-amber-400',
  },
  HIGH: {
    border: 'border-red-400',
    bg: 'bg-red-50',
    text: 'text-red-700',
    Icon: XCircle,
    iconColor: 'text-red-500',
    label: '높음',
    bar: 'bg-red-400',
  },
} as const

export default function RiskCard({ level, score, factors }: RiskCardProps) {
  const { border, bg, text, Icon, iconColor, label, bar } = CONFIG[level]

  return (
    <div className={`rounded-lg border-2 ${border} ${bg} p-4 space-y-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={`h-5 w-5 ${iconColor}`} />
          <span className={`font-semibold text-sm ${text}`}>리스크 {label}</span>
        </div>
        <span className={`text-sm font-mono font-bold ${text}`}>{score.toFixed(1)}점</span>
      </div>

      <div className="h-2 bg-white/70 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${bar} transition-all duration-700`}
          style={{ width: `${Math.min(100, score * 10)}%` }}
        />
      </div>

      {factors && factors.length > 0 && (
        <ul className="space-y-1">
          {factors.map((f, i) => (
            <li key={i} className={`text-xs ${text} flex items-start gap-1`}>
              <span className="mt-0.5 shrink-0">•</span>
              {f}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
