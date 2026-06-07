import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { kpiApi, outcomesApi } from '../api'

interface KPIData {
  period_type: string
  snapshot_date: string
  total_bids: number
  total_wins: number
  win_rate: number
  monthly_target: number
  target_achievement: number
  qualify_pass_rate?: number
  avg_rank_at_loss?: number
  srate_mae?: number
  win_prob_calibration?: number
  go_rate?: number
  no_go_saved: number
  alerts: string[]
  monthly_trend: { month: string; win_rate: number; total_bids: number; total_wins: number }[]
}

function MetricCard({
  label, value, subtitle, status,
}: { label: string; value: string; subtitle?: string; status?: 'good' | 'warn' | 'bad' | 'neutral' }) {
  const statusCls = {
    good:    'border-green-200 bg-green-50',
    warn:    'border-yellow-200 bg-yellow-50',
    bad:     'border-red-200 bg-red-50',
    neutral: 'border-gray-200 bg-white',
  }[status || 'neutral']

  return (
    <div className={`rounded-xl border p-4 ${statusCls}`}>
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-gray-900">{value}</div>
      {subtitle && <div className="text-xs text-gray-500 mt-0.5">{subtitle}</div>}
    </div>
  )
}

function ProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const color = pct >= 100 ? 'bg-green-500' : pct >= 60 ? 'bg-blue-500' : pct >= 30 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span className="font-medium">{value} / {max} ({pct.toFixed(0)}%)</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-3">
        <div className={`h-3 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function RecordOutcomeForm() {
  const [form, setForm] = useState({
    bid_id: '',
    submitted_rate: '',
    result: 'WON' as 'WON' | 'LOST' | 'DISQUALIFIED',
    actual_srate: '',
    winner_rate: '',
    our_rank: '',
    total_bidders: '',
  })
  const [done, setDone] = useState(false)

  const mut = useMutation({
    mutationFn: () => outcomesApi.record({
      bid_id:         parseInt(form.bid_id),
      submitted_rate: parseFloat(form.submitted_rate),
      result:         form.result,
      actual_srate:   form.actual_srate ? parseFloat(form.actual_srate) : undefined,
      winner_rate:    form.winner_rate ? parseFloat(form.winner_rate) : undefined,
      our_rank:       form.our_rank ? parseInt(form.our_rank) : undefined,
      total_bidders:  form.total_bidders ? parseInt(form.total_bidders) : undefined,
    }),
    onSuccess: () => {
      setDone(true)
      setForm({ bid_id: '', submitted_rate: '', result: 'WON', actual_srate: '', winner_rate: '', our_rank: '', total_bidders: '' })
      setTimeout(() => setDone(false), 2500)
    },
  })

  const set = (f: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [f]: e.target.value }))

  return (
    <div className="bg-white rounded-xl border p-5 space-y-4">
      <h3 className="font-semibold text-gray-700">투찰 결과 기록 (피드백 루프)</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">공고 ID *</label>
          <input type="number" value={form.bid_id} onChange={set('bid_id')}
            className="w-full border rounded-lg px-2 py-1.5 text-sm" placeholder="공고 ID" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">우리 투찰률 *</label>
          <input type="number" value={form.submitted_rate} onChange={set('submitted_rate')}
            step="0.0001" className="w-full border rounded-lg px-2 py-1.5 text-sm" placeholder="0.8720" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">결과 *</label>
          <select value={form.result} onChange={set('result')}
            className="w-full border rounded-lg px-2 py-1.5 text-sm">
            <option value="WON">낙찰 (WON)</option>
            <option value="LOST">패찰 (LOST)</option>
            <option value="DISQUALIFIED">적격탈락</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">실제 사정율</label>
          <input type="number" value={form.actual_srate} onChange={set('actual_srate')}
            step="0.0001" className="w-full border rounded-lg px-2 py-1.5 text-sm" placeholder="0.8850" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">낙찰자 투찰률</label>
          <input type="number" value={form.winner_rate} onChange={set('winner_rate')}
            step="0.0001" className="w-full border rounded-lg px-2 py-1.5 text-sm" placeholder="0.8715" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">우리 순위</label>
          <input type="number" value={form.our_rank} onChange={set('our_rank')}
            className="w-full border rounded-lg px-2 py-1.5 text-sm" placeholder="2" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">전체 참여자</label>
          <input type="number" value={form.total_bidders} onChange={set('total_bidders')}
            className="w-full border rounded-lg px-2 py-1.5 text-sm" placeholder="8" />
        </div>
        <div className="flex items-end">
          <button onClick={() => mut.mutate()} disabled={!form.bid_id || !form.submitted_rate || mut.isPending}
            className="w-full px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50">
            {done ? '✓ 기록 완료' : mut.isPending ? '저장 중...' : '결과 기록'}
          </button>
        </div>
      </div>
      {mut.isError && <p className="text-xs text-red-500">오류: {String(mut.error)}</p>}
    </div>
  )
}

export default function KPIDashboardPage() {
  const [period, setPeriod] = useState<'MONTHLY' | 'WEEKLY' | 'DAILY'>('MONTHLY')

  const { data, isLoading, refetch } = useQuery<KPIData>({
    queryKey: ['kpi-dashboard', period],
    queryFn: () => kpiApi.dashboard(period),
    refetchInterval: 60_000,
  })

  const winRateStatus = data
    ? data.win_rate >= 0.35 ? 'good' : data.win_rate >= 0.20 ? 'warn' : 'bad'
    : 'neutral'

  const maeStatus = data?.srate_mae != null
    ? data.srate_mae <= 0.003 ? 'good' : data.srate_mae <= 0.005 ? 'warn' : 'bad'
    : 'neutral'

  const eceStatus = data?.win_prob_calibration != null
    ? data.win_prob_calibration <= 0.05 ? 'good' : data.win_prob_calibration <= 0.10 ? 'warn' : 'bad'
    : 'neutral'

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">수주율 KPI 대시보드</h1>
          <p className="text-sm text-gray-500 mt-1">
            {data?.snapshot_date || '—'} 기준 | 목표함수: Maximize(수주건수, 수주금액, 이익, 적격통과율)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={period} onChange={(e) => setPeriod(e.target.value as 'MONTHLY' | 'WEEKLY' | 'DAILY')}
            className="text-sm border rounded-lg px-3 py-2">
            <option value="MONTHLY">이번 달</option>
            <option value="WEEKLY">이번 주</option>
            <option value="DAILY">오늘</option>
          </select>
          <button onClick={() => refetch()} className="px-3 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200">
            새로고침
          </button>
        </div>
      </div>

      {/* 경고 */}
      {data?.alerts && data.alerts.length > 0 && (
        <div className="space-y-2">
          {data.alerts.map((a, i) => (
            <div key={i} className="flex items-start gap-2 bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-sm text-orange-800">
              <span className="mt-0.5">⚠️</span>
              <span>{a}</span>
            </div>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="text-center text-gray-400 py-16">KPI 데이터 로딩 중...</div>
      ) : data ? (
        <>
          {/* 목표 달성 진행 */}
          <div className="bg-white rounded-xl border p-5 space-y-3">
            <h2 className="font-semibold text-gray-700">월 수주 목표 달성 현황</h2>
            <ProgressBar value={data.total_wins} max={data.monthly_target} label="수주건수" />
            <div className="text-xs text-gray-400">
              달성률 {(data.target_achievement * 100).toFixed(0)}%
              {data.target_achievement >= 1 && ' — 🎉 목표 달성!'}
              {data.target_achievement < 0.5 && data.monthly_target > 0 && ' — 공격적 투찰 전략 적용 중'}
            </div>
          </div>

          {/* 핵심 KPI */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard label="수주율" value={`${(data.win_rate * 100).toFixed(1)}%`}
              subtitle={`${data.total_wins}/${data.total_bids}건`} status={winRateStatus} />
            <MetricCard label="적격심사 통과율"
              value={data.qualify_pass_rate != null ? `${(data.qualify_pass_rate * 100).toFixed(1)}%` : '—'}
              status={data.qualify_pass_rate != null ? (data.qualify_pass_rate >= 0.95 ? 'good' : 'warn') : 'neutral'} />
            <MetricCard label="패찰 시 평균 순위"
              value={data.avg_rank_at_loss != null ? `${data.avg_rank_at_loss.toFixed(1)}위` : '—'}
              subtitle="낮을수록 아깝게 진 것"
              status={data.avg_rank_at_loss != null ? (data.avg_rank_at_loss <= 2 ? 'good' : data.avg_rank_at_loss <= 4 ? 'warn' : 'bad') : 'neutral'} />
            <MetricCard label="NO-GO 절감 건수" value={`${data.no_go_saved}건`}
              subtitle="이길 수 없는 공고 제외" status="neutral" />
          </div>

          {/* 모델 품질 */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <MetricCard label="사정율 예측 MAE"
              value={data.srate_mae != null ? data.srate_mae.toFixed(4) : '—'}
              subtitle="낮을수록 정확 (목표 ≤0.003)" status={maeStatus} />
            <MetricCard label="낙찰확률 캘리브레이션 ECE"
              value={data.win_prob_calibration != null ? data.win_prob_calibration.toFixed(3) : '—'}
              subtitle="낮을수록 신뢰 (목표 ≤0.05)" status={eceStatus} />
            <MetricCard label="GO 판정 비율"
              value={data.go_rate != null ? `${(data.go_rate * 100).toFixed(0)}%` : '—'}
              subtitle="GO 공고 중 낙찰 비율" status="neutral" />
          </div>

          {/* 월별 트렌드 */}
          {data.monthly_trend.length > 0 && (
            <div className="bg-white rounded-xl border p-5">
              <h2 className="font-semibold text-gray-700 mb-4">월별 수주율 추이</h2>
              <div className="flex items-end gap-2 h-32">
                {data.monthly_trend.map((m) => {
                  const h = Math.max(4, Math.round(m.win_rate * 100))
                  return (
                    <div key={m.month} className="flex-1 flex flex-col items-center gap-1">
                      <div className="text-xs text-gray-500">{(m.win_rate * 100).toFixed(0)}%</div>
                      <div className="w-full bg-blue-500 rounded-t" style={{ height: `${h}%` }} title={`${m.total_wins}/${m.total_bids}건`} />
                      <div className="text-xs text-gray-400 rotate-0">{m.month.slice(5)}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center text-gray-400 py-16 bg-gray-50 rounded-xl border">
          아직 투찰 결과 데이터가 없습니다. 아래에서 투찰 결과를 기록해보세요.
        </div>
      )}

      {/* 결과 기록 폼 */}
      <RecordOutcomeForm />
    </div>
  )
}
