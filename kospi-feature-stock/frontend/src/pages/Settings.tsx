import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { CheckCircle, XCircle, AlertCircle, Server, Activity } from 'lucide-react'
import { systemApi } from '@/api/market'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'

interface HealthResponse {
  status: string
  services?: Record<string, string>
  version?: string
  uptime_seconds?: number
}

const THRESHOLDS = [
  { label: 'VOLUME_SURGE 배수',           key: 'VOLUME_SURGE_RATIO',      env: 'VOLUME_SURGE_RATIO',          default: '3.0' },
  { label: 'AMOUNT_SURGE 배수',           key: 'AMOUNT_SURGE_RATIO',      env: 'AMOUNT_SURGE_RATIO',          default: '3.0' },
  { label: '고점 돌파 최소 등락률 (%)',    key: 'BREAKOUT_MIN_CHANGE',     env: 'BREAKOUT_MIN_CHANGE',         default: '1.0' },
  { label: '장대양봉 최소 몸통 (%)',       key: 'CANDLE_BODY_MIN',         env: 'CANDLE_BODY_MIN_PCT',         default: '5.0' },
  { label: 'VI 발동 임계값 (%)',           key: 'VI_THRESHOLD',            env: 'VI_THRESHOLD_PCT',            default: '10.0' },
  { label: 'ML 매수 최소 확률',           key: 'ML_BUY_THRESHOLD',        env: 'ML_BUY_THRESHOLD',            default: '0.55' },
  { label: 'ATR 손절 배수',              key: 'ATR_STOP_MULT',           env: 'ATR_STOP_MULT',               default: '1.5' },
  { label: 'ATR 목표 배수',              key: 'ATR_TARGET_MULT',         env: 'ATR_TARGET_MULT',             default: '3.0' },
  { label: '유사 사례 Top-K',            key: 'SIMILAR_TOP_K',           env: 'SIMILAR_TOP_K',               default: '10' },
  { label: 'K-Means 테마 클러스터 수',    key: 'N_CLUSTERS',              env: 'N_CLUSTERS',                  default: '30' },
]

function StatusIcon({ status }: { status: string }) {
  if (status === 'ok' || status === 'healthy' || status === 'connected')
    return <CheckCircle size={14} className="text-green-400" />
  if (status === 'degraded' || status === 'warning')
    return <AlertCircle size={14} className="text-yellow-400" />
  return <XCircle size={14} className="text-red-400" />
}

function statusColor(s: string) {
  if (s === 'ok' || s === 'healthy' || s === 'connected') return 'text-green-400'
  if (s === 'degraded' || s === 'warning') return 'text-yellow-400'
  return 'text-red-400'
}

function formatUptime(seconds?: number) {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export function Settings() {
  const { data: health, isLoading, error } = useQuery<HealthResponse>({
    queryKey:       ['health'],
    queryFn:        systemApi.health,
    refetchInterval: 30_000,
    retry:           1,
  })

  const services = health?.services ?? {}
  const serviceEntries = Object.entries(services).length > 0
    ? Object.entries(services)
    : [
        ['db',      health?.status === 'ok' ? 'ok' : 'unknown'],
        ['kafka',   health?.status === 'ok' ? 'ok' : 'unknown'],
        ['redis',   health?.status === 'ok' ? 'ok' : 'unknown'],
        ['kis_api', health?.status === 'ok' ? 'ok' : 'unknown'],
      ] as [string, string][]

  return (
    <div className="p-6 space-y-5">

      {/* 시스템 헬스 */}
      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>시스템 상태</CardTitle>
            <div className="text-xs text-[var(--muted)] mt-0.5">30초마다 자동 갱신</div>
          </div>
          {health && (
            <div className={clsx('flex items-center gap-1.5 text-sm font-semibold', statusColor(health.status))}>
              <StatusIcon status={health.status} />
              {health.status.toUpperCase()}
            </div>
          )}
          {isLoading && <span className="text-xs text-[var(--muted)]">확인 중…</span>}
          {error && <span className="text-xs text-red-400">연결 실패</span>}
        </CardHeader>
        <CardBody className="pt-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {serviceEntries.map(([name, status]) => (
              <div
                key={name}
                className={clsx(
                  'flex items-center gap-2.5 p-3.5 rounded-xl border',
                  status === 'ok' || status === 'connected'
                    ? 'border-green-500/25 bg-green-500/5'
                    : status === 'degraded'
                    ? 'border-yellow-500/25 bg-yellow-500/5'
                    : 'border-[var(--border)] bg-[var(--bg)]'
                )}
              >
                <StatusIcon status={status} />
                <div>
                  <div className="text-xs font-semibold text-[var(--fg)] capitalize">{name.replace(/_/g, ' ')}</div>
                  <div className={clsx('text-[10px] font-medium capitalize', statusColor(status))}>
                    {status}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {health && (
            <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center gap-6 text-xs text-[var(--muted)]">
              {health.version && (
                <span className="flex items-center gap-1.5">
                  <Server size={11} /> 버전 {health.version}
                </span>
              )}
              {health.uptime_seconds != null && (
                <span className="flex items-center gap-1.5">
                  <Activity size={11} /> 업타임 {formatUptime(health.uptime_seconds)}
                </span>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {/* 환경변수 기반 임계값 */}
      <Card>
        <CardHeader>
          <CardTitle>시스템 파라미터</CardTitle>
          <div className="text-xs text-[var(--muted)] mt-0.5">
            .env 파일로 설정 · 변경 후 서비스 재시작 필요
          </div>
        </CardHeader>
        <CardBody className="pt-3 px-0 pb-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                  <th className="text-left py-2.5 pl-5 pr-3 font-medium">파라미터</th>
                  <th className="text-left py-2.5 pr-3 font-medium">환경변수</th>
                  <th className="text-right py-2.5 pr-5 font-medium">기본값</th>
                </tr>
              </thead>
              <tbody>
                {THRESHOLDS.map((t) => (
                  <tr key={t.key} className="border-b border-[var(--border)]/50">
                    <td className="py-2.5 pl-5 pr-3 text-[var(--fg)]">{t.label}</td>
                    <td className="py-2.5 pr-3">
                      <code className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--border)] text-cyan-400 font-mono">
                        {t.env}
                      </code>
                    </td>
                    <td className="py-2.5 pr-5 text-right tabular text-[var(--muted)] font-medium">
                      {t.default}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      {/* 마이크로서비스 포트 정보 */}
      <Card>
        <CardHeader>
          <CardTitle>마이크로서비스 포트</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { name: 'API Server',       port: '8000', desc: 'FastAPI REST + WebSocket' },
              { name: 'Collector',        port: '8001', desc: 'KIS REST + DART 수집' },
              { name: 'Detector',         port: '8002', desc: 'Kafka 소비 · 이벤트 탐지' },
              { name: 'Analyzer',         port: '8003', desc: '뉴스/공시 감성 분석' },
              { name: 'Recommender',      port: '8004', desc: 'ML 기반 매매 추천' },
              { name: 'ML Service',       port: '8005', desc: 'LightGBM 학습/추론' },
            ].map((svc) => (
              <div key={svc.name} className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-[var(--fg)]">{svc.name}</span>
                  <code className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--border)] text-cyan-400 font-mono">
                    :{svc.port}
                  </code>
                </div>
                <div className="text-[10px] text-[var(--muted)]">{svc.desc}</div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
