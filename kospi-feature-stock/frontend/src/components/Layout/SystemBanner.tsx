import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, XCircle, Info } from 'lucide-react'
import { adminApi, type SystemStatus } from '@/api/admin'

function isStale(dateStr: string | null, maxHours = 25): boolean {
  if (!dateStr) return true
  const diff = Date.now() - new Date(dateStr).getTime()
  return diff > maxHours * 3600_000
}

export function SystemBanner() {
  const { data } = useQuery<SystemStatus>({
    queryKey:        ['system-status'],
    queryFn:         adminApi.getSystemStatus,
    refetchInterval: 300_000,
    retry:           false,
  })

  if (!data) return null

  const warnings: { level: 'error' | 'warn' | 'info'; msg: string }[] = []

  if (!data.ml.model_loaded) {
    warnings.push({ level: 'error', msg: 'ML 모델 미로드 — 추천 기능이 비활성화됩니다.' })
  }

  if (data.data.pattern_vector_coverage < 10) {
    warnings.push({ level: 'warn', msg: `패턴 벡터 커버리지 ${data.data.pattern_vector_coverage.toFixed(1)}% — 유사종목 검색 정확도가 낮습니다.` })
  }

  if (isStale(data.data.latest_daily_bar, 25)) {
    warnings.push({ level: 'warn', msg: '일봉 데이터가 25시간 이상 갱신되지 않았습니다.' })
  }

  if (!data.services.redis) {
    warnings.push({ level: 'error', msg: 'Redis 연결 불가 — 실시간 스트리밍이 중단됩니다.' })
  }

  const highLag = Object.entries(data.kafka_lag).filter(([, v]) => v > 5000)
  if (highLag.length > 0) {
    const topics = highLag.map(([t]) => t).join(', ')
    warnings.push({ level: 'warn', msg: `Kafka 처리 지연 (${topics})` })
  }

  if (warnings.length === 0) return null

  const hasError = warnings.some(w => w.level === 'error')

  return (
    <div className={`flex flex-col gap-0.5 ${hasError ? 'bg-red-950/60' : 'bg-yellow-950/60'} border-b border-[var(--border)]`}>
      {warnings.map((w, i) => {
        const Icon = w.level === 'error' ? XCircle : w.level === 'warn' ? AlertTriangle : Info
        const color = w.level === 'error' ? 'text-red-400' : w.level === 'warn' ? 'text-yellow-400' : 'text-blue-400'
        return (
          <div key={i} className={`flex items-center gap-2 px-4 py-1.5 text-xs ${color}`}>
            <Icon size={12} className="shrink-0" />
            <span>{w.msg}</span>
          </div>
        )
      })}
    </div>
  )
}
