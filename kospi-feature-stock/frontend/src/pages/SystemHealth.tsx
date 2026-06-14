import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  CheckCircle2, XCircle, AlertTriangle, Cpu, Database,
  Radio, Activity, Clock, RefreshCw,
} from 'lucide-react'
import { adminApi, type SystemStatus } from '@/api/admin'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { fmt } from '@/lib/utils'

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={clsx('inline-block w-2 h-2 rounded-full', ok ? 'bg-green-400' : 'bg-red-400')} />
  )
}

function ServiceRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-[var(--border)] last:border-0">
      <span className="text-sm text-[var(--fg)]">{label}</span>
      <span className={clsx('flex items-center gap-1.5 text-xs font-semibold', ok ? 'text-green-400' : 'text-red-400')}>
        {ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
        {ok ? '정상' : '오류'}
      </span>
    </div>
  )
}

function LagRow({ topic, lag }: { topic: string; lag: number }) {
  const level = lag < 0 ? 'unknown' : lag > 5000 ? 'critical' : lag > 1000 ? 'warn' : 'ok'
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-[var(--border)] last:border-0">
      <span className="text-sm text-[var(--fg)] font-mono">{topic}</span>
      <span className={clsx(
        'text-xs font-semibold tabular',
        level === 'ok'       && 'text-green-400',
        level === 'warn'     && 'text-yellow-400',
        level === 'critical' && 'text-red-400',
        level === 'unknown'  && 'text-[var(--muted)]',
      )}>
        {lag < 0 ? '—' : lag.toLocaleString()}
      </span>
    </div>
  )
}

function DataRow({ label, value, stale }: { label: string; value: string | null; stale?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-[var(--border)] last:border-0">
      <span className="text-xs text-[var(--muted)]">{label}</span>
      <span className={clsx('text-xs font-mono', stale ? 'text-yellow-400' : 'text-[var(--fg)]')}>
        {value ?? '—'}
        {stale && <AlertTriangle size={10} className="inline ml-1" />}
      </span>
    </div>
  )
}

function isStale(dateStr: string | null, maxHours = 25): boolean {
  if (!dateStr) return true
  return Date.now() - new Date(dateStr).getTime() > maxHours * 3600_000
}

export function SystemHealth() {
  const { data, isLoading, dataUpdatedAt, refetch, isFetching } = useQuery<SystemStatus>({
    queryKey:        ['system-status'],
    queryFn:         adminApi.getSystemStatus,
    refetchInterval: 60_000,
  })

  const ml   = data?.ml
  const dat  = data?.data
  const svc  = data?.services
  const lags = data?.kafka_lag ?? {}

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-[var(--fg)] flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" />
          시스템 헬스 대시보드
        </h1>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
        >
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          {dataUpdatedAt ? `갱신: ${new Date(dataUpdatedAt).toLocaleTimeString('ko-KR')}` : '갱신 중...'}
        </button>
      </div>

      {/* 요약 카드 */}
      {dat && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="종목 수"    value={dat.stock_count.toLocaleString()}  sub="is_active" valueColor="text-[var(--fg)]" />
          <StatCard label="일봉 수"    value={dat.bar_count.toLocaleString()}     sub="daily_bars" valueColor="text-[var(--fg)]" />
          <StatCard label="이벤트 수"  value={dat.event_count.toLocaleString()}   sub="feature_events" valueColor="text-[var(--fg)]" />
          <StatCard label="벡터 수"    value={dat.vector_count.toLocaleString()}  sub="pgvector" valueColor="text-cyan-400" />
          <StatCard label="추천 수"    value={dat.rec_count.toLocaleString()}     sub="recommendations" valueColor="text-[var(--fg)]" />
          <StatCard label="벡터 커버리지" value={`${dat.pattern_vector_coverage.toFixed(1)}%`} sub="이벤트 대비"
            valueColor={dat.pattern_vector_coverage >= 75 ? 'text-green-400' : dat.pattern_vector_coverage >= 30 ? 'text-yellow-400' : 'text-red-400'} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* ML 모델 상태 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Cpu size={14} className="text-cyan-400" /> ML 모델
            </CardTitle>
            {ml && <StatusDot ok={ml.model_loaded} />}
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : ml ? (
              <div>
                <DataRow label="모델 상태"     value={ml.model_loaded ? '로드됨' : '미로드'} stale={!ml.model_loaded} />
                <DataRow label="학습 일시"     value={ml.trained_at ? fmt.smartTime(ml.trained_at) : null} />
                <DataRow label="AUC"           value={ml.auc != null ? ml.auc.toFixed(4) : null} />
                <DataRow label="F1"            value={ml.f1 != null ? ml.f1.toFixed(4) : null} />
                <DataRow label="최적 임계값"   value={ml.optimal_threshold != null ? ml.optimal_threshold.toFixed(3) : null} />
                <DataRow label="모델 경로"     value={ml.model_dir} />
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>

        {/* 서비스 상태 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Database size={14} className="text-cyan-400" /> 서비스 연결
            </CardTitle>
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-10 skeleton rounded" />)}</div>
            ) : svc ? (
              <div>
                <ServiceRow label="PostgreSQL (DB)" ok={svc.db} />
                <ServiceRow label="Redis"           ok={svc.redis} />
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>

        {/* Kafka Lag */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Radio size={14} className="text-cyan-400" /> Kafka 처리 지연
            </CardTitle>
            <span className="text-xs text-[var(--muted)]">메시지 수</span>
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : (
              Object.entries(lags).map(([topic, lag]) => (
                <LagRow key={topic} topic={topic} lag={lag} />
              ))
            )}
          </CardBody>
        </Card>

        {/* 데이터 신선도 */}
        <Card className="md:col-span-2 lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Clock size={14} className="text-cyan-400" /> 데이터 신선도
            </CardTitle>
          </CardHeader>
          <CardBody>
            {isLoading || !dat ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 skeleton rounded" />)}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-8">
                <DataRow label="최신 일봉"   value={dat.latest_daily_bar}       stale={isStale(dat.latest_daily_bar, 25)} />
                <DataRow label="최신 이벤트" value={dat.latest_feature_event ? fmt.smartTime(dat.latest_feature_event) : null} stale={isStale(dat.latest_feature_event, 2)} />
                <DataRow label="최신 추천"   value={dat.latest_recommendation ? fmt.smartTime(dat.latest_recommendation) : null} stale={isStale(dat.latest_recommendation, 2)} />
                <DataRow label="최신 공시"   value={dat.latest_disclosure ? fmt.smartTime(dat.latest_disclosure) : null} stale={isStale(dat.latest_disclosure, 8)} />
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
