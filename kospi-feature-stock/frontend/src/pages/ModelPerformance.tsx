import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Activity, Radio, TrendingUp, BarChart2, Clock, CheckCircle2, RefreshCw, Loader2, XCircle } from 'lucide-react'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, ReferenceLine,
} from 'recharts'
import {
  marketApi,
  type ModelMetrics, type KafkaLag, type ShapExplain,
  type PerformanceTrendPoint, type EventPerformance, type ModelHistoryItem,
  type RetrainStatus,
} from '@/api/market'
import { fmt } from '@/lib/utils'
import { EVENT_LABELS } from '@/components/ui/Badge'

const LAG_WARN  = 500
const LAG_ERROR = 2000

function RetrainButton({
  status, loading, isRetraining, onRetrain,
}: {
  status:       RetrainStatus | undefined
  loading:      boolean
  isRetraining: boolean
  onRetrain:    () => void
}) {
  const disabled = loading || isRetraining
  const s = status?.status

  return (
    <div className="flex items-center gap-1.5">
      {s === 'done' && (
        <span className="flex items-center gap-1 text-xs text-green-400">
          <CheckCircle2 size={12} /> 완료
        </span>
      )}
      {s === 'failed' && (
        <span className="flex items-center gap-1 text-xs text-red-400">
          <XCircle size={12} /> 실패
        </span>
      )}
      {isRetraining && (
        <span className="flex items-center gap-1 text-xs text-yellow-400">
          <Loader2 size={12} className="animate-spin" />
          {s === 'pending' ? '대기 중...' : '학습 중...'}
        </span>
      )}
      <button
        onClick={onRetrain}
        disabled={disabled}
        className={clsx(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border',
          disabled
            ? 'opacity-50 cursor-not-allowed bg-[var(--card)] text-[var(--muted)] border-[var(--border)]'
            : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/20',
        )}
      >
        {isRetraining
          ? <Loader2 size={12} className="animate-spin" />
          : <RefreshCw size={12} />}
        재학습
      </button>
    </div>
  )
}

function LagBar({ label, lag, max }: { label: string; lag: number; max: number }) {
  const pct   = max > 0 ? Math.min(100, (lag / max) * 100) : 0
  const color = lag >= LAG_ERROR ? '#f87171' : lag >= LAG_WARN ? '#facc15' : '#4ade80'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-[var(--muted)] font-mono truncate">{label}</span>
        <span className="tabular font-semibold" style={{ color }}>{lag.toLocaleString()}</span>
      </div>
      <div className="h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

const TOOLTIP_STYLE = {
  background: 'var(--card)', border: '1px solid var(--border)',
  borderRadius: 8, fontSize: 12, color: 'var(--fg)',
}

type TrendDays = 7 | 30 | 90
type EventDays = 30 | 90 | 180

export function ModelPerformance() {
  const [trendDays, setTrendDays]         = useState<TrendDays>(30)
  const [eventDays, setEventDays]         = useState<EventDays>(90)
  const [retrainLoading, setRetrainLoading] = useState(false)
  const queryClient = useQueryClient()

  const { data: retrainStatus } = useQuery<RetrainStatus>({
    queryKey:        ['retrain-status'],
    queryFn:         marketApi.getRetrainStatus,
    staleTime:       0,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'running' || s === 'pending' ? 3000 : false
    },
  })

  const isRetraining = retrainStatus?.status === 'running' || retrainStatus?.status === 'pending'

  useEffect(() => {
    if (retrainStatus?.status === 'done' || retrainStatus?.status === 'failed') {
      setRetrainLoading(false)
      queryClient.invalidateQueries({ queryKey: ['model-metrics'] })
      queryClient.invalidateQueries({ queryKey: ['model-history'] })
    }
  }, [retrainStatus?.status, queryClient])

  const handleRetrain = async () => {
    setRetrainLoading(true)
    try {
      await marketApi.triggerRetrain()
      queryClient.invalidateQueries({ queryKey: ['retrain-status'] })
    } catch {
      setRetrainLoading(false)
    }
  }

  const { data: metrics, isLoading } = useQuery<ModelMetrics | null>({
    queryKey:  ['model-metrics'],
    queryFn:   marketApi.getModelMetrics,
    staleTime: 300_000,
  })
  const { data: kafkaLag } = useQuery<KafkaLag>({
    queryKey:       ['kafka-lag'],
    queryFn:        marketApi.getKafkaLag,
    staleTime:      30_000,
    refetchInterval: 30_000,
  })
  const { data: shap } = useQuery<ShapExplain>({
    queryKey: ['shap-explain'],
    queryFn:  marketApi.getShapExplain,
    staleTime: 600_000,
    retry: false,
  })
  const { data: trend = [] } = useQuery<PerformanceTrendPoint[]>({
    queryKey: ['perf-trend', trendDays],
    queryFn:  () => marketApi.getPerformanceTrend(trendDays),
    staleTime: 300_000,
  })
  const { data: eventPerf = [] } = useQuery<EventPerformance[]>({
    queryKey: ['event-perf', eventDays],
    queryFn:  () => marketApi.getEventPerformance(eventDays),
    staleTime: 300_000,
  })
  const { data: modelHistory = [] } = useQuery<ModelHistoryItem[]>({
    queryKey: ['model-history'],
    queryFn:  marketApi.getModelHistory,
    staleTime: 600_000,
  })

  const featureData = metrics?.feature_importance
    ? Object.entries(metrics.feature_importance)
        .sort(([, a], [, b]) => b - a).slice(0, 20)
        .map(([name, importance]) => ({ name, importance }))
    : []

  const eventChartData = eventPerf.map((e) => ({
    name:          EVENT_LABELS[e.event_type] ?? e.event_type,
    승률:           e.win_rate,
    평균수익률:      e.avg_return_5d,
    건수:           e.total,
  }))

  const totalRecs  = trend.reduce((s, d) => s + d.total, 0)
  const totalWins  = trend.reduce((s, d) => s + d.wins, 0)
  const avgWinRate = totalRecs > 0 ? Math.round(totalWins / totalRecs * 100) : 0
  const avgReturn5d = trend.length > 0
    ? (trend.reduce((s, d) => s + d.avg_return_5d, 0) / trend.length).toFixed(2)
    : '0.00'

  return (
    <div className="p-6 space-y-5">

      {/* ── Kafka Lag ── */}
      {kafkaLag && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>
                <span className="flex items-center gap-1.5">
                  <Radio size={14} className="text-cyan-400" /> Kafka 컨슈머 Lag
                </span>
              </CardTitle>
              <div className={clsx(
                'px-2.5 py-0.5 rounded-full text-xs font-semibold border',
                kafkaLag.total_lag >= LAG_ERROR
                  ? 'bg-red-500/15 text-red-400 border-red-500/30'
                  : kafkaLag.total_lag >= LAG_WARN
                  ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                  : 'bg-green-500/15 text-green-400 border-green-500/30',
              )}>
                Total {kafkaLag.total_lag.toLocaleString()}
              </div>
            </div>
          </CardHeader>
          <CardBody>
            {kafkaLag.error ? (
              <p className="text-xs text-[var(--muted)]">{kafkaLag.error}</p>
            ) : Object.keys(kafkaLag.by_topic).length === 0 ? (
              <p className="text-xs text-[var(--muted)]">Detector 미실행 — lag 데이터 없음</p>
            ) : (
              <div className="space-y-3">
                {Object.entries(kafkaLag.by_topic).map(([topic, lag]) => (
                  <LagBar key={topic} label={topic} lag={lag}
                    max={Math.max(...Object.values(kafkaLag.by_topic), 1)} />
                ))}
                <p className="text-xs text-[var(--muted)] pt-1">
                  30초마다 자동 갱신 · 경고 ≥{LAG_WARN.toLocaleString()} · 위험 ≥{LAG_ERROR.toLocaleString()}
                </p>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {/* ── 추천 성과 요약 카드 ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="기간 추천 건수" value={totalRecs.toLocaleString()} sub={`최근 ${trendDays}일`} valueColor="text-[var(--fg)]" />
        <StatCard label="승률" value={`${avgWinRate}%`} sub="5일 기준"
          valueColor={avgWinRate >= 55 ? 'text-green-400' : avgWinRate >= 40 ? 'text-yellow-400' : 'text-red-400'} />
        <StatCard label="평균 5일 수익률" value={`${avgReturn5d}%`} sub="완료된 추천"
          valueColor={parseFloat(avgReturn5d) >= 0 ? 'text-green-400' : 'text-red-400'} />
        <StatCard label="이벤트 유형 수" value={eventPerf.length.toString()} sub={`최근 ${eventDays}일 활성`} valueColor="text-cyan-400" />
      </div>

      {/* ── 일별 승률·수익률 추이 ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <TrendingUp size={14} className="text-green-400" /> 일별 추천 성과 추이
              </span>
            </CardTitle>
            <div className="flex gap-1">
              {([7, 30, 90] as TrendDays[]).map((d) => (
                <button key={d} onClick={() => setTrendDays(d)}
                  className={clsx(
                    'px-2.5 py-0.5 rounded text-xs font-medium transition-colors',
                    trendDays === d
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                      : 'text-[var(--muted)] hover:text-[var(--fg)]',
                  )}>
                  {d}일
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardBody>
          {trend.length === 0 ? (
            <div className="flex items-center justify-center h-48 text-[var(--muted)] text-sm">
              완료된 추천 추적 데이터가 없습니다. 추천 성과가 집계되면 표시됩니다.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={trend} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#71717a' }}
                  tickFormatter={(v) => v.slice(5)} />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#71717a' }}
                  tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#71717a' }}
                  tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v: number, name: string) => [`${v.toFixed(1)}%`, name]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine yAxisId="left" y={50} stroke="#71717a" strokeDasharray="4 4" />
                <Line yAxisId="left" type="monotone" dataKey="win_rate" name="승률"
                  stroke="#4ade80" strokeWidth={2} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey="avg_return_5d" name="5일수익률"
                  stroke="#22d3ee" strokeWidth={2} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey="avg_return_1d" name="1일수익률"
                  stroke="#a78bfa" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardBody>
      </Card>

      {/* ── 이벤트 유형별 성과 ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <BarChart2 size={14} className="text-purple-400" /> 이벤트 유형별 성과
              </span>
            </CardTitle>
            <div className="flex gap-1">
              {([30, 90, 180] as EventDays[]).map((d) => (
                <button key={d} onClick={() => setEventDays(d)}
                  className={clsx(
                    'px-2.5 py-0.5 rounded text-xs font-medium transition-colors',
                    eventDays === d
                      ? 'bg-purple-500/20 text-purple-400 border border-purple-500/40'
                      : 'text-[var(--muted)] hover:text-[var(--fg)]',
                  )}>
                  {d}일
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardBody>
          {eventChartData.length === 0 ? (
            <div className="flex items-center justify-center h-48 text-[var(--muted)] text-sm">
              이벤트 성과 데이터가 없습니다.
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={eventChartData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#71717a' }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#71717a' }}
                    tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#71717a' }}
                    tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <ReferenceLine yAxisId="left" y={50} stroke="#71717a" strokeDasharray="4 4" />
                  <Bar yAxisId="left" dataKey="승률" fill="#4ade80" radius={[3, 3, 0, 0]} opacity={0.85} />
                  <Bar yAxisId="right" dataKey="평균수익률" fill="#22d3ee" radius={[3, 3, 0, 0]} opacity={0.75} />
                </BarChart>
              </ResponsiveContainer>
              {/* 테이블 */}
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                      <th className="text-left py-1.5 font-medium">이벤트</th>
                      <th className="text-right py-1.5 font-medium">건수</th>
                      <th className="text-right py-1.5 font-medium">승률</th>
                      <th className="text-right py-1.5 font-medium">5일 수익률</th>
                      <th className="text-right py-1.5 font-medium">예측 확률</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {eventPerf.map((e) => (
                      <tr key={e.event_type} className="hover:bg-white/5">
                        <td className="py-1.5 font-mono text-[var(--fg)]">
                          {EVENT_LABELS[e.event_type] ?? e.event_type}
                        </td>
                        <td className="py-1.5 text-right tabular text-[var(--muted)]">{e.total}</td>
                        <td className={clsx('py-1.5 text-right tabular font-semibold',
                          e.win_rate >= 55 ? 'text-green-400' : e.win_rate >= 40 ? 'text-yellow-400' : 'text-red-400')}>
                          {e.win_rate.toFixed(1)}%
                        </td>
                        <td className={clsx('py-1.5 text-right tabular',
                          e.avg_return_5d >= 0 ? 'text-green-400' : 'text-red-400')}>
                          {e.avg_return_5d >= 0 ? '+' : ''}{e.avg_return_5d.toFixed(2)}%
                        </td>
                        <td className="py-1.5 text-right tabular text-cyan-400">
                          {(e.avg_pred_prob * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardBody>
      </Card>

      {/* ── ML 모델 현재 메트릭 ── */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => <div key={i} className="h-24 skeleton rounded-xl" />)}
        </div>
      ) : !metrics ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2.5 p-3 bg-amber-500/10 border border-amber-500/25 rounded-xl text-amber-300 text-xs">
            <span className="font-semibold text-amber-400">⚠ ML 모델 미학습</span>
            현재 규칙 기반(fallback) 모드로 운영 중입니다.
          </div>
          <div className="flex flex-col items-center justify-center py-10 gap-4 text-[var(--muted)]">
            <Activity size={28} className="opacity-30" />
            <p className="text-sm">학습된 모델이 없습니다.</p>
            <RetrainButton
              status={retrainStatus}
              loading={retrainLoading}
              isRetraining={isRetraining}
              onRetrain={handleRetrain}
            />
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-4 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-400 to-green-400 flex items-center justify-center flex-shrink-0">
              <Activity size={18} className="text-white" />
            </div>
            <div>
              <div className="font-semibold text-[var(--fg)]">{metrics.model_type}</div>
              <div className="text-xs text-[var(--muted)] mt-0.5">
                학습일: {fmt.dateTime(metrics.trained_at)} · 피처 {metrics.n_features}개
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <RetrainButton
                status={retrainStatus}
                loading={retrainLoading}
                isRetraining={isRetraining}
                onRetrain={handleRetrain}
              />
              <div className={clsx(
                'px-3 py-1 rounded-full text-xs font-semibold border',
                metrics.auc >= 0.7
                  ? 'bg-green-500/15 text-green-400 border-green-500/30'
                  : 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
              )}>
                AUC {metrics.auc.toFixed(4)}
              </div>
            </div>
          </div>

          {metrics.auc < 0.65 && (
            <div className="flex items-center gap-2.5 p-3 bg-amber-500/10 border border-amber-500/25 rounded-xl text-amber-300 text-xs">
              <span className="font-semibold text-amber-400">⚠ 모델 성능 미달</span>
              AUC {metrics.auc.toFixed(3)} — 권장 기준(0.70) 미만입니다. 추천은 규칙 기반 fallback으로 보완 중입니다.
            </div>
          )}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="AUC"
              value={metrics.auc.toFixed(4)}
              sub={metrics.auc >= 0.70 ? '권장 기준 충족 (≥ 0.70)' : '권장: 0.70 이상'}
              valueColor={metrics.auc >= 0.7 ? 'text-green-400' : 'text-yellow-400'} />
            <StatCard label="F1 Score"
              value={metrics.f1.toFixed(4)}
              sub={metrics.f1 >= 0.50 ? '권장 기준 충족 (≥ 0.50)' : '권장: 0.50 이상'}
              valueColor={metrics.f1 >= 0.50 ? 'text-green-400' : 'text-yellow-400'} />
            <StatCard label="Precision" value={metrics.precision.toFixed(4)} sub="정밀도 (매수 신호 중 실제 성공)" valueColor="text-cyan-400" />
            <StatCard label="Recall" value={metrics.recall.toFixed(4)} sub="재현율 (실제 성공 중 탐지 비율)" valueColor="text-purple-400" />
          </div>

          {featureData.length > 0 && (
            <Card>
              <CardHeader><CardTitle>피처 중요도 Top 20</CardTitle></CardHeader>
              <CardBody>
                <ResponsiveContainer width="100%" height={420}>
                  <BarChart data={featureData} layout="vertical"
                    margin={{ top: 4, right: 16, bottom: 4, left: 120 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 12, fill: '#71717a' }}
                      tickFormatter={(v) => v.toFixed(3)} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 12, fill: '#71717a' }} width={115} />
                    <Tooltip formatter={(v: number) => [v.toFixed(4), '중요도']} contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="importance" fill="#22d3ee" radius={[0, 3, 3, 0]} opacity={0.8} />
                  </BarChart>
                </ResponsiveContainer>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle>모델 상세</CardTitle></CardHeader>
            <CardBody>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                <div>
                  <div className="text-xs text-[var(--muted)] mb-1">모델 종류</div>
                  <div className="font-semibold text-[var(--fg)]">{metrics.model_type}</div>
                </div>
                <div>
                  <div className="text-xs text-[var(--muted)] mb-1">전체 피처 수</div>
                  <div className="font-semibold tabular text-cyan-400">{metrics.n_features}개</div>
                </div>
                <div>
                  <div className="text-xs text-[var(--muted)] mb-1">마지막 학습</div>
                  <div className="font-semibold text-[var(--fg)]">{fmt.dateTime(metrics.trained_at)}</div>
                </div>
                <div>
                  <div className="text-xs text-[var(--muted)] mb-1">정확도</div>
                  <div className="font-semibold tabular">{(metrics.accuracy * 100).toFixed(2)}%</div>
                </div>
                {metrics.brier_score != null && (
                  <div>
                    <div className="text-xs text-[var(--muted)] mb-1">Brier Score</div>
                    <div className={clsx('font-semibold tabular',
                      metrics.brier_score < 0.2 ? 'text-green-400' : 'text-yellow-400')}>
                      {metrics.brier_score.toFixed(4)}
                    </div>
                  </div>
                )}
              </div>
            </CardBody>
          </Card>
        </>
      )}

      {/* ── 모델 이력 ── */}
      {modelHistory.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <Clock size={14} className="text-yellow-400" /> 모델 버전 이력
              </span>
            </CardTitle>
          </CardHeader>
          <CardBody>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="text-left py-1.5 font-medium">상태</th>
                    <th className="text-left py-1.5 font-medium">모델</th>
                    <th className="text-left py-1.5 font-medium">버전</th>
                    <th className="text-right py-1.5 font-medium">학습일</th>
                    <th className="text-right py-1.5 font-medium">AUC</th>
                    <th className="text-right py-1.5 font-medium">F1</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {modelHistory.map((m) => (
                    <tr key={m.id} className="hover:bg-white/5">
                      <td className="py-1.5">
                        {m.is_active
                          ? <span className="flex items-center gap-1 text-green-400"><CheckCircle2 size={11} />활성</span>
                          : <span className="text-[var(--muted)]">비활성</span>}
                      </td>
                      <td className="py-1.5 font-mono text-[var(--fg)]">{m.model_type}</td>
                      <td className="py-1.5 text-[var(--muted)]">{m.version ?? '-'}</td>
                      <td className="py-1.5 text-right tabular text-[var(--muted)]">
                        {m.trained_at ? fmt.dateTime(m.trained_at) : '-'}
                      </td>
                      <td className="py-1.5 text-right tabular text-cyan-400">
                        {m.metrics.auc != null ? m.metrics.auc.toFixed(4) : '-'}
                      </td>
                      <td className="py-1.5 text-right tabular text-[var(--fg)]">
                        {m.metrics.f1 != null ? m.metrics.f1.toFixed(4) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}

      {/* ── SHAP 피처 기여도 ── */}
      {shap && !shap.error && shap.values.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>SHAP 피처 기여도</CardTitle>
              <span className="text-xs text-[var(--muted)]">
                중립 샘플 기준 · entry 모델 · base {shap.base_value.toFixed(4)}
              </span>
            </div>
          </CardHeader>
          <CardBody>
            <div className="space-y-1.5">
              {shap.values.map(({ feature, shap: val }) => {
                const positive = val >= 0
                const barW = Math.min(100,
                  Math.abs(val) / (shap.values[0] ? Math.abs(shap.values[0].shap) + 1e-9 : 1) * 100)
                return (
                  <div key={feature} className="flex items-center gap-2 text-xs">
                    <span className="w-40 text-right text-[var(--muted)] font-mono truncate shrink-0">{feature}</span>
                    <div className="flex-1 flex items-center gap-1 relative h-4">
                      <div className="absolute inset-0 flex items-center">
                        <div className="w-1/2 flex justify-end pr-0.5">
                          {!positive && (
                            <div className="h-3 rounded-l bg-blue-500/70" style={{ width: `${barW}%` }} />
                          )}
                        </div>
                        <div className="w-px h-4 bg-[var(--border)]" />
                        <div className="w-1/2 pl-0.5">
                          {positive && (
                            <div className="h-3 rounded-r bg-red-500/70" style={{ width: `${barW}%` }} />
                          )}
                        </div>
                      </div>
                    </div>
                    <span className={clsx(
                      'w-16 text-right tabular font-semibold shrink-0',
                      positive ? 'text-red-400' : 'text-blue-400',
                    )}>
                      {positive ? '+' : ''}{val.toFixed(4)}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="text-xs text-[var(--muted)] mt-3">
              빨강=매수 확률 상승 기여 · 파랑=매수 확률 하락 기여
            </p>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
