import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, XCircle, Info } from 'lucide-react'
import { adminApi, type SystemStatus } from '@/api/admin'

// 마지막으로 일봉 수집이 완료됐어야 할 거래일 날짜(YYYY-MM-DD) 반환
// - EOD 수집 완료 기준: 16:30 KST
// - 주말(토·일) skip
function _lastExpectedBarDate(): string {
  const KST = 9 * 3600_000
  const kst = new Date(Date.now() + KST)
  const h = kst.getUTCHours()
  const m = kst.getUTCMinutes()

  let d = new Date(Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate()))
  // 19:00 이전이면 아직 EOD 수집 완료 전 — 전 거래일을 기준으로 판단
  if (h < 19) d.setUTCDate(d.getUTCDate() - 1)
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1)

  return d.toISOString().slice(0, 10)
}

function isStale(dateStr: string | null): boolean {
  if (!dateStr) return true
  const barDate = dateStr.includes('T') ? dateStr.slice(0, 10) : dateStr
  return barDate < _lastExpectedBarDate()
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

  if (data.data.pattern_vector_coverage > 0 && data.data.pattern_vector_coverage < 30) {
    warnings.push({ level: 'warn', msg: `패턴 벡터 커버리지 ${data.data.pattern_vector_coverage.toFixed(1)}% — 유사종목 검색 정확도가 낮습니다.` })
  }

  if (isStale(data.data.latest_daily_bar)) {
    const lastDate = data.data.latest_daily_bar
      ? data.data.latest_daily_bar.slice(0, 10)
      : '알 수 없음'
    warnings.push({ level: 'warn', msg: `일봉 데이터 미갱신 — 마지막: ${lastDate}` })
  }

  if (!data.services.redis) {
    warnings.push({ level: 'error', msg: 'Redis 연결 불가 — 실시간 스트리밍이 중단됩니다.' })
  }

  const offlineSvcs = Object.entries(data.services).filter(([k, v]) => !v && k !== 'db' && k !== 'redis')
  if (offlineSvcs.length > 0) {
    const names = offlineSvcs.map(([k]) => k).join(', ')
    warnings.push({ level: 'warn', msg: `마이크로서비스 오프라인: ${names}` })
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
