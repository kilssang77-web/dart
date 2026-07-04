import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  CheckCircle2, XCircle, AlertTriangle, Cpu, Database,
  Radio, Activity, Clock, RefreshCw, History, CalendarClock,
  Play, ShieldCheck,
} from 'lucide-react'
import {
  adminApi,
  type SystemStatus,
  type BackfillJob,
  type BackfillStatus,
  type ScheduleStatus,
  type DataQuality,
} from '@/api/admin'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { fmt } from '@/lib/utils'

// ── 공통 헬퍼 컴포넌트 ──────────────────────────────────────────────────────────

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

// ── 백필 status Badge ─────────────────────────────────────────────────────────

type BackfillStatus2 = BackfillJob['status']

function statusVariant(s: BackfillStatus2) {
  if (s === 'done')    return 'green'
  if (s === 'running') return 'cyan'
  if (s === 'pending') return 'yellow'
  if (s === 'failed')  return 'red'
  return 'gray'
}

const STATUS_LABEL: Record<string, string> = {
  running: '실행 중',
  done:    '완료',
  failed:  '실패',
  pending: '대기',
  skipped: '건너뜀',
}

function BackfillStatusBadge({ status }: { status: BackfillJob['status'] }) {
  return (
    <Badge variant={statusVariant(status)}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  )
}

// ── 소요 시간 계산 ─────────────────────────────────────────────────────────────

function elapsed(started: string, finished: string | null): string {
  const end = finished ? new Date(finished) : new Date()
  const ms  = end.getTime() - new Date(started).getTime()
  if (ms < 0) return '—'
  const s = Math.floor(ms / 1000)
  if (s < 60)     return `${s}초`
  if (s < 3600)   return `${Math.floor(s / 60)}분 ${s % 60}초`
  return `${Math.floor(s / 3600)}시간 ${Math.floor((s % 3600) / 60)}분`
}

// ── 탭1: 시스템 헬스 (기존 내용) ─────────────────────────────────────────────

function HealthTab({ data, isLoading, dataUpdatedAt, refetch, isFetching }: {
  data?: SystemStatus
  isLoading: boolean
  dataUpdatedAt: number
  refetch: () => void
  isFetching: boolean
}) {
  const ml       = data?.ml
  const dat      = data?.data
  const svc      = data?.services
  const channels = data?.redis_channels ?? {}

  return (
    <div className="space-y-5">
      {/* 갱신 버튼 */}
      <div className="flex justify-end">
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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

        {/* 인프라 연결 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Database size={14} className="text-cyan-400" /> 인프라 연결
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

        {/* 마이크로서비스 상태 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Activity size={14} className="text-cyan-400" /> 마이크로서비스
            </CardTitle>
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : svc ? (
              <div>
                <ServiceRow label="ML 서비스 (8001)"          ok={svc.ml} />
                <ServiceRow label="추천 서비스 (Recommender)"  ok={svc.recommender} />
                <ServiceRow label="자동매매 서비스 (Trader)"   ok={svc.trader} />
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>

        {/* Redis Pub/Sub 채널 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Radio size={14} className="text-cyan-400" /> Redis Pub/Sub
            </CardTitle>
            <span className="text-xs text-[var(--muted)]">구독자 수</span>
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : (
              Object.entries(channels).length > 0 ? (
                Object.entries(channels).map(([ch, cnt]) => (
                  <div key={ch} className="flex items-center justify-between py-2.5 border-b border-[var(--border)] last:border-0">
                    <span className="text-sm text-[var(--fg)] font-mono">{ch}</span>
                    <span className={`text-xs font-semibold tabular ${cnt > 0 ? 'text-green-400' : 'text-[var(--muted)]'}`}>
                      {cnt < 0 ? '—' : cnt}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-sm text-[var(--muted)]">채널 정보 없음</p>
              )
            )}
          </CardBody>
        </Card>

        {/* 데이터 신선도 */}
        <Card className="md:col-span-2 lg:col-span-4">
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

// ── 탭2: 백필 이력 ────────────────────────────────────────────────────────────

function BackfillTab() {
  const queryClient = useQueryClient()

  const { data: statusData, isLoading: statusLoading } = useQuery<BackfillStatus>({
    queryKey:        ['backfill-status'],
    queryFn:         adminApi.getBackfillStatus,
    refetchInterval: 15_000,
  })

  const { data: history, isLoading: histLoading, refetch: refetchHist, isFetching: histFetching } =
    useQuery<BackfillJob[]>({
      queryKey:        ['backfill-history'],
      queryFn:         () => adminApi.getBackfillHistory(20),
      refetchInterval: 30_000,
    })

  const triggerMut = useMutation({
    mutationFn: (job_type: string) => adminApi.triggerBackfill(job_type),
    onSuccess: () => {
      alert('백필 트리거가 전송되었습니다.')
      queryClient.invalidateQueries({ queryKey: ['backfill-status'] })
      queryClient.invalidateQueries({ queryKey: ['backfill-history'] })
    },
    onError: (e: Error) => {
      alert(`트리거 실패: ${e.message}`)
    },
  })

  return (
    <div className="space-y-5">
      {/* 현재 상태 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Activity size={14} className="text-cyan-400" /> 현재 작업 상태
            </CardTitle>
          </CardHeader>
          <CardBody>
            {statusLoading ? (
              <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : statusData ? (
              <div>
                {statusData.current_job ? (
                  <>
                    <DataRow label="작업 유형"   value={statusData.current_job.job_type} />
                    <DataRow label="상태"        value={STATUS_LABEL[statusData.current_job.status] ?? statusData.current_job.status} />
                    <DataRow label="트리거"      value={statusData.current_job.triggered_by} />
                    <DataRow label="시작 시각"   value={fmt.smartTime(statusData.current_job.started_at)} />
                    <DataRow label="소요 시간"   value={elapsed(statusData.current_job.started_at, statusData.current_job.finished_at)} />
                  </>
                ) : (
                  <p className="text-sm text-[var(--muted)] py-2">실행 중인 작업 없음</p>
                )}
                <div className="pt-2 flex items-center gap-2 text-xs text-[var(--muted)]">
                  <span>Redis 마지막 실행:</span>
                  <span className="font-mono text-[var(--fg)]">{statusData.last_run_redis ?? '—'}</span>
                </div>
                {statusData.trigger_pending && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-yellow-400">
                    <AlertTriangle size={11} />
                    트리거 대기 중 (워커 폴링 예정)
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Play size={14} className="text-cyan-400" /> 수동 트리거
            </CardTitle>
          </CardHeader>
          <CardBody>
            <p className="text-xs text-[var(--muted)] mb-4">
              Redis 키를 설정하여 워커가 다음 폴링 시 백필을 실행하도록 트리거합니다.
            </p>
            <div className="flex flex-col gap-2">
              {(['bars', 'financials', 'govdata'] as const).map((jt) => (
                <button
                  key={jt}
                  onClick={() => triggerMut.mutate(jt)}
                  disabled={triggerMut.isPending}
                  className={clsx(
                    'flex items-center justify-between px-3 py-2 rounded-lg border text-sm',
                    'border-[var(--border)] bg-[var(--bg)] hover:border-cyan-500/50 hover:bg-cyan-500/5',
                    'transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                >
                  <span className="font-mono text-[var(--fg)]">{jt}</span>
                  <span className="text-xs text-cyan-400 flex items-center gap-1">
                    <Play size={11} />
                    트리거
                  </span>
                </button>
              ))}
            </div>
            {triggerMut.isPending && (
              <p className="text-xs text-[var(--muted)] mt-2 flex items-center gap-1">
                <RefreshCw size={11} className="animate-spin" />
                전송 중...
              </p>
            )}
          </CardBody>
        </Card>
      </div>

      {/* 이력 테이블 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-1.5">
              <History size={14} className="text-cyan-400" /> 백필 이력 (최근 20건)
            </CardTitle>
            <button
              onClick={() => refetchHist()}
              disabled={histFetching}
              className="flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
            >
              <RefreshCw size={11} className={histFetching ? 'animate-spin' : ''} />
              새로고침
            </button>
          </div>
        </CardHeader>
        <CardBody className="px-0 pb-0 pt-3">
          {histLoading ? (
            <div className="px-5 space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 skeleton rounded" />)}</div>
          ) : !history || history.length === 0 ? (
            <div className="px-5 pb-5 space-y-2">
              <p className="text-sm text-[var(--muted)]">이력 없음 — bars_backfill 워커가 장외 시간(22:00~06:00 KST)에 최초 실행되면 기록됩니다.</p>
              <p className="text-xs text-[var(--muted)]/60">수동 실행이 필요하면 우측 상단 <strong>수동 트리거</strong> 카드를 사용하세요.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)]">
                    {['#', '유형', '상태', '트리거', '대상', '성공', '건너뜀', '실패', '행추가', '시작', '소요'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left text-[var(--muted)] font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {history.map((job) => (
                    <tr key={job.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--card-hover,var(--card))] transition-colors">
                      <td className="px-3 py-2.5 text-[var(--muted)] tabular">{job.id}</td>
                      <td className="px-3 py-2.5 font-mono text-[var(--fg)] whitespace-nowrap">{job.job_type}</td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <BackfillStatusBadge status={job.status} />
                      </td>
                      <td className="px-3 py-2.5 text-[var(--muted)]">{job.triggered_by}</td>
                      <td className="px-3 py-2.5 tabular text-[var(--fg)]">{job.target_count?.toLocaleString() ?? '—'}</td>
                      <td className="px-3 py-2.5 tabular text-green-400">{job.success_count?.toLocaleString() ?? '—'}</td>
                      <td className="px-3 py-2.5 tabular text-yellow-400">{job.skip_count?.toLocaleString() ?? '—'}</td>
                      <td className="px-3 py-2.5 tabular text-red-400">{job.fail_count?.toLocaleString() ?? '—'}</td>
                      <td className="px-3 py-2.5 tabular text-cyan-400">{job.rows_added?.toLocaleString() ?? '—'}</td>
                      <td className="px-3 py-2.5 text-[var(--muted)] whitespace-nowrap">{fmt.smartTime(job.started_at)}</td>
                      <td className="px-3 py-2.5 text-[var(--muted)] whitespace-nowrap">{elapsed(job.started_at, job.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

// ── 탭3: 스케줄 현황 ──────────────────────────────────────────────────────────

interface ScheduleItem {
  label: string
  key: keyof ScheduleStatus
  description: string
  expectedInterval: string
  staleHours: number
}

const SCHEDULE_ITEMS: ScheduleItem[] = [
  { label: '일봉 백필',       key: 'bars_backfill_last', description: 'bars_backfill 워커 — daily_bars 누락봉 보완',    expectedInterval: '매일 22:00~06:00 KST', staleHours: 30 },
  { label: '재무 데이터',     key: 'financials_last',    description: 'financials 워커 — KIS 재무제표 7일 주기 수집',   expectedInterval: '7일 주기',             staleHours: 200 },
  { label: '정부 데이터',     key: 'govdata_last',       description: 'govdata 워커 — 금융위원회 API 종목 마스터 갱신', expectedInterval: '매일 18:00 KST',       staleHours: 30 },
  { label: 'Redis 통계 갱신', key: 'stats_last_refresh', description: '탐지 통계 Redis 키 갱신 (종목별 7개 키)',        expectedInterval: '수동 또는 자동 갱신', staleHours: 48 },
]

function ScheduleCard({ item, value }: { item: ScheduleItem; value: string | null }) {
  const stale = isStale(value, item.staleHours)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <CalendarClock size={13} className="text-cyan-400" />
            {item.label}
          </CardTitle>
          {value ? (
            stale
              ? <Badge variant="yellow"><AlertTriangle size={10} className="mr-1 inline" />지연</Badge>
              : <Badge variant="green"><CheckCircle2 size={10} className="mr-1 inline" />정상</Badge>
          ) : (
            <Badge variant="gray">미수집</Badge>
          )}
        </div>
      </CardHeader>
      <CardBody>
        <p className="text-xs text-[var(--muted)] mb-3">{item.description}</p>
        <div className="space-y-1">
          <div className="flex justify-between items-center">
            <span className="text-xs text-[var(--muted)]">마지막 실행</span>
            <span className={clsx('text-xs font-mono', stale ? 'text-yellow-400' : 'text-[var(--fg)]')}>
              {value ? fmt.smartTime(value) : '—'}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-[var(--muted)]">예정 주기</span>
            <span className="text-xs text-[var(--muted)]">{item.expectedInterval}</span>
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

function ScheduleTab() {
  const { data, isLoading, refetch, isFetching } = useQuery<ScheduleStatus>({
    queryKey:        ['schedule-status'],
    queryFn:         adminApi.getScheduleStatus,
    refetchInterval: 60_000,
  })

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
        >
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-36 skeleton rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SCHEDULE_ITEMS.map((item) => (
            <ScheduleCard
              key={item.key}
              item={item}
              value={data ? data[item.key] : null}
            />
          ))}
        </div>
      )}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Clock size={13} className="text-cyan-400" /> Redis 원시 값 (디버그용)
            </CardTitle>
          </CardHeader>
          <CardBody>
            <div className="font-mono text-xs text-[var(--muted)] space-y-1">
              <div className="flex gap-3"><span className="w-48 shrink-0">bars_backfill:last</span><span className="text-[var(--fg)]">{data.bars_backfill_last ?? '(없음)'}</span></div>
              <div className="flex gap-3"><span className="w-48 shrink-0">financials:last_run</span><span className="text-[var(--fg)]">{data.financials_last ?? '(없음)'}</span></div>
              <div className="flex gap-3"><span className="w-48 shrink-0">govdata:last_run</span><span className="text-[var(--fg)]">{data.govdata_last ?? '(없음)'}</span></div>
              <div className="flex gap-3"><span className="w-48 shrink-0">stats:last_refresh</span><span className="text-[var(--fg)]">{data.stats_last_refresh ?? '(없음)'}</span></div>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}

// ── 탭4: 데이터 품질 ─────────────────────────────────────────────────────────

function CoverageBar({ pct, warn = 90, danger = 70 }: { pct: number; warn?: number; danger?: number }) {
  const color = pct >= warn ? 'bg-green-400' : pct >= danger ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-[var(--border)] rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className={clsx('text-xs font-bold tabular w-12 text-right',
        pct >= warn ? 'text-green-400' : pct >= danger ? 'text-yellow-400' : 'text-red-400'
      )}>{pct.toFixed(1)}%</span>
    </div>
  )
}

function DataQualityTab() {
  const { data, isLoading, refetch, isFetching } = useQuery<DataQuality>({
    queryKey:        ['data-quality'],
    queryFn:         adminApi.getDataQuality,
    refetchInterval: 120_000,
  })

  const bars = data?.bar_completeness
  const sd   = data?.supply_coverage
  const ml   = data?.ml_confidence

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
        >
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 일봉 완성도 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Database size={14} className="text-cyan-400" /> 일봉 완성도
            </CardTitle>
            {bars && (
              <span className={clsx('text-xs font-semibold',
                bars.coverage_7d_pct >= 90 ? 'text-green-400' : bars.coverage_7d_pct >= 70 ? 'text-yellow-400' : 'text-red-400'
              )}>
                {bars.coverage_7d_pct.toFixed(1)}%
              </span>
            )}
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : bars ? (
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--muted)]">7일 내 일봉 보유 종목</span>
                    <span className="text-[var(--fg)] tabular">{bars.bars_last7d_stocks.toLocaleString()} / {bars.active_stocks.toLocaleString()}</span>
                  </div>
                  <CoverageBar pct={bars.coverage_7d_pct} />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--muted)]">당일 일봉 보유 종목</span>
                    <span className="text-[var(--fg)] tabular">{bars.bars_today_stocks.toLocaleString()} / {bars.active_stocks.toLocaleString()}</span>
                  </div>
                  <CoverageBar pct={bars.coverage_today_pct} />
                </div>
                <DataRow label="최신 일봉" value={bars.latest_bar_date} stale={isStale(bars.latest_bar_date, 25)} />
                {bars.missing_bars_count > 0 && (
                  <div className="mt-2 p-2.5 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
                    <div className="flex items-center gap-1.5 text-xs text-yellow-400 font-semibold mb-1.5">
                      <AlertTriangle size={11} />
                      결측 종목 {bars.missing_bars_count.toLocaleString()}개
                    </div>
                    {bars.missing_bars_sample.slice(0, 5).map((s) => (
                      <div key={s.code} className="flex justify-between text-[10px] text-[var(--muted)] py-0.5">
                        <span>{s.name} ({s.code})</span>
                        <span>{s.last_bar_date ?? '없음'}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>

        {/* 수급 커버리지 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Activity size={14} className="text-cyan-400" /> 수급 커버리지
            </CardTitle>
            {sd && (
              <span className={clsx('text-xs font-semibold',
                sd.coverage_30d_pct >= 90 ? 'text-green-400' : sd.coverage_30d_pct >= 70 ? 'text-yellow-400' : 'text-red-400'
              )}>
                {sd.coverage_30d_pct.toFixed(1)}%
              </span>
            )}
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : sd ? (
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--muted)]">7일 수급 보유 종목</span>
                    <span className="text-[var(--fg)] tabular">{sd.coverage_7d_stocks.toLocaleString()}</span>
                  </div>
                  <CoverageBar pct={sd.coverage_7d_pct} />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--muted)]">30일 수급 보유 종목</span>
                    <span className="text-[var(--fg)] tabular">{sd.coverage_30d_stocks.toLocaleString()}</span>
                  </div>
                  <CoverageBar pct={sd.coverage_30d_pct} />
                </div>
                <DataRow label="최신 수급" value={sd.latest_sd_date} stale={isStale(sd.latest_sd_date, 25)} />
                {sd.missing_stocks > 0 && (
                  <div className="text-xs text-yellow-400 flex items-center gap-1.5 mt-1">
                    <AlertTriangle size={11} />
                    수급 미수집 {sd.missing_stocks.toLocaleString()}개 종목
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>

        {/* ML 신뢰도 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5 text-sm">
              <Cpu size={14} className="text-cyan-400" /> ML 신뢰도
            </CardTitle>
            {ml && (
              <span className={clsx('text-xs font-semibold',
                ml.model_loaded
                  ? (ml.auc != null && ml.auc >= 0.60 ? 'text-green-400' : 'text-yellow-400')
                  : 'text-red-400'
              )}>
                {ml.model_loaded ? (ml.auc != null ? `AUC ${ml.auc.toFixed(4)}` : '로드됨') : '미로드'}
              </span>
            )}
          </CardHeader>
          <CardBody>
            {isLoading ? (
              <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-8 skeleton rounded" />)}</div>
            ) : ml ? (
              <div>
                <DataRow label="모델 상태"     value={ml.model_loaded ? '로드됨' : '미로드'} stale={!ml.model_loaded} />
                <DataRow label="AUC"           value={ml.auc != null ? ml.auc.toFixed(4) : null} />
                <DataRow label="F1"            value={ml.f1 != null ? ml.f1.toFixed(4) : null} />
                <DataRow label="임계값"        value={ml.threshold != null ? ml.threshold.toFixed(3) : null} />
                <DataRow label="피처 수"       value={ml.feature_count?.toLocaleString() ?? null} />
                <DataRow label="학습 샘플"     value={ml.train_samples?.toLocaleString() ?? null} />
                <DataRow label="모델 나이"     value={ml.model_age_days != null ? `${ml.model_age_days}일` : null}
                  stale={ml.model_age_days != null && ml.model_age_days > 14} />
                <div className="mt-2">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--muted)]">벡터 커버리지</span>
                    <span className="text-[var(--fg)] tabular">{ml.vector_coverage_pct.toFixed(1)}%</span>
                  </div>
                  <CoverageBar pct={ml.vector_coverage_pct} warn={75} danger={30} />
                </div>
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">데이터 없음</p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}

// ── 탭 헤더 ───────────────────────────────────────────────────────────────────

type Tab = 'health' | 'backfill' | 'schedule' | 'quality'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'health',   label: '시스템 헬스',  icon: <Activity size={13} /> },
  { id: 'backfill', label: '백필 이력',    icon: <History size={13} /> },
  { id: 'schedule', label: '스케줄 현황',  icon: <CalendarClock size={13} /> },
  { id: 'quality',  label: '데이터 품질',  icon: <ShieldCheck size={13} /> },
]

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export function SystemHealth() {
  const [tab, setTab] = useState<Tab>('health')

  const { data, isLoading, dataUpdatedAt, refetch, isFetching } = useQuery<SystemStatus>({
    queryKey:        ['system-status'],
    queryFn:         adminApi.getSystemStatus,
    refetchInterval: 60_000,
  })

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-[var(--fg)] flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" />
          시스템 헬스 대시보드
        </h1>
      </div>

      {/* 탭 헤더 */}
      <div className="flex items-center gap-1 border-b border-[var(--border)]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === t.id
                ? 'border-cyan-400 text-cyan-400'
                : 'border-transparent text-[var(--muted)] hover:text-[var(--fg)]',
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      {tab === 'health' && (
        <HealthTab
          data={data}
          isLoading={isLoading}
          dataUpdatedAt={dataUpdatedAt}
          refetch={refetch}
          isFetching={isFetching}
        />
      )}
      {tab === 'backfill' && <BackfillTab />}
      {tab === 'schedule' && <ScheduleTab />}
      {tab === 'quality'  && <DataQualityTab />}
    </div>
  )
}
