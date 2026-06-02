import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Sparkles, TrendingUp, TrendingDown, Minus, ChevronDown, ChevronUp,
  Clock, Search,
} from 'lucide-react'
import { bidsApi, recommendApi, statsApi } from '@/api'
import type { RecommendV2Result, BidDetail } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import WinProbGauge from '@/components/ui/WinProbGauge'
import StrategyCompareChart, { type StrategyEntry } from '@/components/ui/StrategyCompareChart'
import SrateRangeViz from '@/components/ui/SrateRangeViz'
import RiskCard from '@/components/ui/RiskCard'

// --- localStorage 키 ---
const HISTORY_KEY  = 'recommend_history_v2'
const PRESETS_KEY  = 'recommend_presets_v1'

interface Preset { name: string; form: typeof defaultForm; agencyName: string }
const defaultForm = { agency_id: '0', industry_id: '0', region_id: '0', base_amount: '', a_value: '', construction_period: '', min_bid_rate: '0.87745' }

function loadPresets(): Preset[] {
  try { return JSON.parse(localStorage.getItem(PRESETS_KEY) ?? '[]') } catch { return [] }
}

interface HistoryEntry {
  agency_id: string
  industry_id: string
  region_id: string
  base_amount: string
  a_value: string
  construction_period: string
  min_bid_rate: string
  agencyName: string
}

function loadHistory(): HistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]')
  } catch {
    return []
  }
}

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
  const [presets, setPresets] = useState<Preset[]>(loadPresets)
  const [presetName, setPresetName] = useState('')
  const [showPresetSave, setShowPresetSave] = useState(false)

  // 기관명 자동완성
  const [agencySearch, setAgencySearch] = useState('')
  const [agencyQuery, setAgencyQuery] = useState('')
  const [showAgencyList, setShowAgencyList] = useState(false)
  const agencyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const t = setTimeout(() => setAgencyQuery(agencySearch), 300)
    return () => clearTimeout(t)
  }, [agencySearch])

  const filteredAgencies = useMemo(() => {
    if (!agencyQuery.trim()) return []
    return (meta?.agencies ?? [])
      .filter((a) => a.name.includes(agencyQuery))
      .slice(0, 8)
  }, [agencyQuery, meta])

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (agencyRef.current && !agencyRef.current.contains(e.target as Node)) {
        setShowAgencyList(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleAgencySelect = (id: number, name: string) => {
    setForm((f) => ({ ...f, agency_id: String(id) }))
    setAgencySearch(name)
    setShowAgencyList(false)
  }

  // 사정율 분포 (Top 10 구간 추천용)
  const { data: srateDist } = useQuery({
    queryKey: ['srate-dist-recommend', form.agency_id, form.industry_id],
    queryFn: () => statsApi.srateDistribution({
      agency_id: Number(form.agency_id) > 0 ? Number(form.agency_id) : undefined,
      industry_id: Number(form.industry_id) > 0 ? Number(form.industry_id) : undefined,
      months: 24,
    }),
    enabled: !!result,
    staleTime: 60_000,
  })

  // 최근 이력
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory)
  const [showHistory, setShowHistory] = useState(false)
  const historyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (historyRef.current && !historyRef.current.contains(e.target as Node)) {
        setShowHistory(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const loadFromHistory = (entry: HistoryEntry) => {
    setForm({
      agency_id: entry.agency_id,
      industry_id: entry.industry_id,
      region_id: entry.region_id,
      base_amount: entry.base_amount,
      a_value: entry.a_value,
      construction_period: entry.construction_period,
      min_bid_rate: entry.min_bid_rate,
    })
    setAgencySearch(entry.agencyName)
    setShowHistory(false)
  }

  // 공고 자동입력
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
      if (agency) setAgencySearch(agency.name)
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
      a_value:             form.a_value            ? Number(form.a_value)            : undefined,
      construction_period: form.construction_period ? Number(form.construction_period) : undefined,
    }),
    onSuccess: (data) => {
      const res = data as RecommendV2Result
      setResult(res)
      const agencyName = meta?.agencies.find((a) => a.id === Number(form.agency_id))?.name ?? ''
      const entry: HistoryEntry = { ...form, agencyName }
      const next = [entry, ...history.filter((h) => h.agency_id !== entry.agency_id || h.base_amount !== entry.base_amount)].slice(0, 5)
      setHistory(next)
      localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
    },
  })

  const valid = Number(form.agency_id) > 0 && Number(form.industry_id) > 0 &&
                Number(form.region_id) > 0 && Number(form.base_amount) > 0
  const pct = (v: number) => (v * 100).toFixed(2)

  // 4전략 데이터 구성
  const strategyData: StrategyEntry[] = result
    ? [
        { name: '공격형',  winProb: result.win_probabilities.at_aggressive  * 100, rate: result.strategies.aggressive.rate,  isSelected: false },
        { name: '균형형',  winProb: result.win_probabilities.at_balanced       * 100, rate: result.strategies.balanced.rate,    isSelected: true  },
        { name: '안정형',  winProb: result.win_probabilities.at_conservative * 100, rate: result.strategies.conservative.rate, isSelected: false },
        { name: '회피형',  winProb: 0,                                              rate: result.competition.floor_rate,       isSelected: false },
      ]
    : []

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

      {/* ── 입력 폼 ── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">입찰 정보 입력</CardTitle>
            {history.length > 0 && (
              <div className="relative" ref={historyRef}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs gap-1"
                  onClick={() => setShowHistory((v) => !v)}
                >
                  <Clock className="h-3 w-3" />
                  최근 이력
                  <ChevronDown className="h-3 w-3" />
                </Button>
                {showHistory && (
                  <div className="absolute right-0 top-8 z-50 w-72 bg-white border border-slate-200 rounded-lg shadow-lg py-1">
                    {history.map((h, i) => (
                      <button
                        key={i}
                        className="w-full text-left px-3 py-2 text-xs hover:bg-slate-50 border-b last:border-0"
                        onClick={() => loadFromHistory(h)}
                      >
                        <div className="font-medium truncate">{h.agencyName}</div>
                        <div className="text-muted-foreground">
                          {Number(h.base_amount).toLocaleString('ko-KR')}원
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {/* 기관명 자동완성 */}
            <div className="space-y-2" ref={agencyRef}>
              <Label>발주기관 *</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                <Input
                  className="pl-8"
                  placeholder="기관명 검색..."
                  value={agencySearch}
                  onChange={(e) => {
                    setAgencySearch(e.target.value)
                    setShowAgencyList(true)
                    if (!e.target.value) setForm((f) => ({ ...f, agency_id: '0' }))
                  }}
                  onFocus={() => setShowAgencyList(true)}
                />
                {showAgencyList && filteredAgencies.length > 0 && (
                  <div className="absolute top-full left-0 right-0 z-50 bg-white border border-slate-200 rounded-lg shadow-lg mt-1 py-1 max-h-48 overflow-auto">
                    {filteredAgencies.map((a) => (
                      <button
                        key={a.id}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => handleAgencySelect(a.id, a.name)}
                      >
                        {a.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {Number(form.agency_id) > 0 && (
                <p className="text-xs text-green-600">선택됨 (ID: {form.agency_id})</p>
              )}
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
              {form.base_amount && Number(form.base_amount) > 0 && (
                <p className="text-xs text-muted-foreground">
                  {Number(form.base_amount).toLocaleString('ko-KR')}원
                </p>
              )}
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

          <div className="flex items-center gap-3 flex-wrap">
            <Button onClick={() => mutation.mutate()} disabled={!valid || mutation.isPending}>
              {mutation.isPending ? '분석 중... (30,000회 시뮬레이션)' : '추천 받기'}
            </Button>
            {/* 프리셋 저장 */}
            {valid && !showPresetSave && (
              <Button variant="outline" size="sm" className="h-9 text-xs gap-1" onClick={() => setShowPresetSave(true)}>
                ★ 조건 저장
              </Button>
            )}
            {showPresetSave && (
              <div className="flex items-center gap-2">
                <Input className="h-9 w-36 text-xs" placeholder="프리셋 이름" value={presetName} onChange={(e) => setPresetName(e.target.value)} />
                <Button size="sm" className="h-9 text-xs" onClick={() => {
                  if (!presetName.trim()) return
                  const p: Preset = { name: presetName.trim(), form: { ...form }, agencyName: agencySearch }
                  const next = [p, ...presets.filter((x) => x.name !== p.name)].slice(0, 8)
                  setPresets(next)
                  localStorage.setItem(PRESETS_KEY, JSON.stringify(next))
                  setPresetName(''); setShowPresetSave(false)
                }}>저장</Button>
                <Button size="sm" variant="ghost" className="h-9 text-xs" onClick={() => setShowPresetSave(false)}>취소</Button>
              </div>
            )}
            {/* 프리셋 불러오기 */}
            {presets.length > 0 && (
              <Select onValueChange={(name) => {
                const p = presets.find((x) => x.name === name); if (!p) return
                setForm({ ...p.form }); setAgencySearch(p.agencyName)
              }}>
                <SelectTrigger className="h-9 w-36 text-xs"><SelectValue placeholder="프리셋 불러오기" /></SelectTrigger>
                <SelectContent>
                  {presets.map((p) => <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
            {mutation.isError && (
              <p className="text-sm text-destructive">추천 오류가 발생했습니다. 잠시 후 다시 시도하세요.</p>
            )}
          </div>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-4">

          {/* ── HERO: 2-column ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 좌: WinProbGauge + 최종 권장 낙찰가율 */}
            <Card className="border-primary/40 bg-primary/5">
              <CardContent className="pt-5 flex flex-col items-center gap-3">
                <WinProbGauge
                  winProb={result.win_probabilities.at_balanced ?? 0}
                  label="낙찰 예상 확률 (균형전략)"
                />
                <div className="text-center">
                  <p className="text-xs font-medium text-primary/60 uppercase tracking-wider mb-1">최종 권장 투찰률</p>
                  <span className="text-5xl font-mono font-black text-primary leading-none">
                    {(result.strategies.balanced.rate * 100).toFixed(2)}%
                  </span>
                  <p className="text-xs text-muted-foreground mt-1">{result.strategies.balanced.target}</p>
                </div>
                <ConfidenceBadge confidence={result.estimated_price.confidence} />
                <div className="w-full grid grid-cols-3 gap-2">
                  <InfoBox label="낙찰하한" value={`${pct(result.competition.floor_rate)}%`} />
                  <InfoBox label="예상 사정율" value={`${(result.estimated_price.srate_range.center * 100).toFixed(3)}%`} />
                  <InfoBox label="예상 예정가" value={`${(result.estimated_price.estimated_price_range.center / 1e8).toFixed(2)}억`} />
                </div>
              </CardContent>
            </Card>

            {/* 우: RiskCard + 경쟁강도 */}
            <div className="space-y-4">
              <RiskCard
                level={result.risk.level as 'LOW' | 'MEDIUM' | 'HIGH'}
                score={result.risk.score}
                factors={result.risk.factors}
              />
              <Card>
                <CardContent className="pt-4">
                  <p className="text-xs font-medium text-muted-foreground mb-3">경쟁강도 지표</p>
                  <div className="grid grid-cols-2 gap-2">
                    <InfoBox label="경쟁강도 점수" value={`${result.competition.score.toFixed(1)}/10`} />
                    <InfoBox label="시장 압박 지수" value={`${(result.competition.pressure * 100).toFixed(0)}%`} />
                    <InfoBox label="예상 경쟁업체" value={`${result.competition.expected_competitors}개사`} />
                    <InfoBox label="공격형 업체비율" value={`${(result.competition.aggressive_ratio * 100).toFixed(0)}%`} />
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* ── 4전략 비교 차트 ── */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">전략별 낙찰 확률 비교</CardTitle>
            </CardHeader>
            <CardContent>
              <StrategyCompareChart strategies={strategyData} />
              <div className="grid grid-cols-3 gap-3 mt-3 border-t pt-3">
                {[
                  { title: '공격형', s: result.strategies.aggressive, wp: result.win_probabilities.at_aggressive },
                  { title: '균형형 (권장)', s: result.strategies.balanced, wp: result.win_probabilities.at_balanced, hl: true },
                  { title: '안정형', s: result.strategies.conservative, wp: result.win_probabilities.at_conservative },
                ].map(({ title, s, wp, hl }) => (
                  <div key={title} className={cn('rounded-md p-2.5 text-xs', hl ? 'bg-primary text-primary-foreground' : 'bg-muted/50')}>
                    <div className={cn('font-medium mb-1', hl ? 'text-primary-foreground/80' : 'text-muted-foreground')}>{title}</div>
                    <div className="text-lg font-mono font-bold">{(s.rate * 100).toFixed(2)}%</div>
                    <div className={cn('mt-1', hl ? 'text-primary-foreground/70' : 'text-muted-foreground')}>
                      낙찰확률 {(wp * 100).toFixed(1)}%
                    </div>
                    <div className={cn('mt-1 leading-snug', hl ? 'text-primary-foreground/70' : 'text-muted-foreground')}>{s.note}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* ── 사정율 예측 범위 ── */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">사정율 예측 범위</CardTitle>
                <ConfidenceBadge confidence={result.estimated_price.confidence} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <SrateRangeViz
                p10={result.estimated_price.srate_range.p10}
                p25={result.estimated_price.srate_range.lower}
                p50={result.estimated_price.srate_range.center}
                p75={result.estimated_price.srate_range.upper}
                p90={result.estimated_price.srate_range.p90}
              />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 border-t pt-3">
                <InfoBox label="예정가격 하단" value={`${(result.estimated_price.estimated_price_range.lower / 1e8).toFixed(2)}억`} />
                <InfoBox label="예정가격 중앙" value={`${(result.estimated_price.estimated_price_range.center / 1e8).toFixed(2)}억`} />
                <InfoBox label="예정가격 상단" value={`${(result.estimated_price.estimated_price_range.upper / 1e8).toFixed(2)}억`} />
                <InfoBox label="샘플 수" value={`${result.estimated_price.sample_count}건`} />
              </div>
              {/* 발주처별 사정율 세분화 */}
              {srateDist && (srateDist.agency_stats || srateDist.global_stats) && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 border-t pt-3 text-xs">
                  {srateDist.agency_stats && (
                    <div className="bg-blue-50 rounded-lg p-2.5 border border-blue-100">
                      <p className="font-semibold text-blue-700 mb-1">이 발주처 기준</p>
                      <p className="text-foreground">평균 {(srateDist.agency_stats.mean * 100).toFixed(3)}%</p>
                      <p className="text-muted-foreground">편차 ±{(srateDist.agency_stats.std * 100).toFixed(3)}%</p>
                      <p className="text-muted-foreground">{srateDist.agency_stats.sample_count}건</p>
                    </div>
                  )}
                  {srateDist.industry_stats && (
                    <div className="bg-gray-50 rounded-lg p-2.5 border border-gray-100">
                      <p className="font-semibold text-gray-600 mb-1">동일 공종 기준</p>
                      <p className="text-foreground">평균 {(srateDist.industry_stats.mean * 100).toFixed(3)}%</p>
                      <p className="text-muted-foreground">편차 ±{(srateDist.industry_stats.std * 100).toFixed(3)}%</p>
                      <p className="text-muted-foreground">{srateDist.industry_stats.sample_count}건</p>
                    </div>
                  )}
                  {srateDist.global_stats && (
                    <div className="bg-gray-50 rounded-lg p-2.5 border border-gray-100">
                      <p className="font-semibold text-gray-600 mb-1">전체 평균</p>
                      <p className="text-foreground">평균 {(srateDist.global_stats.mean * 100).toFixed(3)}%</p>
                      <p className="text-muted-foreground">편차 ±{(srateDist.global_stats.std * 100).toFixed(3)}%</p>
                      <p className="text-muted-foreground">{srateDist.global_stats.sample_count}건</p>
                    </div>
                  )}
                </div>
              )}
              <p className="text-xs text-muted-foreground">
                {result.estimated_price.used_model ? 'ML 모델 사용' : '규칙 기반 추정 (데이터 축적 중)'}
              </p>
              <RateBand
                floor={result.competition.floor_rate}
                lower={result.rate_range.lower}
                center={result.rate_range.center}
                upper={result.rate_range.upper}
              />
            </CardContent>
          </Card>

          {/* ── SHAP 요인 카드 ── */}
          {result.explanation.top_factors.length > 0 && (
            <Card>
              <CardHeader className="pb-0">
                <button
                  className="flex items-center justify-between w-full text-sm font-semibold"
                  onClick={() => setShowDetail((v) => !v)}
                >
                  <span>추천 근거 — SHAP 기여 요인</span>
                  {showDetail ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
              </CardHeader>
              {showDetail && (
                <CardContent className="pt-3 space-y-2">
                  <p className="text-xs bg-blue-50 border border-blue-100 rounded-lg p-3 leading-relaxed text-foreground mb-3">
                    {result.explanation.narrative_ko}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {result.explanation.top_factors.map((f) => (
                      <div
                        key={f.feature}
                        className={cn(
                          'flex items-center gap-3 p-3 rounded-lg border',
                          f.direction === 'positive'
                            ? 'bg-green-50 border-green-200'
                            : 'bg-red-50 border-red-200',
                        )}
                      >
                        <div className={cn('shrink-0', f.direction === 'positive' ? 'text-green-600' : 'text-red-500')}>
                          {f.direction === 'positive'
                            ? <TrendingUp className="h-4 w-4" />
                            : <TrendingDown className="h-4 w-4" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium truncate">{f.label}</div>
                          <div className="h-1.5 bg-white/70 rounded-full mt-1 overflow-hidden">
                            <div
                              className={cn('h-full rounded-full', f.direction === 'positive' ? 'bg-green-400' : 'bg-red-400')}
                              style={{ width: `${Math.min(Math.abs(f.shap_value) * 2000, 100)}%` }}
                            />
                          </div>
                        </div>
                        <div className={cn('text-xs font-mono shrink-0 font-semibold', f.direction === 'positive' ? 'text-green-700' : 'text-red-600')}>
                          {f.shap_value > 0 ? '+' : ''}{f.shap_value.toFixed(4)}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground pt-1">
                    모델: {result.explanation.model_version} / 기준 데이터: {result.explanation.data_count}건
                  </p>
                </CardContent>
              )}
            </Card>
          )}

          {/* ── 경쟁사 프로파일 + 시장변동성 ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">경쟁사 프로파일</CardTitle>
              </CardHeader>
              <CardContent>
                {result.competition.profiles?.length > 0 ? (
                  <div className="space-y-1">
                    {result.competition.profiles.slice(0, 5).map((p) => (
                      <div key={p.competitor_id} className="flex items-center justify-between text-xs py-1 border-b last:border-0">
                        <span className="truncate">{p.name}</span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-muted-foreground">평균 {(p.avg_rate * 100).toFixed(2)}%</span>
                          <RiskBadgeSm level={p.risk_level} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">경쟁사 프로파일 정보 없음</p>
                )}
                <div className="grid grid-cols-2 gap-2 mt-3 border-t pt-3">
                  <InfoBox label="낙찰 집중도(HHI)" value={result.competition.hhi.toFixed(3)} />
                  <InfoBox label="낙찰 불가 하한" value={`${pct(result.competition.floor_rate)}%`} />
                </div>
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
                  <InfoBox label="앙상블 A" value={`${(result.ensemble_weights.engine_a * 100).toFixed(0)}%`} />
                  <InfoBox label="앙상블 B" value={`${(result.ensemble_weights.engine_b * 100).toFixed(0)}%`} />
                </div>
                {!result.market_trend.has_recent_data && (
                  <p className="text-xs text-yellow-600 bg-yellow-50 rounded px-2 py-1">
                    최근 4주 이력 없음 — 전국 평균 기반 추정
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ── 구간 추천 Top 10 ── */}
          {srateDist?.bins && srateDist.bins.length > 0 && (() => {
            const totalCount = srateDist.bins.reduce((s: number, b: { count: number }) => s + b.count, 0)
            const top10 = [...srateDist.bins]
              .sort((a: { count: number }, b: { count: number }) => b.count - a.count)
              .slice(0, 10)
              .map((b: { rate_pct: number; count: number }, idx: number) => ({
                rank: idx + 1,
                pct: (b.rate_pct * 100).toFixed(3) + '%',
                count: b.count,
                ratio: +((b.count / (totalCount || 1)) * 100).toFixed(1),
                isNear: result && Math.abs(b.rate_pct - result.strategies.balanced.rate) < 0.005,
              }))
            return (
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">과거 낙찰 집중 구간 Top 10 <span className="text-xs font-normal text-muted-foreground ml-1">(소수점 3자리 · 24개월)</span></CardTitle>
                    <span className="text-[11px] text-muted-foreground">
                      {srateDist?.agency_stats
                        ? `이 발주처 기준 (${srateDist.agency_stats.sample_count}건)`
                        : srateDist?.global_stats
                        ? `전체 기준 (${srateDist.global_stats.sample_count}건)`
                        : ''}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">순위</TableHead>
                        <TableHead>사정율 구간</TableHead>
                        <TableHead className="text-right">빈도수</TableHead>
                        <TableHead className="text-right">비율</TableHead>
                        <TableHead className="text-center w-20">주목</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {top10.map((row) => (
                        <TableRow key={row.rank} className={cn(row.isNear && 'bg-primary/5 font-medium')}>
                          <TableCell className="text-center font-mono text-muted-foreground">{row.rank}</TableCell>
                          <TableCell className="font-mono font-semibold">{row.pct}</TableCell>
                          <TableCell className="text-right">{row.count.toLocaleString()}건</TableCell>
                          <TableCell className="text-right text-muted-foreground">{row.ratio}%</TableCell>
                          <TableCell className="text-center">
                            {row.isNear && <Badge variant="default" className="text-[10px] px-1.5 py-0">추천 근접</Badge>}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )
          })()}

          {/* ── 유사 사례 ── */}
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
                      <TableRow
                        key={s.bid_id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/bids/${s.bid_id}`)}
                      >
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

// ── 서브 컴포넌트 ──────────────────────────────────────────

function RateBand({ floor, lower, center, upper }: { floor: number; lower: number; center: number; upper: number }) {
  const min = floor * 100 - 0.2
  const max = upper * 100 + 0.5
  const p = (v: number) => ((v * 100 - min) / (max - min) * 100)
  return (
    <div>
      <div className="relative h-8 bg-muted rounded-full overflow-hidden">
        <div className="absolute h-full bg-red-100 rounded-full" style={{ left: '0%', width: `${p(floor)}%` }} />
        <div className="absolute h-full bg-blue-100 rounded-full"
          style={{ left: `${p(lower)}%`, width: `${p(upper) - p(lower)}%` }} />
        <div className="absolute top-0 h-full w-1 bg-primary rounded"
          style={{ left: `${p(center)}%`, transform: 'translateX(-50%)' }} />
        <div className="absolute top-0 h-full w-0.5 bg-red-400" style={{ left: `${p(floor)}%` }} />
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
  const p = Math.round(confidence * 100)
  const variant = p >= 70 ? 'success' : p >= 40 ? 'warning' : 'destructive'
  return <Badge variant={variant}>신뢰도 {p}%</Badge>
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

function RiskBadgeSm({ level }: { level: string }) {
  const variant = level === 'HIGH' ? 'destructive' : level === 'MEDIUM' ? 'warning' : 'success'
  return <Badge variant={variant} className="text-[10px] px-1.5 py-0">{level}</Badge>
}
