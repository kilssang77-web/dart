import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { TrendingUp, Info, Trophy, AlertTriangle, ChevronDown, ChevronUp, Building2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { recommendApi, agenciesApi } from '@/api'
import type { YegaFrequencyResult, AgencyYegaPattern } from '@/types'

/*
 * 예가 빈도 분석 (복수예가 Prism형)
 * A값 ±2% 범위의 15개 예비가격 후보에서 C(15,4)=1,365가지 조합을 모두 계산,
 * 평균(예정가격)이 집중되는 구간을 시각화.
 */

function fmtWon(v: number) {
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '억원'
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '만원'
  return v.toLocaleString() + '원'
}
function parseWon(s: string) { return Number(s.replace(/,/g, '')) }

const FLOOR = 0.87745

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) return <span className="text-amber-500 font-bold text-base">1</span>
  if (rank === 2) return <span className="text-slate-500 font-bold text-sm">2</span>
  if (rank === 3) return <span className="text-amber-600 font-bold text-sm">3</span>
  return <span className="text-slate-500 text-sm font-mono">{rank}</span>
}

function ResultPanel({ result, baseAmount }: { result: YegaFrequencyResult; baseAmount: number }) {
  const [showAllCandidates, setShowAllCandidates] = useState(false)
  const [showFullTable, setShowFullTable] = useState(false)

  const top1 = result.top10[0]
  const top3 = result.top10.slice(0, 3)

  // 차트 데이터: top3 구간 강조
  const top3Rates = new Set(top3.map(r => r.rate_pct))
  const chartData = result.chart_bins.map(b => ({
    ...b,
    isTop: top3Rates.has(b.rate_pct),
  }))

  const tableRows = showFullTable ? result.frequency : result.top10

  return (
    <div className="space-y-5">
      {/* 핵심 결과 요약 — 3종 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 최빈 구간 */}
        <div className="relative overflow-hidden rounded-xl border-2 border-blue-300 bg-blue-50/30 ring-2 ring-blue-500 ring-offset-1">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-600" />
          <div className="p-4">
            <p className="text-xs text-slate-500 mb-2">예정가격 최빈 구간</p>
            <p className="text-3xl font-bold font-mono text-blue-700">
              {(top1.rate_pct).toFixed(4)}%
            </p>
            <p className="text-sm text-slate-500 mt-1">{fmtWon(top1.amount)}</p>
            <p className="text-xs text-blue-600 mt-1.5 font-medium">
              1,365가지 중 {top1.count}회 ({top1.probability}%)
            </p>
          </div>
        </div>

        {/* Top 3 누적 확률 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-2">Top 3 누적 확률</p>
            <p className="text-3xl font-bold font-mono text-slate-900">
              {top3.reduce((s, r) => s + r.probability, 0).toFixed(1)}%
            </p>
            <p className="text-xs text-slate-500 mt-1 mb-2">
              상위 3개 구간에 예정가격이 집중
            </p>
            <div className="flex gap-1 flex-wrap">
              {top3.map((r, i) => (
                <Badge
                  key={i}
                  className={cn(
                    'text-xs font-mono',
                    i === 0
                      ? 'bg-blue-100 text-blue-700 border-blue-200'
                      : 'bg-slate-100 text-slate-600 border-slate-200',
                  )}
                >
                  {r.rate_pct.toFixed(3)}%
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 추천 투찰금액 */}
        <div className={cn(
          'relative overflow-hidden rounded-xl border-2',
          top1.rate > FLOOR
            ? 'border-emerald-200 bg-emerald-50/30'
            : 'border-amber-200 bg-amber-50/30',
        )}>
          <div className={cn('absolute top-0 left-0 right-0 h-0.5', top1.rate > FLOOR ? 'bg-emerald-500' : 'bg-amber-500')} />
          <div className="p-4">
            <p className="text-xs text-slate-500 mb-2">추천 투찰금액</p>
            {top1.rate > FLOOR ? (
              <>
                <p className="text-2xl font-bold font-mono text-emerald-700">
                  {fmtWon(top1.amount - result.round_unit)}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  최빈 예정가격 {fmtWon(top1.amount)} 직전
                </p>
                <p className="text-xs text-emerald-600 mt-1.5 font-medium">
                  투찰률 {((top1.amount - result.round_unit) / baseAmount * 100).toFixed(4)}%
                </p>
              </>
            ) : (
              <div className="flex items-start gap-2 text-amber-700 mt-1">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <p className="text-sm">최빈 구간이 낙찰하한율 이하. 낙찰하한율 기준 투찰 권장.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 빈도 분포 차트 */}
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-blue-600" />
            예정가격 빈도 분포 — C(15,4) = {result.total_combinations.toLocaleString()}가지 조합
          </CardTitle>
          <p className="text-xs text-slate-500 mt-1">
            막대 높이 = 해당 구간이 예정가격이 될 조합 수. 파란색 강조 막대 = 상위 3개 집중 구간
          </p>
        </CardHeader>
        <CardContent className="p-5">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey="rate_pct"
                tickFormatter={(v) => `${v.toFixed(2)}%`}
                tick={{ fontSize: 12, fill: '#475569' }}
                angle={-30}
                textAnchor="end"
                height={44}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: '#475569' }}
                width={36}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px' }}
                formatter={(v, _n, p) => [
                  `${v}회 (${((Number(v) / result.total_combinations) * 100).toFixed(2)}%)`,
                  '조합 수',
                ]}
                labelFormatter={(l) => `투찰률 ${l}%`}
              />
              <ReferenceLine
                x={FLOOR * 100}
                stroke="#ef4444"
                strokeDasharray="4 2"
                label={{ value: '하한', position: 'top', fontSize: 10, fill: '#ef4444' }}
              />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={index}
                    fill={entry.isTop ? '#2563eb' : '#bfdbfe'}
                    opacity={entry.isTop ? 1 : 0.7}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 상위 빈도 구간 테이블 */}
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Trophy className="h-4 w-4 text-amber-500" />
              예정가격 집중 구간 {showFullTable ? `전체 (${result.frequency.length}개)` : 'Top 10'}
            </CardTitle>
            <button
              onClick={() => setShowFullTable(v => !v)}
              className="text-xs text-blue-600 flex items-center gap-1 hover:underline"
            >
              {showFullTable
                ? <><ChevronUp className="h-3 w-3" /> 접기</>
                : <><ChevronDown className="h-3 w-3" /> 전체 보기</>}
            </button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50/70 border-b border-slate-100">
                  <th className="px-4 py-2.5 text-left text-sm font-medium text-slate-500 w-10">순위</th>
                  <th className="px-4 py-2.5 text-right text-sm font-medium text-slate-500">예정가격</th>
                  <th className="px-4 py-2.5 text-right text-sm font-medium text-slate-500">투찰률</th>
                  <th className="px-4 py-2.5 text-right text-sm font-medium text-slate-500">조합 수</th>
                  <th className="px-4 py-2.5 text-right text-sm font-medium text-slate-500">확률</th>
                  <th className="px-4 py-2.5 text-right text-sm font-medium text-slate-500">누적</th>
                  <th className="px-4 py-2.5 text-left text-sm font-medium text-slate-500">추천 투찰금액</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row, i) => {
                  const rank = i + 1
                  const bidAmount = row.amount - result.round_unit
                  const bidRate = bidAmount / baseAmount
                  const valid = bidRate >= FLOOR
                  return (
                    <tr
                      key={i}
                      className={cn(
                        'border-b border-slate-50 transition-colors',
                        rank <= 3 ? 'bg-blue-50/30 hover:bg-blue-50/50' : 'hover:bg-slate-50/50',
                      )}
                    >
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-100 text-center">
                          <RankBadge rank={rank} />
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-sm text-slate-700">
                        {fmtWon(row.amount)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono">
                        <span className={cn('font-semibold', rank <= 3 ? 'text-blue-600' : 'text-slate-600')}>
                          {row.rate_pct.toFixed(4)}%
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-500 text-xs">
                        {row.count}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className={cn('font-semibold text-sm', rank === 1 ? 'text-blue-600' : 'text-slate-700')}>
                          {row.probability}%
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-500 text-xs">
                        {row.cumulative_prob}%
                      </td>
                      <td className="px-4 py-2.5">
                        {valid ? (
                          <span className="font-mono text-emerald-600 text-xs">
                            {fmtWon(bidAmount)} ({(bidRate * 100).toFixed(4)}%)
                          </span>
                        ) : (
                          <span className="text-xs text-amber-500 bg-amber-50 rounded px-1.5 py-0.5 border border-amber-100">
                            하한율 미달
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* 15개 예비가격 후보 */}
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold text-slate-800">
              예비가격 후보 15개 <span className="text-slate-500 font-normal">(A값 {fmtWon(result.a_value_used)} ±2%)</span>
            </CardTitle>
            <button
              onClick={() => setShowAllCandidates(v => !v)}
              className="text-xs text-blue-600 flex items-center gap-1 hover:underline"
            >
              {showAllCandidates
                ? <><ChevronUp className="h-3 w-3" /> 접기</>
                : <><ChevronDown className="h-3 w-3" /> 펼치기</>}
            </button>
          </div>
        </CardHeader>
        {showAllCandidates && (
          <CardContent className="p-5">
            <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
              {result.candidates.map((c) => (
                <div key={c.idx} className="bg-slate-50 border border-slate-100 rounded-lg p-2.5 text-center">
                  <p className="text-xs text-slate-500 mb-1">#{c.idx}</p>
                  <p className="font-mono font-semibold text-slate-800 text-xs">{fmtWon(c.amount)}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{(c.rate * 100).toFixed(3)}%</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-3">
              반올림 단위: {result.round_unit.toLocaleString()}원 | 총 {result.total_combinations.toLocaleString()}가지 (C(15,4)) 조합 계산
            </p>
          </CardContent>
        )}
      </Card>
    </div>
  )
}

const ZONE_LABEL: Record<string, string> = {
  low:  '저번호 집중 (1~5번)',
  mid:  '중간번호 집중 (6~10번)',
  high: '고번호 집중 (11~15번)',
}

function AgencyPatternPanel({ pattern }: { pattern: AgencyYegaPattern }) {
  if (pattern.sample_count === 0) {
    return (
      <Card className="border-amber-200 bg-amber-50/40 shadow-sm">
        <CardContent className="p-4 text-sm text-amber-700">
          이 발주기관의 최근 낙찰 데이터가 없습니다. 전체 분포를 참고하세요.
        </CardContent>
      </Card>
    )
  }

  const top3Set = new Set(pattern.top3_numbers)
  const displayRows = pattern.pattern.slice(0, 15)

  return (
    <Card className="bg-white border-indigo-200 shadow-sm">
      <CardHeader className="border-b border-indigo-100 pb-3">
        <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-indigo-600" />
          발주기관 특화 패턴 — 상위 번호 하이라이트
        </CardTitle>
        <div className="flex items-center gap-2 flex-wrap mt-1">
          <span className="text-xs text-slate-500">
            분석 표본: {pattern.sample_count}건
          </span>
          {pattern.dominant_zone && (
            <Badge className="text-xs border-indigo-200 bg-indigo-50 text-indigo-700">
              {ZONE_LABEL[pattern.dominant_zone] ?? pattern.dominant_zone}
            </Badge>
          )}
          <div className="flex gap-1">
            {pattern.top3_numbers.map((n, i) => (
              <Badge
                key={i}
                className={cn(
                  'text-xs font-mono',
                  i === 0
                    ? 'bg-indigo-600 text-white'
                    : 'bg-indigo-100 text-indigo-700 border-indigo-200',
                )}
              >
                #{n}
              </Badge>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-5">
        <div className="grid grid-cols-5 gap-2">
          {displayRows.map((row) => (
            <div
              key={row.number}
              className={cn(
                'rounded-lg p-2.5 text-center border transition-all',
                top3Set.has(row.number)
                  ? 'bg-indigo-50 border-indigo-300 shadow-sm'
                  : 'bg-slate-50 border-slate-100',
              )}
            >
              <p className={cn('text-xs mb-0.5', top3Set.has(row.number) ? 'text-indigo-500 font-medium' : 'text-slate-500')}>
                #{row.number}
              </p>
              <p className={cn('font-mono font-semibold', top3Set.has(row.number) ? 'text-indigo-800 text-sm' : 'text-slate-600 text-xs')}>
                {row.freq_pct.toFixed(1)}%
              </p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-3">
          번호 = 예비가격 후보 인덱스 (1: A값 -2% / 15: A값 +2%). 진한 인디고 = 상위 3개.
        </p>
      </CardContent>
    </Card>
  )
}

export default function YegaPage() {
  const [baseAmount, setBaseAmount] = useState('')
  const [aValue, setAValue]         = useState('')
  const [agencyId, setAgencyId]     = useState<number | undefined>()
  const [enabled, setEnabled]       = useState(false)

  const base = parseWon(baseAmount)
  const a    = aValue ? parseWon(aValue) : undefined

  const { data: agencies } = useQuery<{ items: { id: number; name: string }[]; total: number }>({
    queryKey:  ['agencies-list'],
    queryFn:   () => agenciesApi.list({ size: 100 }),
    staleTime: 300_000,
  })

  const agencyOptions = useMemo(
    () => agencies?.items ?? [],
    [agencies],
  )

  const { data, isFetching, error } = useQuery<YegaFrequencyResult>({
    queryKey:  ['yega-frequency', base, a, agencyId],
    queryFn:   () => recommendApi.yegaFrequency(base, a, agencyId),
    enabled:   enabled && base > 0,
    staleTime: 60_000,
  })

  const handleCalc = () => {
    if (base > 0) setEnabled(true)
  }

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-blue-600" />
            예가 빈도 분석
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            복수예가 방식 C(15,4) 조합 분석 — 예정가격이 집중되는 구간을 사전에 파악하여 최적 투찰률 결정
          </p>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-5">
        {/* 안내 배너 */}
        <div className="flex items-start gap-2 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>
            A값(예비가격 기초금액) ±2% 범위에서 15개 후보를 생성하고, 가능한 모든 4개 추첨 조합(1,365가지)의 평균을 계산합니다.
            A값은 공고문 상의 <strong>예비가격 기초금액</strong>을 입력하세요. 없으면 기초금액 기반으로 추정합니다.
          </span>
        </div>

        {/* 입력 카드 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800">공고 정보 입력</CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-700">
                  기초금액 (원) <span className="text-red-500">*</span>
                </Label>
                <Input
                  placeholder="예: 3000000000"
                  value={baseAmount}
                  onChange={(e) => { setBaseAmount(e.target.value); setEnabled(false) }}
                  className="border-slate-200 focus:border-blue-400"
                />
                {base > 0 && (
                  <p className="text-xs text-slate-500">{(base / 1e8).toFixed(2)}억원</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-700">
                  A값 / 예비가격 기초금액 (원)
                  <span className="ml-1 text-xs text-slate-500 font-normal">(선택 — 공고문 참조)</span>
                </Label>
                <Input
                  placeholder="없으면 기초금액 기반 추정"
                  value={aValue}
                  onChange={(e) => { setAValue(e.target.value); setEnabled(false) }}
                  className="border-slate-200 focus:border-blue-400"
                />
                {aValue && parseWon(aValue) > 0 && (
                  <p className="text-xs text-slate-500">
                    {(parseWon(aValue) / 1e8).toFixed(2)}억원
                    {base > 0 && ` (기초금액 대비 ${(parseWon(aValue) / base * 100).toFixed(2)}%)`}
                  </p>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm font-medium text-slate-700 flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5 text-slate-500" />
                발주기관
                <span className="ml-1 text-xs text-slate-500 font-normal">(선택 — 발주기관 특화 패턴 분석)</span>
              </Label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 transition-colors"
                value={agencyId ?? ''}
                onChange={(e) => { setAgencyId(e.target.value ? Number(e.target.value) : undefined); setEnabled(false) }}
              >
                <option value="">전체 (발주기관 미선택)</option>
                {agencyOptions.map((ag) => (
                  <option key={ag.id} value={ag.id}>{ag.name}</option>
                ))}
              </select>
            </div>

            <Button
              onClick={handleCalc}
              disabled={base <= 0}
              className="gap-2 bg-blue-600 hover:bg-blue-700"
            >
              <TrendingUp className="h-4 w-4" />
              빈도 분석 실행
            </Button>
          </CardContent>
        </Card>

        {/* 로딩 */}
        {isFetching && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardContent className="py-12 text-center">
              <div className="flex flex-col items-center gap-3">
                <div className="relative h-10 w-10">
                  <TrendingUp className="h-10 w-10 text-blue-200 absolute" />
                  <TrendingUp className="h-10 w-10 text-blue-500 absolute animate-pulse" />
                </div>
                <p className="text-sm text-slate-500">1,365가지 조합 계산 중...</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* 에러 */}
        {error && (
          <Card className="border-red-200 bg-red-50 shadow-sm">
            <CardContent className="p-4 text-sm text-red-700">
              분석 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.
            </CardContent>
          </Card>
        )}

        {/* 결과 */}
        {data && !isFetching && (
          <>
            {data.agency_pattern && (
              <AgencyPatternPanel pattern={data.agency_pattern} />
            )}
            <ResultPanel result={data} baseAmount={base} />
          </>
        )}
      </div>
    </div>
  )
}
