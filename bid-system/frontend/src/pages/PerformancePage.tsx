import { useQuery } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Target, Trophy, ShieldCheck, BarChart2, ClipboardList,
  CheckCircle2, XCircle, Clock, AlertTriangle, Activity,
} from 'lucide-react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { kpiApi, myBidsApi, statsApi } from '@/api'
import type { MyBidRecord, DefeatAnalysis, WinPattern, OverviewStatsWithChange } from '@/types'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

interface KPIData {
  period_type:         string
  snapshot_date:       string
  total_bids:          number
  total_wins:          number
  win_rate:            number
  monthly_target?:     number
  target_achievement?: number
  qualify_pass_rate?:  number
  avg_rank_at_loss?:   number
  srate_mae?:          number
  win_prob_calibration?: number
  go_rate?:            number
  no_go_saved:         number
  alerts:              string[]
  monthly_trend:       { month: string; win_rate: number; total_bids: number; total_wins: number }[]
}

// 색상 맵 정의
const statusColorMap = {
  good:    { bar: 'bg-emerald-500', icon: 'bg-emerald-50', iconText: 'text-emerald-600', border: 'border-emerald-200', bg: 'bg-emerald-50/60', value: 'text-emerald-700' },
  warn:    { bar: 'bg-amber-400',   icon: 'bg-amber-50',   iconText: 'text-amber-600',   border: 'border-amber-200',   bg: 'bg-amber-50/60',   value: 'text-amber-700' },
  bad:     { bar: 'bg-red-500',     icon: 'bg-red-50',     iconText: 'text-red-600',     border: 'border-red-200',     bg: 'bg-red-50/60',     value: 'text-red-700' },
  neutral: { bar: 'bg-blue-500',    icon: 'bg-slate-100',  iconText: 'text-slate-500',   border: 'border-slate-200',   bg: 'bg-white',         value: 'text-slate-900' },
}

function KpiCard({
  label, value, sub, status, icon: Icon,
}: {
  label: string
  value: string
  sub?: string
  status?: 'good' | 'warn' | 'bad' | 'neutral'
  icon?: React.ComponentType<{ className?: string }>
}) {
  const s = statusColorMap[status ?? 'neutral']

  return (
    <Card className={cn('relative overflow-hidden bg-white border shadow-sm hover:shadow-md transition-shadow', s.border)}>
      <div className={cn('absolute top-0 left-0 right-0 h-0.5', s.bar)} />
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className={cn('text-2xl font-bold mt-1 tabular-nums', s.value)}>{value}</p>
            {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
          </div>
          {Icon && (
            <div className={cn('rounded-xl p-2.5 shrink-0 ml-3', s.icon)}>
              <Icon className={cn('h-5 w-5', s.iconText)} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function ResultBadge({ result }: { result: string }) {
  if (result === 'won')
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
        <CheckCircle2 className="h-3 w-3" />낙찰
      </span>
    )
  if (result === 'lost')
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-600 border border-red-200 font-semibold">
        <XCircle className="h-3 w-3" />미낙찰
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-50 text-slate-500 border border-slate-200">
      <Clock className="h-3 w-3" />대기중
    </span>
  )
}

// ── KPI 대시보드 탭 ─────────────────────────────────────────────
function TabKPI() {
  const { data: kpi, isLoading: kpiLoading } = useQuery<KPIData>({
    queryKey: ['kpi-dashboard', 'MONTHLY'],
    queryFn: () => kpiApi.dashboard('MONTHLY'),
    staleTime: 60_000,
  })

  const { data: overview } = useQuery<OverviewStatsWithChange>({
    queryKey: ['stats-overview', 3],
    queryFn: () => statsApi.overview(3),
    staleTime: 300_000,
  })

  if (kpiLoading) return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)}
      </div>
      <Skeleton className="h-52 w-full rounded-xl" />
    </div>
  )

  const winRateStatus = kpi?.win_rate == null ? 'neutral'
    : kpi.win_rate >= 0.3 ? 'good' : kpi.win_rate >= 0.2 ? 'warn' : 'bad'

  const qualifyStatus = kpi?.qualify_pass_rate == null ? 'neutral'
    : kpi.qualify_pass_rate >= 0.95 ? 'good' : kpi.qualify_pass_rate >= 0.85 ? 'warn' : 'bad'

  return (
    <div className="space-y-4">
      {/* KPI 카드 4개 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          label="이번 달 수주율"
          value={kpi?.win_rate != null ? `${(kpi.win_rate * 100).toFixed(1)}%` : '-'}
          sub={kpi?.total_bids != null ? `투찰 ${kpi.total_bids}건 중 ${kpi.total_wins ?? 0}건 낙찰` : undefined}
          status={winRateStatus}
          icon={Trophy}
        />
        <KpiCard
          label="적격심사 통과율"
          value={kpi?.qualify_pass_rate != null ? `${(kpi.qualify_pass_rate * 100).toFixed(1)}%` : '-'}
          sub="탈락 방지율"
          status={qualifyStatus}
          icon={ShieldCheck}
        />
        <KpiCard
          label="NO_GO 절감"
          value={kpi?.no_go_saved != null ? `${kpi.no_go_saved}건` : '-'}
          sub="AI 선별로 불필요한 투찰 방지"
          status="neutral"
          icon={Target}
        />
        <KpiCard
          label="패찰 시 평균 순위"
          value={kpi?.avg_rank_at_loss != null ? `${kpi.avg_rank_at_loss.toFixed(1)}위` : '-'}
          sub="낮을수록 아깝게 놓침"
          status={kpi?.avg_rank_at_loss != null ? (kpi.avg_rank_at_loss <= 3 ? 'warn' : 'neutral') : 'neutral'}
          icon={BarChart2}
        />
      </div>

      {/* 이상 알림 */}
      {kpi?.alerts && kpi.alerts.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/60 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-amber-800 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" /> AI 성능 경고
            </CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-4 space-y-1.5">
            {kpi.alerts.map((a, i) => (
              <p key={i} className="text-sm text-amber-700 flex items-start gap-1.5">
                <span className="shrink-0 mt-0.5">•</span>{a}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      {/* 월별 수주율 트렌드 */}
      {kpi?.monthly_trend && kpi.monthly_trend.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <div className="rounded-lg p-1.5 bg-blue-50">
                <TrendingUp className="h-4 w-4 text-blue-600" />
              </div>
              월별 수주율 추이
            </CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={kpi.monthly_trend} margin={{ left: -20, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#475569' }} />
                <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 12, fill: '#475569' }} />
                <Tooltip
                  contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                  formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, '수주율']}
                />
                <ReferenceLine
                  y={0.25}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: '목표 25%', fontSize: 10, fill: '#f59e0b' }}
                />
                <Line type="monotone" dataKey="win_rate" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 3, fill: '#2563eb' }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* 월별 투찰건수 */}
      {kpi?.monthly_trend && kpi.monthly_trend.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800">월별 투찰 / 낙찰 건수</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={kpi.monthly_trend} margin={{ left: -20, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#475569' }} />
                <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                <Tooltip contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }} />
                <Bar dataKey="total_bids" name="투찰" fill="#bfdbfe" radius={[3, 3, 0, 0]} />
                <Bar dataKey="total_wins" name="낙찰" fill="#2563eb" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* AI 모델 정확도 */}
      {(kpi?.srate_mae != null || kpi?.win_prob_calibration != null) && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <div className="rounded-lg p-1.5 bg-purple-50">
                <Activity className="h-4 w-4 text-purple-600" />
              </div>
              AI 모델 성능
            </CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
                <p className="text-sm font-medium text-slate-500">사정율 예측 MAE</p>
                <p className={cn('text-2xl font-bold mt-1 tabular-nums',
                  (kpi?.srate_mae ?? 0) <= 0.003 ? 'text-emerald-600'
                  : (kpi?.srate_mae ?? 0) <= 0.005 ? 'text-amber-600' : 'text-red-500')}>
                  {kpi?.srate_mae != null ? (kpi.srate_mae * 100).toFixed(3) + '%' : '-'}
                </p>
                <p className="text-xs text-slate-500 mt-1">목표 0.500% 이하</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
                <p className="text-sm font-medium text-slate-500">낙찰확률 캘리브레이션 오차(ECE)</p>
                <p className={cn('text-2xl font-bold mt-1 tabular-nums',
                  (kpi?.win_prob_calibration ?? 0) <= 0.05 ? 'text-emerald-600'
                  : (kpi?.win_prob_calibration ?? 0) <= 0.10 ? 'text-amber-600' : 'text-red-500')}>
                  {kpi?.win_prob_calibration != null ? kpi.win_prob_calibration.toFixed(3) : '-'}
                </p>
                <p className="text-xs text-slate-500 mt-1">목표 0.10 이하</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 3개월 시장 개요 */}
      {overview && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800">최근 3개월 시장 현황</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: '총 공고', value: overview.total_bids?.toLocaleString() ?? '-', sub: '건' },
                { label: '평균 수주율', value: overview.avg_win_rate != null ? `${(overview.avg_win_rate * 100).toFixed(1)}%` : '-', sub: '' },
                { label: '평균 경쟁강도', value: overview.avg_competitor_count?.toFixed(1) ?? '-', sub: '개사' },
              ].map((item) => (
                <div key={item.label} className="text-center bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <p className="text-xs text-slate-500 font-medium">{item.label}</p>
                  <p className="text-2xl font-bold mt-1 text-slate-900 tabular-nums">
                    {item.value}<span className="text-xs font-normal text-slate-500 ml-0.5">{item.sub}</span>
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── 투찰 이력 탭 ────────────────────────────────────────────────
function TabHistory({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  const { data: statsData } = useQuery({
    queryKey: ['my-bids-stats'],
    queryFn: myBidsApi.stats,
    staleTime: 60_000,
  })

  const { data: listData, isLoading } = useQuery<{ items: MyBidRecord[]; total: number }>({
    queryKey: ['my-bids', undefined, 1, 20],
    queryFn: () => myBidsApi.list({ page: 1, size: 20 }),
    staleTime: 60_000,
  })

  const stats = statsData as { total?: number; won?: number; lost?: number; pending?: number; win_rate?: number; avg_submitted_rate?: number } | null

  return (
    <div className="space-y-4">
      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="전체 투찰" value={stats?.total?.toString() ?? '-'} sub="건" icon={ClipboardList} />
        <KpiCard label="낙찰" value={stats?.won?.toString() ?? '-'} sub="건" status={stats?.won ? 'good' : 'neutral'} icon={Trophy} />
        <KpiCard
          label="수주율"
          value={stats?.win_rate != null ? `${(stats.win_rate * 100).toFixed(1)}%` : '-'}
          status={stats?.win_rate != null ? (stats.win_rate >= 0.25 ? 'good' : stats.win_rate >= 0.15 ? 'warn' : 'bad') : 'neutral'}
          icon={TrendingUp}
        />
        <KpiCard
          label="평균 투찰률"
          value={stats?.avg_submitted_rate != null ? `${(stats.avg_submitted_rate * 100).toFixed(3)}%` : '-'}
          icon={Target}
        />
      </div>

      {/* 자세히 보기 링크 */}
      <div className="flex justify-end">
        <Button variant="outline" size="sm" className="border-slate-200 text-slate-600" onClick={() => navigate('/my-bids')}>
          전체 투찰 이력 보기
        </Button>
      </div>

      {/* 최근 20건 */}
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="pb-2 pt-4 px-5">
          <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-slate-500" />
            최근 투찰 이력
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50">
                <TableHead className="text-sm text-slate-500">공고명</TableHead>
                <TableHead className="text-sm text-slate-500">발주기관</TableHead>
                <TableHead className="text-sm text-slate-500">투찰일</TableHead>
                <TableHead className="text-right text-sm text-slate-500">기초금액</TableHead>
                <TableHead className="text-right text-sm text-slate-500">투찰률</TableHead>
                <TableHead className="text-center text-sm text-slate-500">결과</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full rounded" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : !(listData?.items?.length) ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-slate-500 py-10">
                    투찰 이력이 없습니다.
                  </TableCell>
                </TableRow>
              ) : (
                listData.items.map((rec) => (
                  <TableRow
                    key={rec.id}
                    className={cn(
                      'cursor-pointer transition-colors',
                      rec.result === 'won' ? 'bg-emerald-50/30 hover:bg-emerald-50/60' : 'hover:bg-slate-50'
                    )}
                    onClick={() => rec.bid_id ? navigate(`/bids/${rec.bid_id}`) : undefined}
                  >
                    <TableCell className="max-w-xs">
                      <p className="truncate font-semibold text-slate-800">{rec.title}</p>
                      {rec.announcement_no && (
                        <p className="text-xs text-slate-500 font-mono">{rec.announcement_no}</p>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm text-slate-500">
                      {rec.agency_name ?? '-'}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm text-slate-500">
                      {rec.bid_date ? new Date(rec.bid_date).toLocaleDateString('ko-KR') : '-'}
                    </TableCell>
                    <TableCell className="text-right text-sm text-slate-600 tabular-nums">
                      {rec.base_amount > 0 ? (rec.base_amount / 1e8).toFixed(1) + '억' : '-'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm text-slate-700 tabular-nums">
                      {(rec.submitted_rate * 100).toFixed(3)}%
                    </TableCell>
                    <TableCell className="text-center">
                      <ResultBadge result={rec.result} />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

// ── 패찰 분석 탭 ────────────────────────────────────────────────
function TabDefeat({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  const { data: defeat, isLoading } = useQuery<DefeatAnalysis>({
    queryKey: ['defeat-analysis'],
    queryFn: myBidsApi.defeatAnalysis,
    staleTime: 300_000,
  })

  const { data: winPattern } = useQuery<WinPattern>({
    queryKey: ['win-pattern'],
    queryFn: myBidsApi.winPattern,
    staleTime: 300_000,
  })

  if (isLoading) return (
    <div className="space-y-4">
      {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32 w-full rounded-xl" />)}
    </div>
  )

  if (!defeat || defeat.total_analyzed === 0) return (
    <div className="text-center py-16 space-y-3">
      <p className="text-slate-500">분석할 패찰 데이터가 없습니다.</p>
      <Button size="sm" onClick={() => navigate('/my-bids')} className="bg-slate-800 hover:bg-slate-900">
        투찰 이력 등록하기
      </Button>
    </div>
  )

  const { miss_stats, distribution, agency_breakdown, trend } = defeat
  const wp = winPattern

  const dirLabel = miss_stats?.direction === 'too_high' ? '낙찰가 위로 이탈 (투찰률이 높음)'
    : miss_stats?.direction === 'too_low' ? '낙찰가 아래 이탈 (투찰률이 낮음)'
    : '이탈 방향 혼재'

  const dirStatus: 'warn' | 'neutral' = miss_stats?.direction !== 'balanced' ? 'warn' : 'neutral'

  return (
    <div className="space-y-4">
      {/* 패찰 개요 */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <KpiCard
          label="평균 이탈폭"
          value={miss_stats?.avg_diff_pct != null ? `${Math.abs(miss_stats.avg_diff_pct).toFixed(3)}%` : '-'}
          sub={dirLabel}
          status={dirStatus}
          icon={TrendingDown}
        />
        <KpiCard
          label="1% 이내 아깝게 패찰"
          value={miss_stats?.within_1pct != null ? `${miss_stats.within_1pct}건` : '-'}
          sub="투찰률 조정으로 낙찰 가능"
          status={miss_stats?.within_1pct ? 'warn' : 'neutral'}
          icon={Target}
        />
        <KpiCard
          label="분석 건수"
          value={defeat.total_analyzed?.toString() ?? '-'}
          sub="건 (패찰 결과 확인 건)"
          icon={ClipboardList}
        />
      </div>

      {/* 이탈 분포 히스토그램 */}
      {distribution && distribution.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800">패찰 이탈 분포</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={distribution.map(d => ({ ...d, label: `${d.from}~${d.to}%` }))} margin={{ left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569' }} />
                <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                <Tooltip
                  contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                  formatter={(v: number) => [v + '건', '건수']}
                />
                <Bar dataKey="count" fill="#93c5fd" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-slate-500 mt-1.5">음수: 낙찰가 아래 이탈 / 양수: 낙찰가 위 이탈</p>
          </CardContent>
        </Card>
      )}

      {/* 월별 패찰 추이 */}
      {trend && trend.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800">월별 패찰 추이</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trend} margin={{ left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="year_month" tick={{ fontSize: 12, fill: '#475569' }} />
                <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                <Tooltip contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }} />
                <Line type="monotone" dataKey="count" name="패찰건수" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 3, fill: '#ef4444' }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* 발주기관별 패찰 */}
      {agency_breakdown && agency_breakdown.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800">발주기관별 패찰 현황</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="text-sm text-slate-500">발주기관</TableHead>
                  <TableHead className="text-center text-sm text-slate-500">패찰건</TableHead>
                  <TableHead className="text-right text-sm text-slate-500">평균 이탈</TableHead>
                  <TableHead className="text-right text-sm text-slate-500">이탈 방향</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {agency_breakdown.slice(0, 10).map((a) => (
                  <TableRow key={a.agency_name} className="hover:bg-slate-50 transition-colors">
                    <TableCell className="font-semibold text-sm text-slate-800">{a.agency_name}</TableCell>
                    <TableCell className="text-center text-sm text-slate-600 tabular-nums">{a.count}건</TableCell>
                    <TableCell className="text-right font-mono text-sm text-slate-600 tabular-nums">
                      {a.avg_diff != null ? `${Math.abs(a.avg_diff).toFixed(3)}%` : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className={cn(
                        'inline-flex items-center text-xs px-2 py-0.5 rounded-full border font-medium',
                        a.direction === 'too_high' ? 'bg-red-50 text-red-600 border-red-200' :
                        a.direction === 'too_low' ? 'bg-blue-50 text-blue-600 border-blue-200' :
                        'bg-slate-50 text-slate-500 border-slate-200'
                      )}>
                        {a.direction === 'too_high' ? '투찰률 높음' :
                         a.direction === 'too_low' ? '투찰률 낮음' : '혼재'}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* 수주 패턴 바이어스 */}
      {wp?.bias && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800">자사 투찰 바이어스 분석</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 font-medium">투찰률 편향 방향</p>
                <p className={cn('text-lg font-bold mt-1',
                  wp.bias.direction === 'above' ? 'text-red-500' :
                  wp.bias.direction === 'below' ? 'text-blue-500' : 'text-emerald-600')}>
                  {wp.bias.direction === 'above' ? '상향 편향 (투찰률이 계속 높음)'
                    : wp.bias.direction === 'below' ? '하향 편향 (투찰률이 계속 낮음)'
                    : '균형 (편향 없음)'}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-slate-500 font-medium">평균 편차</p>
                <p className="text-2xl font-bold text-slate-900 tabular-nums">
                  {wp.bias.rate_diff_mean != null ? `${(wp.bias.rate_diff_mean * 100).toFixed(3)}%` : '-'}
                </p>
              </div>
            </div>
            <p className="text-sm text-slate-500 bg-slate-50 rounded-lg px-4 py-2.5 border border-slate-100">{wp.bias.signal}</p>

            {wp.overall_win_rate != null && (
              <div className="grid grid-cols-3 gap-3 pt-2 border-t border-slate-100">
                {[
                  { label: '전체 투찰', value: String(wp.total), color: 'text-slate-900' },
                  { label: '낙찰', value: String(wp.won), color: 'text-emerald-600' },
                  { label: '전체 수주율', value: `${(wp.overall_win_rate * 100).toFixed(1)}%`, color: 'text-blue-600' },
                ].map(item => (
                  <div key={item.label} className="text-center bg-slate-50 rounded-xl p-3 border border-slate-100">
                    <p className="text-xs text-slate-500 font-medium">{item.label}</p>
                    <p className={cn('text-2xl font-bold mt-0.5 tabular-nums', item.color)}>{item.value}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── 메인 ──────────────────────────────────────────────────────
export default function PerformancePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const defaultTab = searchParams.get('tab') ?? 'kpi'

  return (
    <div className="min-h-screen bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
            <BarChart2 className="h-5 w-5 text-blue-600" />
            성과센터
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">수주 현황 · 투찰 이력 · 패찰 분석</p>
        </div>
      </div>

      <div className="p-6">
        <Tabs defaultValue={defaultTab} className="space-y-5">
          <TabsList className="bg-slate-100 border border-slate-200">
            <TabsTrigger value="kpi" className="gap-1.5 text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm">
              <BarChart2 className="h-3.5 w-3.5" />KPI 대시보드
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-1.5 text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm">
              <ClipboardList className="h-3.5 w-3.5" />투찰 이력
            </TabsTrigger>
            <TabsTrigger value="defeat" className="gap-1.5 text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm">
              <TrendingDown className="h-3.5 w-3.5" />패찰 분석
            </TabsTrigger>
          </TabsList>

          <TabsContent value="kpi" className="mt-0">
            <TabKPI />
          </TabsContent>
          <TabsContent value="history" className="mt-0">
            <TabHistory navigate={navigate} />
          </TabsContent>
          <TabsContent value="defeat" className="mt-0">
            <TabDefeat navigate={navigate} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
