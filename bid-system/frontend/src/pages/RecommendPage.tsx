import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Sparkles, AlertTriangle, TrendingUp, TrendingDown, Minus, ChevronDown, ChevronUp } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine
} from 'recharts'
import { bidsApi, recommendApi } from '@/api'
import type { RecommendV2Result, BidDetail } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'

export default function RecommendPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const bidIdParam = searchParams.get('bid_id')

  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: bidsApi.meta })
  const { data: prefillBid } = useQuery<BidDetail>({
    queryKey: ['bid', bidIdParam],
    queryFn: () => bidsApi.detail(Number(bidIdParam)),
    enabled: !!bidIdParam,
  })

  const [form, setForm] = useState({
    agency_id: '0', industry_id: '0', region_id: '0',
    base_amount: '', a_value: '', construction_period: '',
    min_bid_rate: '0.87745',
  })
  const [result, setResult] = useState<RecommendV2Result | null>(null)
  const [prefilled, setPrefilled] = useState(false)
  const [showDetail, setShowDetail] = useState(false)

  useEffect(() => {
    if (prefillBid && meta && !prefilled) {
      const agency   = meta.agencies.find((a) => a.name === prefillBid.agency_name)
      const industry = meta.industries.find((i) => i.name === prefillBid.industry_name)
      const region   = meta.regions.find((r) => r.name === prefillBid.region_name)
      setForm({
        agency_id:            String(agency?.id ?? 0),
        industry_id:          String(industry?.id ?? 0),
        region_id:            String(region?.id ?? 0),
        base_amount:          prefillBid.base_amount ? String(prefillBid.base_amount) : '',
        a_value:              prefillBid.a_value ? String(prefillBid.a_value) : '',
        construction_period:  prefillBid.construction_period ? String(prefillBid.construction_period) : '',
        min_bid_rate:         prefillBid.min_bid_rate ? String(prefillBid.min_bid_rate) : '0.87745',
      })
      setPrefilled(true)
    }
  }, [prefillBid, meta, prefilled])

  const mutation = useMutation({
    mutationFn: () => recommendApi.recommendV2({
      agency_id:           Number(form.agency_id),
      industry_id:         Number(form.industry_id),
      region_id:           Number(form.region_id),
      base_amount:         Number(form.base_amount),
      min_bid_rate:        Number(form.min_bid_rate) || 0.87745,
      a_value:             form.a_value     ? Number(form.a_value)     : undefined,
      construction_period: form.construction_period ? Number(form.construction_period) : undefined,
    }),
    onSuccess: (data) => setResult(data as RecommendV2Result),
  })

  const valid = Number(form.agency_id) > 0 && Number(form.industry_id) > 0 &&
                Number(form.region_id) > 0 && Number(form.base_amount) > 0
  const pct = (v: number) => (v * 100).toFixed(2)

  return (
    <div className="p-6 space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            AI 투찰률 추천
          </h1>
          <p className="text-muted-foreground text-sm mt-1">하이브리드 v2 — 사정율 + 역사패턴 + 경쟁강도</p>
        </div>
        {bidIdParam && (
          <Button variant="ghost" size="sm" onClick={() => navigate(`/bids/${bidIdParam}`)}>
            ← 공고 상세로 돌아가기
          </Button>
        )}
      </div>

      {prefillBid && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
          <strong>공고 연계:</strong> {prefillBid.title}
        </div>
      )}

      {/* 입력 폼 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">입찰 정보 입력</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>발주기관 *</Label>
              <Select value={form.agency_id} onValueChange={(v) => setForm((f) => ({ ...f, agency_id: v }))}>
                <SelectTrigger><SelectValue placeholder="선택하세요" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">선택하세요</SelectItem>
                  {(meta?.agencies ?? []).map((o) => <SelectItem key={o.id} value={String(o.id)}>{o.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>공종 *</Label>
              <Select value={form.industry_id} onValueChange={(v) => setForm((f) => ({ ...f, industry_id: v }))}>
                <SelectTrigger><SelectValue placeholder="선택하세요" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">선택하세요</SelectItem>
                  {(meta?.industries ?? []).map((o) => <SelectItem key={o.id} value={String(o.id)}>{o.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>지역 *</Label>
              <Select value={form.region_id} onValueChange={(v) => setForm((f) => ({ ...f, region_id: v }))}>
                <SelectTrigger><SelectValue placeholder="선택하세요" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">선택하세요</SelectItem>
                  {(meta?.regions ?? []).map((o) => <SelectItem key={o.id} value={String(o.id)}>{o.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>기초금액 (원) *</Label>
              <Input
                type="number"
                value={form.base_amount}
                onChange={(e) => setForm((f) => ({ ...f, base_amount: e.target.value }))}
                placeholder="예: 500000000"
              />
            </div>
            <div className="space-y-2">
              <Label>낙찰하한율</Label>
              <Input
                type="number"
                value={form.min_bid_rate}
                onChange={(e) => setForm((f) => ({ ...f, min_bid_rate: e.target.value }))}
                placeholder="예: 0.87745"
              />
            </div>
            <div className="space-y-2">
              <Label>A값 (원)</Label>
              <Input
                type="number"
                value={form.a_value}
                onChange={(e) => setForm((f) => ({ ...f, a_value: e.target.value }))}
                placeholder="선택사항"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={() => mutation.mutate()} disabled={!valid || mutation.isPending}>
              {mutation.isPending ? '분석 중...' : '추천 받기'}
            </Button>
            {mutation.isError && (
              <p className="text-sm text-destructive">추천 오류가 발생했습니다. 잠시 후 다시 시도하세요.</p>
            )}
          </div>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-4">
          {/* ── 최종 권장 히어로 ── */}
          <Card className="border-primary/40 bg-primary/5">
            <CardContent className="pt-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="text-xs font-medium text-primary/60 uppercase tracking-wider mb-1">최종 권장 투찰률</p>
                  <div className="flex items-baseline gap-3">
                    <span className="text-5xl font-mono font-black text-primary leading-none">
                      {(result.strategies.balanced.rate * 100).toFixed(2)}%
                    </span>
                    <span className="text-sm text-muted-foreground">{result.strategies.balanced.target}</span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <ConfidenceBadge confidence={result.estimated_price.confidence} />
                  <RiskBadge level={result.risk.level} score={result.risk.score} />
                </div>
              </div>
              <div className="mt-1">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">낙찰 예상 확률</span>
                  <span className="font-semibold text-foreground">
                    {result.win_probabilities.at_center != null
                      ? `${(result.win_probabilities.at_center * 100).toFixed(1)}%`
                      : '데이터 축적 중'}
                  </span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-700"
                    style={{ width: result.win_probabilities.at_center != null
                      ? `${Math.min(100, Math.round(result.win_probabilities.at_center * 100))}%`
                      : '0%' }}
                  />
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3">
                <InfoBox label="낙찰하한" value={`${(result.competition.floor_rate * 100).toFixed(2)}%`} />
                <InfoBox label="예상 사정율" value={`${(result.estimated_price.srate_range.center * 100).toFixed(3)}%`} />
                <InfoBox label="예상 경쟁업체" value={`${result.competition.expected_competitors}개사`} />
              </div>
            </CardContent>
          </Card>

          {/* 전략별 3가지 추천 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <StrategyCard
              title="공격적 전략"
              strategy={result.strategies.aggressive}
              winProb={result.win_probabilities.at_aggressive}
            />
            <StrategyCard
              title="균형 전략 (권장)"
              strategy={result.strategies.balanced}
              winProb={result.win_probabilities.at_center}
              highlight
            />
            <StrategyCard
              title="안정적 전략"
              strategy={result.strategies.conservative}
              winProb={result.win_probabilities.at_conservative}
            />
          </div>

          {/* 사정율 + 예정가격 추정 */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">사정율 예측 · 예정가격 추정</CardTitle>
                <ConfidenceBadge confidence={result.estimated_price.confidence} />
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <InfoBox label="예상 사정율 (중앙)" value={`${(result.estimated_price.srate_range.center * 100).toFixed(3)}%`} />
                <InfoBox label="사정율 범위"
                  value={`${(result.estimated_price.srate_range.lower*100).toFixed(2)}% ~ ${(result.estimated_price.srate_range.upper*100).toFixed(2)}%`} />
                <InfoBox label="예상 예정가격 (중앙)"
                  value={`${(result.estimated_price.estimated_price_range.center / 1e8).toFixed(2)}억`} />
                <InfoBox label="예정가격 범위"
                  value={`${(result.estimated_price.estimated_price_range.lower/1e8).toFixed(2)} ~ ${(result.estimated_price.estimated_price_range.upper/1e8).toFixed(2)}억`} />
              </div>
              <p className="text-xs text-muted-foreground">
                {result.estimated_price.used_model
                  ? `ML 모델 사용 (학습 데이터 ${result.estimated_price.sample_count}건)`
                  : `규칙 기반 추정 (학습 데이터 ${result.estimated_price.sample_count}건 — 데이터 축적 중)`}
              </p>
              <RateBand
                floor={result.competition.floor_rate}
                lower={result.rate_range.lower}
                center={result.rate_range.center}
                upper={result.rate_range.upper}
              />
            </CardContent>
          </Card>

          {/* 경쟁강도 + 시장변동성 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">경쟁강도 분석 (Engine C)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <InfoBox label="경쟁강도 점수" value={`${result.competition.score.toFixed(1)}/10`} />
                  <InfoBox label="시장 압박 지수" value={`${(result.competition.pressure * 100).toFixed(0)}%`} />
                  <InfoBox label="낙찰 집중도(HHI)" value={result.competition.hhi.toFixed(3)} />
                  <InfoBox label="예상 경쟁업체"  value={`${result.competition.expected_competitors}개사`} />
                  <InfoBox label="낙찰 불가 하한"  value={`${pct(result.competition.floor_rate)}%`} />
                  <InfoBox label="공격적 업체 비율" value={`${(result.competition.aggressive_ratio*100).toFixed(0)}%`} />
                </div>
                {result.competition.profiles?.length > 0 && (
                  <div className="border-t pt-3">
                    <p className="text-xs text-muted-foreground mb-2">알려진 경쟁사 프로파일</p>
                    <div className="space-y-1">
                      {result.competition.profiles.slice(0,4).map((p) => (
                        <div key={p.competitor_id} className="flex items-center justify-between text-xs">
                          <span className="truncate">{p.name}</span>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className="text-muted-foreground">평균 {(p.avg_rate*100).toFixed(2)}%</span>
                            <RiskBadgeSm level={p.risk_level} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">시장 변동성 (Engine D)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <TrendRow label="4주 사정율 변화" value={result.market_trend.srate_4w_change} unit="" isRate />
                  <TrendRow label="4주 낙찰률 변화" value={result.market_trend.rate_4w_change} unit="" isRate />
                  <TrendRow label="4주 입찰건수 변화" value={result.market_trend.volume_4w_change} unit="" isRate />
                </div>
                <div className="border-t pt-3 grid grid-cols-2 gap-3">
                  <InfoBox label="앙상블 가중치 A" value={`${(result.ensemble_weights.engine_a * 100).toFixed(0)}%`} />
                  <InfoBox label="앙상블 가중치 B" value={`${(result.ensemble_weights.engine_b * 100).toFixed(0)}%`} />
                </div>
                {!result.market_trend.has_recent_data && (
                  <p className="text-xs text-yellow-600 bg-yellow-50 rounded px-2 py-1">
                    최근 4주 이력 없음 — 전국 평균 기반 추정
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 리스크 + 설명 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">리스크 평가</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <RiskBadge level={result.risk.level} score={result.risk.score} />
                <ul className="space-y-1">
                  {result.risk.factors.map((f, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                      <AlertTriangle className="h-3 w-3 text-yellow-500 mt-0.5 shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">추천 근거 (SHAP + 사정율 분석)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm bg-blue-50 border border-blue-100 rounded-lg p-3 leading-relaxed text-foreground">
                  {result.explanation.narrative_ko}
                </p>
                <p className="text-xs text-muted-foreground">
                  모델: {result.explanation.model_version} / 기준 데이터: {result.explanation.data_count}건
                </p>
              </CardContent>
            </Card>
          </div>

          {/* SHAP 요인 상세 (토글) */}
          {result.explanation.top_factors.length > 0 && (
            <Card>
              <CardHeader className="pb-0">
                <button
                  className="flex items-center justify-between w-full text-sm font-semibold"
                  onClick={() => setShowDetail((v) => !v)}
                >
                  SHAP 기여 요인 상세
                  {showDetail ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
              </CardHeader>
              {showDetail && (
                <CardContent className="pt-3 space-y-2">
                  {result.explanation.top_factors.map((f) => (
                    <div key={f.feature} className="flex items-center gap-3">
                      <div className="w-44 text-xs text-muted-foreground truncate">{f.label}</div>
                      <div className="flex-1 h-5 bg-muted rounded overflow-hidden">
                        <div
                          className={cn('h-full rounded', f.direction === 'positive' ? 'bg-green-400' : 'bg-red-400')}
                          style={{ width: `${Math.min(Math.abs(f.shap_value) * 2000, 100)}%` }}
                        />
                      </div>
                      <div className="text-xs font-mono text-muted-foreground w-18 text-right">
                        {f.shap_value > 0 ? '+' : ''}{f.shap_value.toFixed(4)}
                      </div>
                    </div>
                  ))}
                </CardContent>
              )}
            </Card>
          )}

          {/* 유사 사례 */}
          {result.similar_cases.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">유사 입찰 사례</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>공고명</TableHead>
                      <TableHead>기관</TableHead>
                      <TableHead className="text-right">기초금액</TableHead>
                      <TableHead className="text-right">낙찰률</TableHead>
                      <TableHead className="text-center">경쟁사</TableHead>
                      <TableHead className="text-right">유사도</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.similar_cases.map((s) => (
                      <TableRow key={s.bid_id} className="cursor-pointer"
                        onClick={() => navigate(`/bids/${s.bid_id}`)}>
                        <TableCell className="max-w-xs truncate">{s.title}</TableCell>
                        <TableCell className="whitespace-nowrap">{s.agency_name}</TableCell>
                        <TableCell className="text-right">{(s.base_amount / 1e8).toFixed(1)}억</TableCell>
                        <TableCell className="text-right font-mono font-semibold text-primary">
                          {s.winner_rate ? pct(s.winner_rate) + '%' : '-'}
                        </TableCell>
                        <TableCell className="text-center">{s.competitor_count}</TableCell>
                        <TableCell className="text-right">{(s.similarity_score * 100).toFixed(0)}%</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

// Sub-components

function StrategyCard({
  title, strategy, winProb, highlight
}: {
  title: string
  strategy: { rate: number; target: string; risk: string; note: string }
  winProb: number
  highlight?: boolean
}) {
  return (
    <Card className={cn(highlight && 'border-primary bg-primary text-primary-foreground')}>
      <CardContent className="pt-5">
        <div className={cn('text-xs font-medium mb-1', highlight ? 'text-primary-foreground/70' : 'text-muted-foreground')}>{title}</div>
        <div className="text-3xl font-mono font-bold mb-1">{(strategy.rate * 100).toFixed(2)}%</div>
        <div className={cn('text-xs mb-3', highlight ? 'text-primary-foreground/70' : 'text-muted-foreground')}>{strategy.target}</div>
        <div className="flex items-center justify-between">
          <span className={cn('text-xs', highlight ? 'text-primary-foreground/70' : 'text-muted-foreground')}>낙찰 예상</span>
          <span className="text-sm font-semibold">{(winProb * 100).toFixed(1)}%</span>
        </div>
        <div className={cn('mt-2 text-xs leading-relaxed', highlight ? 'text-primary-foreground/70' : 'text-muted-foreground')}>{strategy.note}</div>
      </CardContent>
    </Card>
  )
}

function RateBand({ floor, lower, center, upper }: { floor: number; lower: number; center: number; upper: number }) {
  const min = floor * 100 - 0.2
  const max = upper * 100 + 0.5
  const p = (v: number) => ((v * 100 - min) / (max - min) * 100)
  return (
    <div className="mt-2">
      <div className="relative h-8 bg-muted rounded-full overflow-hidden">
        <div className="absolute h-full bg-red-100 rounded-full"
          style={{ left: '0%', width: `${p(floor)}%` }} />
        <div className="absolute h-full bg-blue-100 rounded-full"
          style={{ left: `${p(lower)}%`, width: `${p(upper) - p(lower)}%` }} />
        <div className="absolute top-0 h-full w-1 bg-primary rounded"
          style={{ left: `${p(center)}%`, transform: 'translateX(-50%)' }} />
        <div className="absolute top-0 h-full w-0.5 bg-red-400"
          style={{ left: `${p(floor)}%` }} />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground mt-1">
        <span>낙찰하한 {(floor * 100).toFixed(2)}%</span>
        <span>하단 {(lower * 100).toFixed(2)}%</span>
        <span className="font-semibold text-primary">권장 {(center * 100).toFixed(2)}%</span>
        <span>상단 {(upper * 100).toFixed(2)}%</span>
      </div>
    </div>
  )
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)
  const variant = pct >= 70 ? 'success' : pct >= 40 ? 'warning' : 'destructive'
  return <Badge variant={variant}>신뢰도 {pct}%</Badge>
}

function InfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/50 rounded-md p-2.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold mt-0.5">{value}</div>
    </div>
  )
}

function TrendRow({ label, value, isRate }: { label: string; value: number; unit: string; isRate?: boolean }) {
  const Icon = value > 0.001 ? TrendingUp : value < -0.001 ? TrendingDown : Minus
  const color = value > 0.001 ? 'text-blue-600' : value < -0.001 ? 'text-red-500' : 'text-muted-foreground'
  const display = isRate ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(3)}%` : String(value)
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn('flex items-center gap-1 font-mono text-xs font-semibold', color)}>
        <Icon className="h-3 w-3" /> {display}
      </span>
    </div>
  )
}

function RiskBadge({ level, score }: { level: string; score: number }) {
  const variant = level === 'HIGH' ? 'destructive' : level === 'MEDIUM' ? 'warning' : 'success'
  const label = level === 'HIGH' ? '높음' : level === 'MEDIUM' ? '보통' : '낮음'
  return (
    <Badge variant={variant} className="text-sm px-3 py-1">
      리스크 {label} ({score.toFixed(1)}점)
    </Badge>
  )
}

function RiskBadgeSm({ level }: { level: string }) {
  const variant = level === 'HIGH' ? 'destructive' : level === 'MEDIUM' ? 'warning' : 'success'
  return <Badge variant={variant} className="text-[10px] px-1.5 py-0">{level}</Badge>
}