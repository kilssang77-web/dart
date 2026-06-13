import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Activity, Radio } from 'lucide-react'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { marketApi, type ModelMetrics, type KafkaLag } from '@/api/market'
import { fmt } from '@/lib/utils'

const LAG_WARN  = 500
const LAG_ERROR = 2000

function LagBar({ label, lag, max }: { label: string; lag: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (lag / max) * 100) : 0
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

export function ModelPerformance() {
  const { data: metrics, isLoading } = useQuery<ModelMetrics | null>({
    queryKey:  ['model-metrics'],
    queryFn:   marketApi.getModelMetrics,
    staleTime: 300_000,
  })

  const { data: kafkaLag } = useQuery<KafkaLag>({
    queryKey:  ['kafka-lag'],
    queryFn:   marketApi.getKafkaLag,
    staleTime: 30_000,
    refetchInterval: 30_000,
  })

  const featureData = metrics?.feature_importance
    ? Object.entries(metrics.feature_importance)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 20)
        .map(([name, importance]) => ({ name, importance }))
    : []

  return (
    <div className="p-6 space-y-5">

      {/* Kafka 컨슈머 Lag 모니터 */}
      {kafkaLag && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>
                <span className="flex items-center gap-1.5"><Radio size={14} className="text-cyan-400" /> Kafka 컨슈머 Lag</span>
              </CardTitle>
              <div className={clsx(
                'px-2.5 py-0.5 rounded-full text-xs font-semibold border',
                kafkaLag.total_lag >= LAG_ERROR
                  ? 'bg-red-500/15 text-red-400 border-red-500/30'
                  : kafkaLag.total_lag >= LAG_WARN
                  ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                  : 'bg-green-500/15 text-green-400 border-green-500/30'
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
                  <LagBar
                    key={topic}
                    label={topic}
                    lag={lag}
                    max={Math.max(...Object.values(kafkaLag.by_topic), 1)}
                  />
                ))}
                <p className="text-xs text-[var(--muted)] pt-1">30초마다 자동 갱신 · 경고 ≥{LAG_WARN.toLocaleString()} · 위험 ≥{LAG_ERROR.toLocaleString()}</p>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {isLoading ? (
        <div className="space-y-5">
          <div className="h-20 skeleton rounded-xl" />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 skeleton rounded-xl" />
            ))}
          </div>
          <div className="h-96 skeleton rounded-xl" />
          <div className="h-52 skeleton rounded-xl" />
        </div>
      ) : !metrics ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-[var(--muted)]">
          <Activity size={32} className="opacity-30" />
          <p className="text-sm">학습된 모델이 없습니다. bootstrap을 실행하세요.</p>
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
              <div className={clsx(
                'px-3 py-1 rounded-full text-xs font-semibold border',
                metrics.auc >= 0.7
                  ? 'bg-green-500/15 text-green-400 border-green-500/30'
                  : 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
              )}>
                AUC {metrics.auc.toFixed(4)}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="AUC" value={metrics.auc.toFixed(4)} sub="ROC-AUC"
              valueColor={metrics.auc >= 0.7 ? 'text-green-400' : 'text-yellow-400'} />
            <StatCard label="F1 Score" value={metrics.f1.toFixed(4)} sub="Weighted F1"
              valueColor={metrics.f1 >= 0.65 ? 'text-green-400' : 'text-yellow-400'} />
            <StatCard label="Precision" value={metrics.precision.toFixed(4)} sub="정밀도"
              valueColor="text-cyan-400" />
            <StatCard label="Recall" value={metrics.recall.toFixed(4)} sub="재현율"
              valueColor="text-purple-400" />
          </div>

          {featureData.length > 0 && (
            <Card>
              <CardHeader><CardTitle>피처 중요도 Top 20</CardTitle></CardHeader>
              <CardBody>
                <ResponsiveContainer width="100%" height={420}>
                  <BarChart
                    data={featureData}
                    layout="vertical"
                    margin={{ top: 4, right: 16, bottom: 4, left: 120 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 12, fill: '#71717a' }}
                      tickFormatter={(v) => v.toFixed(3)} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 12, fill: '#71717a' }} width={115} />
                    <Tooltip
                      formatter={(v: number) => [v.toFixed(4), '중요도']}
                      contentStyle={{
                        background: 'var(--card)', border: '1px solid var(--border)',
                        borderRadius: 8, fontSize: 12, color: 'var(--fg)',
                      }}
                    />
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
                  <div className="font-semibold tabular text-[var(--fg)]">{(metrics.accuracy * 100).toFixed(2)}%</div>
                </div>
                {metrics.brier_score != null && (
                  <div>
                    <div className="text-xs text-[var(--muted)] mb-1">Brier Score</div>
                    <div className={clsx('font-semibold tabular', metrics.brier_score < 0.2 ? 'text-green-400' : 'text-yellow-400')}>
                      {metrics.brier_score.toFixed(4)}
                    </div>
                  </div>
                )}
              </div>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  )
}