import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FlaskConical, TrendingUp, TrendingDown, Trophy, XCircle,
  Loader2, AlertTriangle, CheckCircle2, ChevronRight,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell, LineChart, Line, Legend,
} from 'recharts'
import { backtestApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const PERIOD_OPTIONS = [
  { label: '6개월', value: 6 },
  { label: '1년', value: 12 },
  { label: '2년', value: 24 },
  { label: '5년', value: 60 },
]

const CAUSE_COLORS: Record<string, string> = {
  '투찰률과도':       '#ef4444',
  '투찰률과도(미세)': '#f97316',
  '경쟁과다':         '#eab308',
  '기타':             '#94a3b8',
}

export default function BacktestPage() {
  const [months, setMonths] = useState(60)

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['backtest', months],
    queryFn: () => backtestApi.run(months),
    staleTime: 120_000,
  })

  const hasData = data && data.total_bids > 0
  const loading = isLoading || isFetching

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-5xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-6 w-6 text-purple-600" />
          <div>
            <h1 className="text-xl font-bold">백테스트 엔진</h1>
            <p className="text-xs text-muted-foreground">과거 투찰 이력 vs 시스템 추천 — 수주율 개선 시뮬레이션</p>
          </div>
        </div>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((p) => (
            <button
              key={p.value}
              onClick={() => setMonths(p.value)}
              className={cn(
                'px-3 py-1.5 text-xs rounded-md font-medium border transition-colors',
                months === p.value
                  ? 'bg-purple-600 text-white border-purple-600'
                  : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50',
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && data && !hasData && (
        <div className="text-center py-16 text-muted-foreground rounded-xl border bg-white">
          <FlaskConical className="h-14 w-14 mx-auto mb-3 opacity-30" />
          <div className="font-medium">백테스트 데이터가 없습니다</div>
          <div className="text-sm mt-1 max-w-sm mx-auto">
            {data.message ?? '투찰 실행 관리에 결과(낙찰/패찰)를 입력하거나 SUCVIEW 파일을 업로드해주세요.'}
          </div>
        </div>
      )}

      {!loading && hasData && (
        <>
          {/* KPI 카드 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Card className="p-4 text-center">
              <div className="text-3xl font-bold text-gray-800">{data.total_bids}</div>
              <div className="text-xs text-muted-foreground mt-1">분석 건수</div>
            </Card>
            <Card className="p-4 text-center">
              <div className="text-3xl font-bold text-blue-600">{data.actual_win_rate}%</div>
              <div className="text-xs text-muted-foreground mt-1">실제 수주율</div>
              <div className="text-xs text-gray-500">{data.actual_wins}건 낙찰</div>
            </Card>
            <Card className="p-4 text-center border-purple-200 bg-purple-50">
              <div className="text-3xl font-bold text-purple-600">{data.simulated_win_rate}%</div>
              <div className="text-xs text-muted-foreground mt-1">시스템 추천시 수주율</div>
              <div className="text-xs text-gray-500">{data.simulated_wins}건 예상</div>
            </Card>
            <Card className={cn(
              'p-4 text-center',
              data.improvement_pct > 0 ? 'border-green-200 bg-green-50' : 'border-red-100 bg-red-50',
            )}>
              <div className={cn(
                'text-3xl font-bold',
                data.improvement_pct > 0 ? 'text-green-600' : 'text-red-500',
              )}>
                {data.improvement_pct > 0 ? '+' : ''}{data.improvement_pct}%p
              </div>
              <div className="text-xs text-muted-foreground mt-1">예상 수주율 개선</div>
              {data.improvement_pct > 0 ? (
                <div className="flex items-center justify-center gap-0.5 text-xs text-green-600 mt-0.5">
                  <TrendingUp className="h-3 w-3" /> 개선 예상
                </div>
              ) : (
                <div className="flex items-center justify-center gap-0.5 text-xs text-red-500 mt-0.5">
                  <TrendingDown className="h-3 w-3" /> 조정 필요
                </div>
              )}
            </Card>
          </div>

          {/* 월별 추이 차트 */}
          {data.monthly_trend.length > 1 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">월별 투찰/수주 추이</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.monthly_trend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                    <Tooltip
                      contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 12 }}
                      formatter={(v: number, name: string) =>
                        [v + (name === 'actual_rate' ? '%' : '건'), name === 'total' ? '참여' : name === 'actual_win' ? '낙찰' : '수주율']}
                    />
                    <Bar dataKey="total" fill="#dbeafe" radius={[3, 3, 0, 0]} name="total" />
                    <Bar dataKey="actual_win" fill="#2563eb" radius={[3, 3, 0, 0]} name="actual_win" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* 패찰 원인 분포 */}
          {data.cause_distribution.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">패찰 원인 분포</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {data.cause_distribution.map((c) => {
                    const total = data.cause_distribution.reduce((s, x) => s + x.count, 0)
                    const pct = total > 0 ? Math.round((c.count / total) * 100) : 0
                    const color = CAUSE_COLORS[c.cause] ?? '#94a3b8'
                    return (
                      <div key={c.cause} className="flex items-center gap-3">
                        <div className="w-24 text-xs text-gray-600 shrink-0 text-right">{c.cause}</div>
                        <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{ width: `${pct}%`, backgroundColor: color }}
                          />
                        </div>
                        <div className="w-16 text-xs text-gray-600 shrink-0">{c.count}건 ({pct}%)</div>
                      </div>
                    )
                  })}
                </div>
                {data.cause_distribution[0]?.cause.includes('투찰률') && (
                  <div className="mt-3 p-3 rounded-md bg-red-50 border border-red-100 text-xs text-red-600">
                    <AlertTriangle className="h-3.5 w-3.5 inline mr-1" />
                    투찰률 과도가 주요 패찰 원인입니다. 시스템 추천율을 적극 활용하세요.
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* 개선 사례 (추천 따랐으면 낙찰됐을 건) */}
          {data.sample_improvements.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                  추천율 적용시 낙찰 가능 사례 (상위 {data.sample_improvements.length}건)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {data.sample_improvements.map((s, i) => (
                    <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg bg-green-50 border border-green-100 text-xs">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium truncate">{s.title}</div>
                        <div className="text-muted-foreground">{s.agency}</div>
                      </div>
                      <div className="shrink-0 text-right space-y-0.5">
                        <div className="text-red-500">실제 {s.actual_rate}%</div>
                        <div className="text-green-600 font-medium">추천 {s.recommended_rate}%</div>
                        <div className="text-gray-400">낙찰 {s.winner_rate}%</div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
