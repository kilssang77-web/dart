import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, ExternalLink, Sparkles, Target, Handshake, Radar,
  Building2, Trophy, AlertTriangle, FileText, Brain, Shield, Users, BarChart2, TrendingUp,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { bidsApi, agenciesApi, recommendApi } from '@/api'
import type {
  BidDetail, FinalRecommendResult, RivalRadarResponse,
  SrateHistogramResponse, AgencyRecentResultsResponse,
  YegaFrequencyResult, OpportunityScore, ActualWinZonesResponse,
  BidRangeResponse, MetaData, FinalRecommendStrategy,
} from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const fmt = (n: number) => new Intl.NumberFormat('ko-KR').format(Math.round(n))
const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`
const fmtRate = (n: number) => `${(n * 100).toFixed(3)}%`
const fmtDate = (s: string | null) => (s ? s.slice(0, 10) : '-')

// ── TabInfo ──────────────────────────────────────────────────────────────

function TabInfo({ bid, score }: { bid: BidDetail; score: OpportunityScore | undefined }) {
  const grade = score?.grade
  const gradeColor =
    grade === 'A' ? 'bg-emerald-500' :
    grade === 'B' ? 'bg-blue-500' :
    grade === 'C' ? 'bg-amber-500' : 'bg-red-500'

  return (
    <div className="space-y-4">
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <FileText className="h-4 w-4 text-blue-600" />공고 기본정보
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">공고번호</dt>
              <dd className="font-mono text-xs text-slate-700 bg-slate-50 rounded px-2 py-1 inline-block">{bid.announcement_no}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">발주처</dt>
              <dd className="font-medium text-slate-800">{bid.agency_name}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">업종</dt>
              <dd className="text-slate-700">{bid.industry_name ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">지역</dt>
              <dd className="text-slate-700">{bid.region_name ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">기초금액</dt>
              <dd className="font-semibold text-slate-900">₩{fmt(bid.base_amount)}원</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">공고일</dt>
              <dd className="text-slate-700">{fmtDate(bid.notice_date)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">개찰일</dt>
              <dd className="font-medium text-slate-800">{fmtDate(bid.bid_open_date)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">마감일</dt>
              <dd className="text-slate-700">{fmtDate(bid.bid_close_date)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">입찰방법</dt>
              <dd className="text-slate-700">{bid.bid_method ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">계약방법</dt>
              <dd className="text-slate-700">{bid.contract_method ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">공사위치</dt>
              <dd className="text-slate-700">{bid.construction_site ?? '-'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 mb-0.5">지역제한</dt>
              <dd className="text-slate-700">{bid.region_restriction ? (bid.eligible_regions ?? '있음') : '없음'}</dd>
            </div>
            {bid.contact_name && (
              <div>
                <dt className="text-xs text-slate-400 mb-0.5">담당자</dt>
                <dd className="text-slate-700">{bid.contact_name}{bid.contact_tel ? ` (${bid.contact_tel})` : ''}</dd>
              </div>
            )}
          </dl>
          {bid.ntce_url && (
            <div className="mt-4 pt-3 border-t border-slate-100">
              <a
                href={bid.ntce_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 hover:underline font-medium"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                나라장터 공고 바로가기
              </a>
            </div>
          )}
        </CardContent>
      </Card>

      {score && score.grade && score.breakdown && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-600" />수주 기회 점수
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="flex items-center gap-4 mb-4 p-3 bg-slate-50 rounded-lg">
              <div className={cn('flex h-14 w-14 items-center justify-center rounded-xl text-white font-bold text-2xl shadow-sm', gradeColor)}>
                {grade}
              </div>
              <div>
                <p className="text-3xl font-bold text-slate-900 tabular-nums">{score.score}<span className="text-lg font-normal text-slate-400 ml-0.5">점</span></p>
                {score.recommendation && <p className="text-xs text-slate-500 mt-0.5">{score.recommendation}</p>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(score.breakdown).map(([key, comp]) => (
                <div key={key} className="flex items-center justify-between rounded-lg bg-slate-50 border border-slate-100 px-3 py-2 text-xs">
                  <span className="text-slate-500">{key.replace('_', ' ')}</span>
                  <span className="font-semibold text-slate-800">{comp.pts}<span className="text-slate-400 font-normal">/{comp.max}</span></span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {bid.results && bid.results.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Trophy className="h-4 w-4 text-blue-600" />개찰 결과
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50 hover:bg-slate-50 border-b border-slate-200">
                  <TableHead className="text-xs text-slate-600 font-semibold">순위</TableHead>
                  <TableHead className="text-xs text-slate-600 font-semibold">업체명</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">투찰율</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">사정율</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bid.results.slice(0, 10).map((r) => (
                  <TableRow key={r.id} className={cn(
                    'border-b border-slate-100 last:border-0',
                    r.is_winner ? 'bg-emerald-50' : 'hover:bg-slate-50'
                  )}>
                    <TableCell className="text-xs text-slate-700">{r.rank}</TableCell>
                    <TableCell className="text-xs font-medium text-slate-800">
                      {r.is_winner && <Trophy className="inline mr-1 h-3 w-3 text-amber-500" />}
                      {r.competitor_name}
                    </TableCell>
                    <TableCell className="text-xs text-right font-mono text-slate-700">{fmtRate(r.bid_rate)}</TableCell>
                    <TableCell className="text-xs text-right font-mono text-slate-700">
                      {r.assessment_rate != null ? fmtRate(r.assessment_rate) : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── TabStrategy ──────────────────────────────────────────────────────────

function TabStrategy({ bidId, bid }: { bidId: number; bid: BidDetail }) {
  const { data: rec, isLoading } = useQuery<FinalRecommendResult>({
    queryKey: ['final-recommend', bidId],
    queryFn: () => bidsApi.finalRecommend(bidId),
  })
  const { data: winZones } = useQuery<ActualWinZonesResponse>({
    queryKey: ['actual-win-zones', bidId],
    queryFn: () => bidsApi.actualWinZones(bidId),
  })

  if (isLoading) return <Skeleton className="h-64 w-full" />
  if (!rec) return <div className="text-sm text-slate-500 p-4">AI 추천 데이터가 없습니다.</div>

  const strategyMeta: Record<string, { label: string; color: string; accent: string; iconColor: string }> = {
    balanced:     { label: '균형형',   color: 'border-blue-200 bg-blue-50/50',    accent: 'bg-blue-500',    iconColor: 'text-blue-600' },
    aggressive:   { label: '공격형',   color: 'border-orange-200 bg-orange-50/50', accent: 'bg-orange-500', iconColor: 'text-orange-600' },
    conservative: { label: '보수형',   color: 'border-emerald-200 bg-emerald-50/50', accent: 'bg-emerald-500', iconColor: 'text-emerald-600' },
    floor_safe:   { label: '하한안전', color: 'border-purple-200 bg-purple-50/50',  accent: 'bg-purple-500',  iconColor: 'text-purple-600' },
  }

  // balanced → aggressive → conservative → floor_safe 순 고정
  const STRATEGY_ORDER = ['balanced', 'aggressive', 'conservative', 'floor_safe'] as const
  const recommendedStrategyKey = STRATEGY_ORDER.find(
    (k) => rec.strategies[k] && Math.abs(rec.strategies[k].rate - rec.recommended_rate) < 0.00001
  ) ?? 'balanced'

  const floorBreached = rec.recommended_rate < rec.floor_rate

  const confidenceColor =
    rec.confidence === 'high' ? 'text-emerald-600 bg-emerald-50 border-emerald-200' :
    rec.confidence === 'medium' ? 'text-amber-600 bg-amber-50 border-amber-200' :
    'text-red-600 bg-red-50 border-red-200'

  const confidenceLabel =
    rec.confidence === 'high' ? '신뢰도 높음' :
    rec.confidence === 'medium' ? '신뢰도 중간' : '신뢰도 낮음'

  return (
    <div className="space-y-4">
      {floorBreached && (
        <div className="flex items-start gap-3 rounded-xl border-2 border-red-200 bg-red-50 px-4 py-3.5 text-sm text-red-700">
          <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0 text-red-500" />
          <div>
            <p className="font-semibold text-red-800 mb-0.5">낙찰하한율 미달 경고</p>
            <p className="text-red-600">
              권장 사정율 <strong>{fmtRate(rec.recommended_rate)}</strong>이 낙찰하한율{' '}
              <strong>{fmtRate(rec.floor_rate)}</strong> 미달입니다. 실격 위험이 있습니다.
            </p>
          </div>
        </div>
      )}

      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            최종 투찰 추천
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="flex items-end gap-6 mb-4">
            <div>
              <p className="text-xs text-slate-400 mb-1">추천 투찰율</p>
              <p className="text-4xl font-bold text-blue-600 tabular-nums">{fmtRate(rec.recommended_rate)}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">추천 금액</p>
              <p className="text-xl font-semibold text-slate-900 tabular-nums">₩{fmt(rec.recommended_amount)}원</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 mb-1">낙찰하한율</p>
              <p className="text-sm font-medium text-slate-500">{fmtRate(rec.floor_rate)}</p>
            </div>
            <div className="ml-auto text-right">
              <p className="text-xs text-slate-400 mb-1">신뢰도</p>
              <span className={cn('text-xs font-semibold px-2.5 py-1 rounded-full border', confidenceColor)}>
                {confidenceLabel}
              </span>
            </div>
          </div>
          {rec.signal && (
            <p className="text-xs text-slate-500 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">{rec.signal}</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        {STRATEGY_ORDER.map((key) => {
          const s = rec.strategies[key]
          if (!s) return null
          const isRec = key === recommendedStrategyKey
          const belowFloor = s.rate < rec.floor_rate
          const ev = s.win_prob * s.amount
          const meta = strategyMeta[key]
          return (
            <Card key={key} className={cn(
              'border-2 transition-all',
              meta.color,
              isRec ? 'ring-2 ring-offset-2 ring-blue-400 shadow-md' : 'shadow-sm',
              belowFloor ? 'opacity-50' : ''
            )}>
              <CardContent className="pt-3.5 pb-3.5">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={cn('w-2 h-2 rounded-full', meta.accent)} />
                    <span className="text-sm font-semibold text-slate-800">{meta.label}</span>
                  </div>
                  <div className="flex gap-1">
                    {isRec && <Badge className="text-[10px] h-5 bg-blue-500 text-white">추천</Badge>}
                    {belowFloor && <Badge className="text-[10px] h-5 bg-red-500 text-white">실격위험</Badge>}
                  </div>
                </div>
                <p className="text-2xl font-bold text-slate-900 tabular-nums">{fmtRate(s.rate)}</p>
                <p className="text-xs text-slate-500 mt-0.5">₩{fmt(s.amount)}원</p>
                <div className="mt-2.5 flex gap-3 text-xs pt-2 border-t border-slate-200/60">
                  <div>
                    <span className="text-slate-400">승률 </span>
                    <strong className={cn('font-semibold', meta.iconColor)}>
                      {s.win_prob > 0 ? fmtPct(s.win_prob) : '-'}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">기댓값 </span>
                    <strong className="text-slate-700">{s.win_prob > 0 ? `₩${fmt(ev)}원` : '-'}</strong>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Brain className="h-4 w-4 text-blue-600" />분석 근거
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
              <p className="text-slate-400 mb-1">사정율 통계</p>
              <p className="font-semibold text-slate-900">평균 {fmtRate(rec.evidence.srate_stats.mean)}</p>
              <p className="text-slate-500 mt-0.5">
                {rec.evidence.srate_stats.sample_count}건 | {rec.evidence.srate_stats.trend_direction}
              </p>
            </div>
            {rec.evidence.prism_top && (
              <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                <p className="text-slate-400 mb-1">PRISM 최고확률</p>
                <p className="font-semibold text-slate-900">{fmtRate(rec.evidence.prism_top.rate)}</p>
                <p className="text-slate-500 mt-0.5">확률 {fmtPct(rec.evidence.prism_top.probability)}</p>
              </div>
            )}
            {rec.evidence.yega_top && (
              <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                <p className="text-slate-400 mb-1">예가 최고확률</p>
                <p className="font-semibold text-slate-900">{fmtRate(rec.evidence.yega_top.rate)}</p>
                <p className="text-slate-500 mt-0.5">확률 {fmtPct(rec.evidence.yega_top.probability)}</p>
              </div>
            )}
            <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
              <p className="text-slate-400 mb-1">개인 편향 보정</p>
              <p className="font-semibold text-slate-900">{rec.evidence.personal_bias.applied ? '적용됨' : '미적용'}</p>
              <p className="text-slate-500 mt-0.5">{fmtRate(rec.evidence.personal_bias.rate_diff_mean)} 차이</p>
            </div>
            <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
              <p className="text-slate-400 mb-1">낙찰하한율</p>
              <p className="font-semibold text-slate-900">{fmtRate(rec.floor_rate)}</p>
              <p className="text-slate-500 mt-0.5">₩{fmt(bid.base_amount * rec.floor_rate)}원</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {winZones && winZones.sample_count > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-blue-600" />실제 낙찰 구간 분포
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="flex gap-4 text-xs text-slate-500 mb-3">
              <span>표본 <strong className="text-slate-700">{winZones.sample_count}건</strong></span>
              <span>평균 낙찰율 <strong className="text-slate-700">{fmtRate(winZones.mean_winner_rate)}</strong></span>
              {winZones.agency_name && <span className="text-slate-400">{winZones.agency_name}</span>}
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={winZones.zones} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="range_lo" tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} tick={{ fontSize: 9, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} />
                <Tooltip
                  formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, '확률']}
                  contentStyle={{ fontSize: 11, border: '1px solid #e2e8f0', borderRadius: 8 }}
                />
                <Bar dataKey="probability" fill="#3b82f6" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <div className="flex gap-2">
        <Button variant="outline" size="sm" asChild className="border-slate-200 text-slate-700 hover:bg-slate-50 hover:text-blue-600">
          <Link to={`/bids/${bidId}/final-recommend`}>
            <Target className="h-3.5 w-3.5 mr-1.5" /> 상세 추천 페이지
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild className="border-slate-200 text-slate-700 hover:bg-slate-50 hover:text-blue-600">
          <Link to={`/bids/${bidId}/joint-sim`}>
            <Handshake className="h-3.5 w-3.5 mr-1.5" /> 공동도급 시뮬레이션
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild className="border-slate-200 text-slate-700 hover:bg-slate-50 hover:text-blue-600">
          <Link to={`/bids/${bidId}/rival-radar`}>
            <Radar className="h-3.5 w-3.5 mr-1.5" /> 경쟁사 레이더
          </Link>
        </Button>
      </div>
    </div>
  )
}

// ── TabQualification ─────────────────────────────────────────────────────

function TabQualification({ bid }: { bid: BidDetail }) {
  const { data: range, isLoading } = useQuery<BidRangeResponse>({
    queryKey: ['bid-range', bid.id],
    queryFn: () => recommendApi.bidRange({ base_amount: bid.base_amount }),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />

  const floors = [
    { label: 'A값', value: range?.a_value != null ? `${fmt(range.a_value)}원` : bid.a_value != null ? `${fmt(bid.a_value)}원` : '-' },
    { label: '낙찰하한가', value: range?.floor_price != null ? `${fmt(range.floor_price)}원` : '-' },
    { label: '낙찰하한율', value: range?.floor_rate != null ? fmtRate(range.floor_rate) : '-' },
    { label: '사정율 중심', value: range?.srate_center != null ? fmtRate(range.srate_center) : '-' },
  ]

  return (
    <div className="space-y-4">
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Shield className="h-4 w-4 text-blue-600" />낙찰하한가 · A값
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-3">
            {floors.map(({ label, value }) => (
              <div key={label} className="bg-slate-50 border border-slate-100 rounded-lg p-3.5">
                <p className="text-xs text-slate-400 mb-1">{label}</p>
                <p className="text-base font-semibold text-slate-900">{value}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {range?.srate_range && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-blue-600" />사정율 분포 (업종 기준)
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="grid grid-cols-5 gap-2 text-center text-xs">
              {(
                [
                  { label: 'P10', value: range.srate_range.p10 },
                  { label: 'P25', value: range.srate_range.p25 },
                  { label: 'P50', value: range.srate_range.p50 },
                  { label: 'P75', value: range.srate_range.p75 },
                  { label: 'P90', value: range.srate_range.p90 },
                ] as { label: string; value: number }[]
              ).map(({ label, value }) => (
                <div key={label} className={cn(
                  'rounded-lg p-2.5 border',
                  label === 'P50' ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-100'
                )}>
                  <p className={cn('mb-1', label === 'P50' ? 'text-blue-500 font-semibold' : 'text-slate-400')}>{label}</p>
                  <p className={cn('font-semibold', label === 'P50' ? 'text-blue-700' : 'text-slate-700')}>{fmtRate(value)}</p>
                </div>
              ))}
            </div>
            {range.srate_source && (
              <p className="text-[10px] text-slate-400 mt-3">
                데이터 출처: {range.srate_source}
                {range.inpo21c_n != null ? ` (${range.inpo21c_n}건)` : ''}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── TabCompetitors ───────────────────────────────────────────────────────

function TabCompetitors({ bidId }: { bidId: number }) {
  const { data: radar, isLoading } = useQuery<RivalRadarResponse>({
    queryKey: ['rival-radar', bidId],
    queryFn: () => bidsApi.rivalRadar(bidId, 15),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />
  if (!radar) return <div className="text-sm text-slate-500 p-4">경쟁사 데이터가 없습니다.</div>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-slate-400 mb-1">총 참여업체</p>
            <p className="text-2xl font-bold text-slate-900 tabular-nums">{radar.total_participants}</p>
          </CardContent>
        </Card>
        <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-emerald-500" />
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-slate-400 mb-1">낙찰업체</p>
            <p className="text-sm font-semibold text-slate-900 truncate">{radar.winner_company ?? '-'}</p>
          </CardContent>
        </Card>
        <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-amber-500" />
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-slate-400 mb-1">낙찰율</p>
            <p className="text-xl font-bold text-slate-900 tabular-nums">
              {radar.winner_rate != null ? fmtRate(radar.winner_rate) : '-'}
            </p>
          </CardContent>
        </Card>
      </div>

      {radar.rivals.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Users className="h-4 w-4 text-blue-600" />경쟁사 투찰 이력
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50 hover:bg-slate-50 border-b border-slate-200">
                  <TableHead className="text-xs text-slate-600 font-semibold">업체명</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">공동입찰</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">평균 투찰율</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">낙찰 횟수</TableHead>
                  <TableHead className="text-xs text-slate-600 font-semibold">위협도</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {radar.rivals.map((r) => {
                  const winRate = r.co_bid_count > 0 ? r.win_count / r.co_bid_count : 0
                  const risk = winRate > 0.3 ? 'HIGH' : winRate > 0.15 ? 'MEDIUM' : 'LOW'
                  return (
                    <TableRow key={r.company_name} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                      <TableCell className="text-xs font-medium text-slate-800">{r.company_name}</TableCell>
                      <TableCell className="text-xs text-right text-slate-600">{r.co_bid_count}건</TableCell>
                      <TableCell className="text-xs text-right font-mono text-slate-700">
                        {r.avg_bid_rate != null ? fmtRate(r.avg_bid_rate) : '-'}
                      </TableCell>
                      <TableCell className="text-xs text-right text-slate-600">{r.win_count}건</TableCell>
                      <TableCell className="text-xs">
                        <Badge
                          variant="outline"
                          className={cn('text-[10px] font-semibold',
                            risk === 'HIGH' ? 'border-red-200 text-red-600 bg-red-50' :
                            risk === 'MEDIUM' ? 'border-amber-200 text-amber-600 bg-amber-50' :
                            'border-emerald-200 text-emerald-600 bg-emerald-50',
                          )}
                        >
                          {risk}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {radar.current_participants.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Trophy className="h-4 w-4 text-blue-600" />개찰 참여자 목록
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50 hover:bg-slate-50 border-b border-slate-200">
                  <TableHead className="text-xs text-slate-600 font-semibold">순위</TableHead>
                  <TableHead className="text-xs text-slate-600 font-semibold">업체명</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">투찰율</TableHead>
                  <TableHead className="text-xs text-slate-600 font-semibold">낙찰</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {radar.current_participants.map((p, i) => (
                  <TableRow key={i} className={cn(
                    'border-b border-slate-100 last:border-0',
                    p.is_winner ? 'bg-emerald-50' : 'hover:bg-slate-50'
                  )}>
                    <TableCell className="text-xs text-slate-700">{p.rank}</TableCell>
                    <TableCell className="text-xs font-medium text-slate-800">{p.company_name}</TableCell>
                    <TableCell className="text-xs text-right font-mono text-slate-700">
                      {p.bid_rate != null ? fmtRate(p.bid_rate) : '-'}
                    </TableCell>
                    <TableCell className="text-xs">
                      {p.is_winner && <Trophy className="h-3.5 w-3.5 text-amber-500" />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── TabAgency ────────────────────────────────────────────────────────────

function TabAgency({ agencyId, agencyName }: { agencyId: number | undefined; agencyName: string }) {
  const { data: histogram, isLoading: histLoading } = useQuery<SrateHistogramResponse>({
    queryKey: ['agency-srate-histogram', agencyId],
    queryFn: () => agenciesApi.srateHistogram(agencyId!),
    enabled: agencyId != null,
  })
  const { data: recentResults, isLoading: recLoading } = useQuery<AgencyRecentResultsResponse>({
    queryKey: ['agency-recent-results', agencyId],
    queryFn: () => agenciesApi.recentResults(agencyId!, 20),
    enabled: agencyId != null,
  })

  if (agencyId == null) {
    return <div className="text-sm text-slate-500 p-4">발주처 ID를 찾을 수 없습니다.</div>
  }

  return (
    <div className="space-y-4">
      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-blue-600" />{agencyName} 사정율 분포
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {histLoading ? (
            <Skeleton className="h-36 w-full" />
          ) : histogram && histogram.bins.length > 0 ? (
            <>
              <div className="flex gap-4 text-xs text-slate-500 mb-3">
                <span>{histogram.months}개월</span>
                <span className="font-medium text-slate-700">{histogram.sample_count}건</span>
                {histogram.mean != null && <span>평균 <strong className="text-slate-900">{fmtRate(histogram.mean)}</strong></span>}
                {histogram.percentiles?.p50 != null && <span>중앙값 <strong className="text-slate-900">{fmtRate(histogram.percentiles.p50)}</strong></span>}
              </div>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={histogram.bins} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="range_lo"
                    tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                  />
                  <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} />
                  <Tooltip
                    formatter={(v: number) => [v, '건수']}
                    labelFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
                    contentStyle={{ fontSize: 11, border: '1px solid #e2e8f0', borderRadius: 8 }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" fillOpacity={0.75} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </>
          ) : (
            <p className="text-sm text-slate-400">히스토그램 데이터가 없습니다.</p>
          )}
        </CardContent>
      </Card>

      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Trophy className="h-4 w-4 text-blue-600" />최근 낙찰 이력
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {recLoading ? (
            <div className="p-4"><Skeleton className="h-32 w-full" /></div>
          ) : recentResults && recentResults.items.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50 hover:bg-slate-50 border-b border-slate-200">
                  <TableHead className="text-xs text-slate-600 font-semibold">공고명</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">기초금액</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">사정율</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">개찰일</TableHead>
                  <TableHead className="text-xs text-right text-slate-600 font-semibold">참여사</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentResults.items.map((r) => (
                  <TableRow key={r.bid_id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                    <TableCell className="text-xs max-w-[200px] truncate">
                      <Link to={`/bids/${r.bid_id}`} className="text-blue-600 hover:text-blue-700 hover:underline font-medium">
                        {r.title}
                      </Link>
                    </TableCell>
                    <TableCell className="text-xs text-right font-mono text-slate-700">₩{fmt(r.base_amount)}원</TableCell>
                    <TableCell className="text-xs text-right font-mono font-semibold text-slate-900">
                      {r.assessment_rate != null ? fmtRate(r.assessment_rate) : '-'}
                    </TableCell>
                    <TableCell className="text-xs text-right text-slate-500">{fmtDate(r.bid_open_date)}</TableCell>
                    <TableCell className="text-xs text-right text-slate-600">{r.competitor_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-slate-400 p-4">이력 데이터가 없습니다.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── TabYega ──────────────────────────────────────────────────────────────

function TabYega({ bid }: { bid: BidDetail }) {
  const { data: yega, isLoading } = useQuery<YegaFrequencyResult>({
    queryKey: ['yega-frequency', bid.id],
    queryFn: () =>
      recommendApi.yegaFrequency(bid.base_amount, bid.a_value ?? undefined),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />
  if (!yega) return <div className="text-sm text-slate-500 p-4">예가 분석 데이터가 없습니다.</div>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-slate-400" />
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-slate-400 mb-1">총 조합 수</p>
            <p className="text-xl font-bold text-slate-900 tabular-nums">{fmt(yega.total_combinations)}</p>
          </CardContent>
        </Card>
        <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-slate-400 mb-1">추천 투찰율</p>
            <p className="text-xl font-bold text-blue-600 tabular-nums">{fmtRate(yega.recommended_rate)}</p>
          </CardContent>
        </Card>
        <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-emerald-500" />
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-slate-400 mb-1">낙찰하한율</p>
            <p className="text-xl font-bold text-emerald-700 tabular-nums">{fmtRate(yega.floor_rate)}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-white border-slate-200 shadow-sm">
        <CardHeader className="border-b border-slate-100 pb-3">
          <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-blue-600" />상위 10개 예가 구간
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50 hover:bg-slate-50 border-b border-slate-200">
                <TableHead className="text-xs text-slate-600 font-semibold">순위</TableHead>
                <TableHead className="text-xs text-right text-slate-600 font-semibold">예가율</TableHead>
                <TableHead className="text-xs text-right text-slate-600 font-semibold">빈도</TableHead>
                <TableHead className="text-xs text-right text-slate-600 font-semibold">확률</TableHead>
                <TableHead className="text-xs text-right text-slate-600 font-semibold">누적확률</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {yega.top10.map((row, i) => (
                <TableRow key={i} className={cn(
                  'border-b border-slate-100 last:border-0 transition-colors',
                  i === 0 ? 'bg-blue-50' : 'hover:bg-slate-50'
                )}>
                  <TableCell className="text-xs font-semibold text-slate-700">{i + 1}</TableCell>
                  <TableCell className="text-xs text-right font-mono font-medium text-slate-900">{row.rate_pct.toFixed(3)}%</TableCell>
                  <TableCell className="text-xs text-right text-slate-600">{row.count}</TableCell>
                  <TableCell className="text-xs text-right font-semibold text-slate-900">{fmtPct(row.probability)}</TableCell>
                  <TableCell className="text-xs text-right text-slate-500">{fmtPct(row.cumulative_prob)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {yega.chart_bins.length > 0 && (
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-blue-600" />예가 분포 차트
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={yega.chart_bins} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="rate_pct" tickFormatter={(v: number) => `${v.toFixed(1)}%`} tick={{ fontSize: 9, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} />
                <Tooltip
                  formatter={(v: number) => [v, '건수']}
                  labelFormatter={(v: number) => `${v.toFixed(3)}%`}
                  contentStyle={{ fontSize: 11, border: '1px solid #e2e8f0', borderRadius: 8 }}
                />
                <Bar dataKey="count" fill="#3b82f6" fillOpacity={0.75} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────

export default function BidDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const bidId = Number(id)

  const { data: bid, isLoading } = useQuery<BidDetail>({
    queryKey: ['bid', id],
    queryFn: () => bidsApi.detail(bidId),
    enabled: !!id,
  })

  const { data: score } = useQuery<OpportunityScore>({
    queryKey: ['opportunity-score', id],
    queryFn: () => bidsApi.opportunityScore(bidId),
    enabled: !!id,
  })

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 5 * 60 * 1000,
  })

  const agencyId = bid && meta
    ? meta.agencies.find((a) => a.name === bid.agency_name)?.id
    : undefined

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (!bid) {
    return (
      <div className="p-6">
        <p className="text-sm text-slate-500">공고를 찾을 수 없습니다.</p>
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mt-2 text-slate-600">
          <ArrowLeft className="mr-1 h-3.5 w-3.5" /> 돌아가기
        </Button>
      </div>
    )
  }

  const statusConfig =
    bid.status === 'open'
      ? { dot: 'bg-emerald-500', label: '진행중', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200' }
      : bid.status === 'closed'
      ? { dot: 'bg-slate-400', label: '완료', badge: 'bg-slate-100 text-slate-600 border-slate-200' }
      : { dot: 'bg-amber-400', label: bid.status, badge: 'bg-amber-50 text-amber-700 border-amber-200' }

  const gradeConfig =
    score?.grade === 'A' ? 'bg-emerald-500 text-white' :
    score?.grade === 'B' ? 'bg-blue-500 text-white' :
    score?.grade === 'C' ? 'bg-amber-400 text-white' : 'bg-red-500 text-white'

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-start gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 h-8 w-8 text-slate-600 hover:bg-slate-100 mt-0.5"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={cn('inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full border', statusConfig.badge)}>
                <span className={cn('inline-block h-1.5 w-1.5 rounded-full', statusConfig.dot)} />
                {statusConfig.label}
              </span>
              {score?.grade && (
                <span className={cn('inline-flex items-center justify-center h-5 w-5 rounded-md text-xs font-bold', gradeConfig)}>
                  {score.grade}
                </span>
              )}
              {bid.source === 'g2b' && (
                <Badge variant="info" className="text-[10px] px-1.5 py-0">G2B</Badge>
              )}
            </div>
            <h1 className="text-base font-bold leading-tight line-clamp-2 text-slate-900">{bid.title}</h1>
            <div className="flex items-center gap-4 mt-1.5 text-xs text-slate-500">
              <span className="flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5 text-slate-400" />{bid.agency_name}
              </span>
              <span className="font-medium text-slate-700">₩{fmt(bid.base_amount)}원</span>
              {bid.bid_open_date && (
                <span>개찰 <strong className="text-slate-700">{fmtDate(bid.bid_open_date)}</strong></span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <Tabs defaultValue="info" className="h-full">
          <div className="bg-white border-b border-slate-200 px-6 pt-3">
            <TabsList className="bg-slate-100 border border-slate-200 h-9 gap-0">
              <TabsTrigger value="info" className="text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600">
                공고정보
              </TabsTrigger>
              <TabsTrigger value="strategy" className="text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600">
                AI전략
              </TabsTrigger>
              <TabsTrigger value="qualification" className="text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600">
                적격심사
              </TabsTrigger>
              <TabsTrigger value="competitors" className="text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600">
                경쟁사
              </TabsTrigger>
              <TabsTrigger value="agency" className="text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600">
                발주처분석
              </TabsTrigger>
              <TabsTrigger value="yega" className="text-xs data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600">
                예가분석
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="px-6 pb-6 pt-5">
            <TabsContent value="info" className="mt-0">
              <TabInfo bid={bid} score={score} />
            </TabsContent>
            <TabsContent value="strategy" className="mt-0">
              <TabStrategy bidId={bidId} bid={bid} />
            </TabsContent>
            <TabsContent value="qualification" className="mt-0">
              <TabQualification bid={bid} />
            </TabsContent>
            <TabsContent value="competitors" className="mt-0">
              <TabCompetitors bidId={bidId} />
            </TabsContent>
            <TabsContent value="agency" className="mt-0">
              <TabAgency agencyId={agencyId} agencyName={bid.agency_name} />
            </TabsContent>
            <TabsContent value="yega" className="mt-0">
              <TabYega bid={bid} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}
