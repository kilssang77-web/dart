import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { BarChart2, Target, TrendingUp, Award, AlertTriangle, RefreshCw, Loader2, CheckCircle2, XCircle, Activity, Users, ChevronDown } from 'lucide-react'
import { kpiApi, outcomesApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

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

type StatusType = 'good' | 'warn' | 'bad' | 'neutral'

function KPICard({
  label, value, subtitle, status, icon: Icon, accent,
}: {
  label: string; value: string; subtitle?: string; status?: StatusType
  icon?: React.ElementType; accent?: string
}) {
  const configs: Record<StatusType, { bar: string; iconBg: string; iconColor: string; valueCls: string }> = {
    good:    { bar: 'bg-emerald-500', iconBg: 'bg-emerald-50', iconColor: 'text-emerald-600', valueCls: 'text-emerald-700' },
    warn:    { bar: 'bg-amber-500',   iconBg: 'bg-amber-50',   iconColor: 'text-amber-600',   valueCls: 'text-amber-700' },
    bad:     { bar: 'bg-red-500',     iconBg: 'bg-red-50',     iconColor: 'text-red-600',     valueCls: 'text-red-700' },
    neutral: { bar: 'bg-blue-500',    iconBg: 'bg-blue-50',    iconColor: 'text-blue-600',    valueCls: 'text-slate-900' },
  }
  const c = configs[status ?? 'neutral']

  return (
    <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
      <div className={cn('absolute top-0 left-0 right-0 h-0.5', c.bar)} />
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className={cn('text-2xl font-bold mt-1 tabular-nums', c.valueCls)}>{value}</p>
            {subtitle && <p className="text-xs text-slate-400 mt-1">{subtitle}</p>}
          </div>
          {Icon && (
            <div className={cn('rounded-xl p-2.5', c.iconBg)}>
              <Icon className={cn('h-5 w-5', c.iconColor)} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function ProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const colorClass = pct >= 100 ? 'bg-emerald-500' : pct >= 60 ? 'bg-blue-500' : pct >= 30 ? 'bg-amber-500' : 'bg-red-500'
  const textColor = pct >= 100 ? 'text-emerald-600' : pct >= 60 ? 'text-blue-600' : pct >= 30 ? 'text-amber-600' : 'text-red-600'
  return (
    <div>
      <div className="flex justify-between text-sm mb-2">
        <span className="font-medium text-slate-700">{label}</span>
        <span className={cn('font-semibold tabular-nums', textColor)}>{value} / {max}건 ({pct.toFixed(0)}%)</span>
      </div>
      <div className="w-full bg-slate-100 rounded-full h-2.5">
        <div className={cn('h-2.5 rounded-full transition-all duration-500', colorClass)} style={{ width: `${pct}%` }} />
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

  const resultOptions = [
    { value: 'WON', label: '낙찰 (WON)' },
    { value: 'LOST', label: '패찰 (LOST)' },
    { value: 'DISQUALIFIED', label: '적격탈락' },
  ]

  return (
    <Card className="bg-white border-slate-200 shadow-sm">
      <CardHeader className="border-b border-slate-100 pb-4">
        <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-600" />투찰 결과 기록
        </CardTitle>
        <CardDescription className="text-slate-500">피드백 루프 — 결과 기록으로 AI 모델 정확도를 향상시킵니다</CardDescription>
      </CardHeader>
      <CardContent className="p-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">공고 ID *</Label>
            <Input type="number" value={form.bid_id} onChange={set('bid_id')} placeholder="공고 ID" className="border-slate-200" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">우리 투찰률 *</Label>
            <Input type="number" value={form.submitted_rate} onChange={set('submitted_rate')} step="0.0001" placeholder="0.8720" className="border-slate-200" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">결과 *</Label>
            <select
              value={form.result}
              onChange={set('result')}
              className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {resultOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">실제 사정율</Label>
            <Input type="number" value={form.actual_srate} onChange={set('actual_srate')} step="0.0001" placeholder="0.8850" className="border-slate-200" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">낙찰자 투찰률</Label>
            <Input type="number" value={form.winner_rate} onChange={set('winner_rate')} step="0.0001" placeholder="0.8715" className="border-slate-200" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">우리 순위</Label>
            <Input type="number" value={form.our_rank} onChange={set('our_rank')} placeholder="2" className="border-slate-200" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-slate-600">전체 참여자</Label>
            <Input type="number" value={form.total_bidders} onChange={set('total_bidders')} placeholder="8" className="border-slate-200" />
          </div>
          <div className="flex items-end">
            <Button
              onClick={() => mut.mutate()}
              disabled={!form.bid_id || !form.submitted_rate || mut.isPending}
              className={cn('w-full gap-2', done ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 hover:bg-blue-700')}
            >
              {done ? (
                <><CheckCircle2 className="h-4 w-4" />기록 완료</>
              ) : mut.isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin" />저장 중...</>
              ) : '결과 기록'}
            </Button>
          </div>
        </div>
        {mut.isError && (
          <div className="mt-3 flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            <XCircle className="h-3.5 w-3.5 shrink-0" />오류: {String(mut.error)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function KPIDashboardPage() {
  const [period, setPeriod] = useState<'MONTHLY' | 'WEEKLY' | 'DAILY'>('MONTHLY')

  const { data, isLoading, refetch } = useQuery<KPIData>({
    queryKey: ['kpi-dashboard', period],
    queryFn: () => kpiApi.dashboard(period),
    refetchInterval: 60_000,
  })

  const winRateStatus: StatusType = data
    ? data.win_rate >= 0.35 ? 'good' : data.win_rate >= 0.20 ? 'warn' : 'bad'
    : 'neutral'

  const maeStatus: StatusType = data?.srate_mae != null
    ? data.srate_mae <= 0.003 ? 'good' : data.srate_mae <= 0.005 ? 'warn' : 'bad'
    : 'neutral'

  const eceStatus: StatusType = data?.win_prob_calibration != null
    ? data.win_prob_calibration <= 0.05 ? 'good' : data.win_prob_calibration <= 0.10 ? 'warn' : 'bad'
    : 'neutral'

  const periodLabel = period === 'MONTHLY' ? '이번 달' : period === 'WEEKLY' ? '이번 주' : '오늘'

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <BarChart2 className="h-5 w-5 text-blue-600" />수주율 KPI 대시보드
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {data?.snapshot_date || '—'} 기준 | 목표함수: Maximize(수주건수, 수주금액, 이익, 적격통과율)
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value as 'MONTHLY' | 'WEEKLY' | 'DAILY')}
              className="text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="MONTHLY">이번 달</option>
              <option value="WEEKLY">이번 주</option>
              <option value="DAILY">오늘</option>
            </select>
            <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-2 border-slate-200 text-slate-600 hover:bg-slate-50">
              <RefreshCw className="h-3.5 w-3.5" />새로고침
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-6 space-y-6">
        {/* 경고 알림 */}
        {data?.alerts && data.alerts.length > 0 && (
          <div className="space-y-2">
            {data.alerts.map((a, i) => (
              <div key={i} className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600" />
                <span>{a}</span>
              </div>
            ))}
          </div>
        )}

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-slate-400">
            <Loader2 className="h-8 w-8 animate-spin mb-3 text-blue-400" />
            <p className="text-sm">KPI 데이터 로딩 중...</p>
          </div>
        ) : data ? (
          <>
            {/* 목표 달성 진행 카드 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="border-b border-slate-100 pb-4">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                      <Target className="h-4 w-4 text-blue-600" />{periodLabel} 수주 목표 달성 현황
                    </CardTitle>
                    <CardDescription className="text-slate-500 mt-1">
                      달성률 <span className={cn('font-semibold', data.target_achievement >= 1 ? 'text-emerald-600' : data.target_achievement >= 0.5 ? 'text-blue-600' : 'text-amber-600')}>
                        {(data.target_achievement * 100).toFixed(0)}%
                      </span>
                      {data.target_achievement >= 1 && ' — 목표 달성!'}
                      {data.target_achievement < 0.5 && data.monthly_target > 0 && ' — 공격적 투찰 전략 적용 중'}
                    </CardDescription>
                  </div>
                  {data.target_achievement >= 1 && (
                    <Badge className="bg-emerald-50 text-emerald-700 border border-emerald-200 gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" />목표 달성
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="p-5">
                <ProgressBar value={data.total_wins} max={data.monthly_target} label="수주건수" />
              </CardContent>
            </Card>

            {/* 핵심 KPI 카드 */}
            <div>
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">핵심 성과 지표</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPICard
                  label="수주율"
                  value={`${(data.win_rate * 100).toFixed(1)}%`}
                  subtitle={`${data.total_wins}/${data.total_bids}건`}
                  status={winRateStatus}
                  icon={Award}
                />
                <KPICard
                  label="적격심사 통과율"
                  value={data.qualify_pass_rate != null ? `${(data.qualify_pass_rate * 100).toFixed(1)}%` : '—'}
                  status={data.qualify_pass_rate != null ? (data.qualify_pass_rate >= 0.95 ? 'good' : 'warn') : 'neutral'}
                  icon={CheckCircle2}
                />
                <KPICard
                  label="패찰 시 평균 순위"
                  value={data.avg_rank_at_loss != null ? `${data.avg_rank_at_loss.toFixed(1)}위` : '—'}
                  subtitle="낮을수록 아깝게 진 것"
                  status={data.avg_rank_at_loss != null ? (data.avg_rank_at_loss <= 2 ? 'good' : data.avg_rank_at_loss <= 4 ? 'warn' : 'bad') : 'neutral'}
                  icon={TrendingUp}
                />
                <KPICard
                  label="NO-GO 절감 건수"
                  value={`${data.no_go_saved}건`}
                  subtitle="이길 수 없는 공고 제외"
                  status="neutral"
                  icon={Users}
                />
              </div>
            </div>

            {/* 모델 품질 카드 */}
            <div>
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">모델 품질 지표</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <KPICard
                  label="사정율 예측 MAE"
                  value={data.srate_mae != null ? data.srate_mae.toFixed(4) : '—'}
                  subtitle="낮을수록 정확 (목표 ≤0.003)"
                  status={maeStatus}
                  icon={Activity}
                />
                <KPICard
                  label="낙찰확률 캘리브레이션 ECE"
                  value={data.win_prob_calibration != null ? data.win_prob_calibration.toFixed(3) : '—'}
                  subtitle="낮을수록 신뢰 (목표 ≤0.05)"
                  status={eceStatus}
                  icon={BarChart2}
                />
                <KPICard
                  label="GO 판정 비율"
                  value={data.go_rate != null ? `${(data.go_rate * 100).toFixed(0)}%` : '—'}
                  subtitle="GO 공고 중 낙찰 비율"
                  status="neutral"
                  icon={Target}
                />
              </div>
            </div>

            {/* 월별 트렌드 바 차트 */}
            {data.monthly_trend.length > 0 && (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardHeader className="border-b border-slate-100 pb-4">
                  <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-blue-600" />월별 수주율 추이
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5">
                  <div className="flex items-end gap-2 h-36">
                    {data.monthly_trend.map((m) => {
                      const h = Math.max(4, Math.round(m.win_rate * 100))
                      const isHigh = m.win_rate >= 0.35
                      return (
                        <div key={m.month} className="flex-1 flex flex-col items-center gap-1.5">
                          <div className={cn('text-xs font-medium tabular-nums', isHigh ? 'text-emerald-600' : 'text-slate-500')}>
                            {(m.win_rate * 100).toFixed(0)}%
                          </div>
                          <div
                            className={cn('w-full rounded-t-md transition-all', isHigh ? 'bg-emerald-500' : 'bg-blue-400')}
                            style={{ height: `${h}%` }}
                            title={`${m.total_wins}/${m.total_bids}건`}
                          />
                          <div className="text-xs text-slate-400">{m.month.slice(5)}</div>
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        ) : (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardContent className="py-20 text-center">
              <BarChart2 className="h-12 w-12 text-slate-200 mx-auto mb-4" />
              <p className="text-slate-500 font-medium">아직 투찰 결과 데이터가 없습니다.</p>
              <p className="text-slate-400 text-sm mt-1">아래에서 투찰 결과를 기록해보세요.</p>
            </CardContent>
          </Card>
        )}

        {/* 결과 기록 폼 */}
        <RecordOutcomeForm />
      </div>
    </div>
  )
}
