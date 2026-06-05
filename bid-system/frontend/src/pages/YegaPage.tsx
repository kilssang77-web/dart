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
  if (rank === 1) return <span className="text-yellow-500 font-bold text-base">🥇</span>
  if (rank === 2) return <span className="text-slate-400 font-bold text-base">🥈</span>
  if (rank === 3) return <span className="text-amber-600 font-bold text-base">🥉</span>
  return <span className="text-muted-foreground text-sm font-mono">{rank}</span>
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
      {/* 핵심 결과 요약 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="border-2 border-primary/50 bg-primary/5">
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">예정가격 최빈 구간</p>
            <p className="text-2xl font-bold font-mono text-primary">
              {(top1.rate_pct).toFixed(4)}%
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {fmtWon(top1.amount)}
            </p>
            <p className="text-xs text-primary mt-1 font-medium">
              1,365가지 중 {top1.count}회 ({top1.probability}%)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">Top 3 누적 확률</p>
            <p className="text-2xl font-bold font-mono">
              {top3.reduce((s, r) => s + r.probability, 0).toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              상위 3개 구간에 예정가격이 집중
            </p>
            <div className="flex gap-1 mt-2 flex-wrap">
              {top3.map((r, i) => (
                <Badge key={i} variant={i === 0 ? 'default' : 'secondary'} className="text-xs font-mono">
                  {r.rate_pct.toFixed(3)}%
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className={cn(
          'border-2',
          top1.rate > FLOOR ? 'border-green-400 bg-green-50/30' : 'border-orange-400 bg-orange-50/30',
        )}>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">추천 투찰금액</p>
            {top1.rate > FLOOR ? (
              <>
                <p className="text-2xl font-bold font-mono text-green-700">
                  {fmtWon(top1.amount - result.round_unit)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  최빈 예정가격 {fmtWon(top1.amount)} 직전
                </p>
                <p className="text-xs text-green-700 mt-1 font-medium">
                  투찰률 {((top1.amount - result.round_unit) / baseAmount * 100).toFixed(4)}%
                </p>
              </>
            ) : (
              <div className="flex items-start gap-2 text-orange-700">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <p className="text-sm">최빈 구간이 낙찰하한율 이하. 낙찰하한율 기준 투찰 권장.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 빈도 분포 차트 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            예정가격 빈도 분포 — C(15,4) = {result.total_combinations.toLocaleString()}가지 조합
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            막대 높이 = 해당 구간이 예정가격이 될 조합 수. 🟦 강조된 막대 = 상위 3개 집중 구간
          </p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="rate_pct"
                tickFormatter={(v) => `${v.toFixed(2)}%`}
                tick={{ fontSize: 10 }}
                angle={-30}
                textAnchor="end"
                height={44}
              />
              <YAxis tick={{ fontSize: 10 }} width={36} />
              <Tooltip
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
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={index}
                    fill={entry.isTop ? '#3b82f6' : '#93c5fd'}
                    opacity={entry.isTop ? 1 : 0.6}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 상위 빈도 구간 테이블 */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Trophy className="h-4 w-4 text-yellow-500" />
              예정가격 집중 구간 {showFullTable ? `전체 (${result.frequency.length}개)` : 'Top 10'}
            </CardTitle>
            <button
              onClick={() => setShowFullTable(v => !v)}
              className="text-xs text-primary flex items-center gap-1 hover:underline"
            >
              {showFullTable ? <><ChevronUp className="h-3 w-3" /> 접기</> : <><ChevronDown className="h-3 w-3" /> 전체 보기</>}
            </button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-3 py-2 text-left w-10">순위</th>
                  <th className="px-3 py-2 text-right">예정가격</th>
                  <th className="px-3 py-2 text-right">투찰률</th>
                  <th className="px-3 py-2 text-right">조합 수</th>
                  <th className="px-3 py-2 text-right">확률</th>
                  <th className="px-3 py-2 text-right">누적</th>
                  <th className="px-3 py-2 text-left">추천 투찰금액</th>
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
                        'border-t hover:bg-muted/30',
                        rank <= 3 ? 'bg-blue-50/40' : '',
                      )}
                    >
                      <td className="px-3 py-2"><RankBadge rank={rank} /></td>
                      <td className="px-3 py-2 text-right font-mono text-sm">
                        {fmtWon(row.amount)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        <span className={cn('font-semibold', rank <= 3 ? 'text-primary' : '')}>
                          {row.rate_pct.toFixed(4)}%
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground">
                        {row.count}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn('font-semibold', rank === 1 ? 'text-primary' : '')}>
                          {row.probability}%
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                        {row.cumulative_prob}%
                      </td>
                      <td className="px-3 py-2">
                        {valid ? (
                          <span className="font-mono text-green-700 text-xs">
                            {fmtWon(bidAmount)} ({(bidRate * 100).toFixed(4)}%)
                          </span>
                        ) : (
                          <span className="text-xs text-orange-500">하한율 미달</span>
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
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">
              예비가격 후보 15개 (A값 {fmtWon(result.a_value_used)} ±2%)
            </CardTitle>
            <button
              onClick={() => setShowAllCandidates(v => !v)}
              className="text-xs text-primary flex items-center gap-1 hover:underline"
            >
              {showAllCandidates ? <><ChevronUp className="h-3 w-3" /> 접기</> : <><ChevronDown className="h-3 w-3" /> 펼치기</>}
            </button>
          </div>
        </CardHeader>
        {showAllCandidates && (
          <CardContent>
            <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
              {result.candidates.map((c) => (
                <div key={c.idx} className="bg-muted/40 rounded p-2 text-center text-xs">
                  <p className="text-muted-foreground">#{c.idx}</p>
                  <p className="font-mono font-semibold">{fmtWon(c.amount)}</p>
                  <p className="text-muted-foreground">{(c.rate * 100).toFixed(3)}%</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
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
      <Card className="border-amber-200 bg-amber-50/40">
        <CardContent className="pt-4 text-sm text-amber-700">
          이 발주처의 최근 낙찰 데이터가 없습니다. 전체 분포를 참고하세요.
        </CardContent>
      </Card>
    )
  }

  const top3Set = new Set(pattern.top3_numbers)
  const displayRows = pattern.pattern.slice(0, 15)

  return (
    <Card className="border-2 border-indigo-200 bg-indigo-50/20">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Building2 className="h-4 w-4 text-indigo-600" />
          발주처 특화 패턴 — 상위 번호 하이라이트
        </CardTitle>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">
            분석 표본: {pattern.sample_count}건
          </span>
          {pattern.dominant_zone && (
            <Badge variant="outline" className="text-xs border-indigo-400 text-indigo-700">
              {ZONE_LABEL[pattern.dominant_zone] ?? pattern.dominant_zone}
            </Badge>
          )}
          <div className="flex gap-1">
            {pattern.top3_numbers.map((n, i) => (
              <Badge key={i} className={cn('text-xs font-mono', i === 0 ? 'bg-indigo-600' : 'bg-indigo-400')}>
                #{n}
              </Badge>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-1.5">
          {displayRows.map((row) => (
            <div
              key={row.number}
              className={cn(
                'rounded p-2 text-center text-xs border',
                top3Set.has(row.number)
                  ? 'bg-indigo-100 border-indigo-400 font-bold'
                  : 'bg-muted/30 border-transparent',
              )}
            >
              <p className={cn('text-muted-foreground', top3Set.has(row.number) && 'text-indigo-700')}>
                #{row.number}
              </p>
              <p className={cn('font-mono', top3Set.has(row.number) ? 'text-indigo-800 text-sm' : 'text-xs')}>
                {row.freq_pct.toFixed(1)}%
              </p>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          번호 = 예비가격 후보 인덱스 (1: A값 -2% / 15: A값 +2%). 진한 파랑 = 상위 3개.
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
    queryFn:   () => agenciesApi.list({ size: 200 }),
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
    <div className="p-6 space-y-6 max-w-4xl">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary" />
          예가 빈도 분석
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          복수예가 방식 C(15,4) 조합 분석 — 예정가격이 집중되는 구간을 사전에 파악하여 최적 투찰률 결정
        </p>
        <div className="flex items-start gap-1.5 mt-2 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-md px-3 py-2">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>
            A값(예비가격 기초금액) ±2% 범위에서 15개 후보를 생성하고, 가능한 모든 4개 추첨 조합(1,365가지)의 평균을 계산합니다.
            <br />
            A값은 공고문 상의 <strong>예비가격 기초금액</strong>을 입력하세요. 없으면 기초금액 기반으로 추정합니다.
          </span>
        </div>
      </div>

      {/* 입력 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">공고 정보 입력</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>기초금액 (원) <span className="text-red-500">*</span></Label>
              <Input
                placeholder="예: 3000000000"
                value={baseAmount}
                onChange={(e) => { setBaseAmount(e.target.value); setEnabled(false) }}
              />
              {base > 0 && (
                <p className="text-xs text-muted-foreground">{(base / 1e8).toFixed(2)}억원</p>
              )}
            </div>

            <div className="space-y-2">
              <Label>
                A값 / 예비가격 기초금액 (원)
                <span className="ml-1 text-xs text-muted-foreground">(선택 — 공고문 참조)</span>
              </Label>
              <Input
                placeholder="없으면 기초금액 기반 추정"
                value={aValue}
                onChange={(e) => { setAValue(e.target.value); setEnabled(false) }}
              />
              {aValue && parseWon(aValue) > 0 && (
                <p className="text-xs text-muted-foreground">
                  {(parseWon(aValue) / 1e8).toFixed(2)}억원
                  {base > 0 && ` (기초금액 대비 ${(parseWon(aValue) / base * 100).toFixed(2)}%)`}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-1">
              <Building2 className="h-3.5 w-3.5" />
              발주처
              <span className="ml-1 text-xs text-muted-foreground">(선택 — 발주처 특화 패턴 분석)</span>
            </Label>
            <select
              className="w-full border rounded-md px-3 py-2 text-sm bg-background"
              value={agencyId ?? ''}
              onChange={(e) => { setAgencyId(e.target.value ? Number(e.target.value) : undefined); setEnabled(false) }}
            >
              <option value="">전체 (발주처 미선택)</option>
              {agencyOptions.map((ag) => (
                <option key={ag.id} value={ag.id}>{ag.name}</option>
              ))}
            </select>
          </div>

          <Button onClick={handleCalc} disabled={base <= 0} className="gap-2">
            <TrendingUp className="h-4 w-4" />
            빈도 분석 실행
          </Button>
        </CardContent>
      </Card>

      {/* 로딩 */}
      {isFetching && (
        <Card>
          <CardContent className="pt-8 pb-8 text-center text-muted-foreground">
            <TrendingUp className="h-8 w-8 animate-pulse mx-auto mb-2 text-primary" />
            <p>1,365가지 조합 계산 중...</p>
          </CardContent>
        </Card>
      )}

      {/* 에러 */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-4 text-sm text-red-700">
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
  )
}
