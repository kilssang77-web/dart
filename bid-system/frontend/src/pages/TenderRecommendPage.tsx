import { useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Target, AlertTriangle,
  TrendingUp, TrendingDown, Minus, CheckCircle2, XCircle, Printer, Loader2,
  Building2, CalendarDays, Users, Brain,
} from 'lucide-react'
import { bidsApi } from '@/api'
import type { BidDetail, FinalRecommendResult } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const CONFIDENCE_LABEL: Record<string, { label: string; cls: string }> = {
  high:   { label: '신뢰도 높음',  cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  medium: { label: '신뢰도 중간',  cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  low:    { label: '신뢰도 낮음',  cls: 'bg-red-50 text-red-700 border-red-200' },
}

const STRATEGY_META: Record<string, {
  label: string
  desc: string
  primary?: boolean
  accent: string
  badgeColor: string
}> = {
  balanced:     { label: '균형형',   desc: '표준 추천 — 확률과 안전성 균형', primary: true,  accent: 'bg-blue-500',    badgeColor: 'bg-blue-50 text-blue-700 border-blue-200' },
  aggressive:   { label: '공격형',   desc: '낙찰률 최우선 — 낮은 금액으로 도전',              accent: 'bg-orange-500',  badgeColor: 'bg-orange-50 text-orange-700 border-orange-200' },
  conservative: { label: '보수형',   desc: '안전 마진 확보 — 높은 사정율로 여유',             accent: 'bg-emerald-500', badgeColor: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  floor_safe:   { label: '하한안전', desc: '하한선 바로 위 — 실격 방지 극보수',               accent: 'bg-purple-500',  badgeColor: 'bg-purple-50 text-purple-700 border-purple-200' },
}

function TrendIcon({ dir }: { dir: string }) {
  if (dir === 'up')   return <TrendingUp   className="h-4 w-4 text-red-500 inline" />
  if (dir === 'down') return <TrendingDown  className="h-4 w-4 text-blue-500 inline" />
  return <Minus className="h-4 w-4 text-slate-500 inline" />
}

function fmtRate(r: number) { return (r * 100).toFixed(4) + '%' }
function fmtAmt(v: number)  { return (v / 1e8).toFixed(4) + '억원' }
function fmtAmtKo(v: number) { return v.toLocaleString('ko-KR') + '원' }

export default function TenderRecommendPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const printRef = useRef<HTMLDivElement>(null)
  const [printing, setPrinting] = useState(false)

  const handlePdf = async () => {
    if (!printRef.current) return
    setPrinting(true)
    try {
      const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
        import('jspdf'),
        import('html2canvas'),
      ])
      const canvas = await html2canvas(printRef.current, { scale: 2, useCORS: true })
      const imgData = canvas.toDataURL('image/png')
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()
      const margin = 10
      const imgW = pageW - margin * 2
      const imgH = (canvas.height * imgW) / canvas.width
      let offset = 0
      let page = 0
      while (offset < imgH) {
        if (page > 0) pdf.addPage()
        pdf.addImage(imgData, 'PNG', margin, margin - offset, imgW, imgH)
        offset += pageH - margin * 2
        page++
      }
      pdf.save(`투찰추천_${id}.pdf`)
    } finally {
      setPrinting(false)
    }
  }

  const { data: bid, isLoading: bidLoading } = useQuery<BidDetail>({
    queryKey: ['bid', id],
    queryFn:  () => bidsApi.detail(Number(id)),
    enabled:  !!id,
    staleTime: 300_000,
  })

  const { data: rec, isLoading: recLoading, error: recError } = useQuery<FinalRecommendResult>({
    queryKey: ['final-recommend', id],
    queryFn:  () => bidsApi.finalRecommend(Number(id)),
    enabled:  !!id,
    staleTime: 60_000,
  })

  const isLoading = bidLoading || recLoading

  if (isLoading) return (
    <div className="min-h-full bg-slate-50">
      <div className="p-6 space-y-4 max-w-3xl mx-auto">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-60 w-full" />
      </div>
    </div>
  )

  if (recError) return (
    <div className="min-h-full bg-slate-50 p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-2 p-4 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        추천 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
      </div>
    </div>
  )

  if (!rec || !bid) return null

  const floorBreached = rec.recommended_rate < rec.floor_rate
  const conf = CONFIDENCE_LABEL[rec.confidence] ?? CONFIDENCE_LABEL.low

  const strategyOrder: Array<keyof typeof rec.strategies> = [
    'balanced', 'conservative', 'aggressive', 'floor_safe',
  ]

  const fmtDate = (v?: string | null) =>
    v ? new Date(v).toLocaleDateString('ko-KR') : '-'

  return (
    <div className="min-h-full bg-slate-50">
      {/* Sticky Page Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-3xl mx-auto">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="gap-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            >
              <ArrowLeft className="h-4 w-4" /> 돌아가기
            </Button>
            <span className="text-slate-300">/</span>
            <span className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
              <Target className="h-4 w-4 text-blue-600" />
              투찰가 종합 분석
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handlePdf}
            disabled={printing}
            className="gap-1.5 border-slate-200 text-slate-700 hover:bg-slate-50 hover:text-blue-600"
          >
            {printing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
            PDF 출력
          </Button>
        </div>
      </div>

      <div className="px-6 py-5 space-y-4 max-w-3xl mx-auto">
        <div ref={printRef} className="space-y-4">

        {/* 공고 요약 카드 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-slate-500 flex items-center gap-1">
                  <Building2 className="h-3 w-3" />{bid.agency_name}
                </p>
                <p className="font-semibold text-slate-900 text-sm leading-snug mt-1 line-clamp-2">{bid.title}</p>
                <div className="mt-2.5 flex flex-wrap gap-4 text-xs">
                  <span className="flex items-center gap-1 text-slate-500">
                    기초금액
                    <strong className="text-slate-900 font-semibold">{(bid.base_amount / 1e8).toFixed(1)}억원</strong>
                  </span>
                  <span className="flex items-center gap-1 text-slate-500">
                    <CalendarDays className="h-3 w-3" />개찰일
                    <strong className="text-slate-900 font-semibold">{fmtDate(bid.bid_open_date)}</strong>
                  </span>
                  <span className="flex items-center gap-1 text-slate-500">
                    <Users className="h-3 w-3" />경쟁사
                    <strong className="text-slate-900 font-semibold">{bid.competitor_count}개사</strong>
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 낙찰하한 경고 배너 */}
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

        {/* 핵심 추천 카드 */}
        <Card className="bg-gradient-to-br from-blue-600 to-blue-700 border-blue-600 shadow-lg">
          <CardContent className="pt-6 pb-6 text-center space-y-2">
            <p className="text-xs text-blue-200 uppercase tracking-widest font-medium">권장 사정율</p>
            <p className="text-5xl font-bold text-white tabular-nums tracking-tight">
              {fmtRate(rec.recommended_rate)}
            </p>
            <p className="text-xl font-semibold text-blue-100 tabular-nums">
              {fmtAmtKo(rec.recommended_amount)}
            </p>
            <div className="flex items-center justify-center gap-2 pt-2">
              <span className={cn('text-xs px-2.5 py-1 rounded-full font-medium border', conf.cls)}>
                {conf.label}
              </span>
              <span className="text-xs text-blue-200">
                표본 {rec.evidence.srate_stats.sample_count.toLocaleString()}건
              </span>
            </div>
            {rec.signal && (
              <p className="text-xs text-blue-200 pt-1 max-w-sm mx-auto leading-relaxed">{rec.signal}</p>
            )}
          </CardContent>
        </Card>

        {/* 4전략 비교표 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Target className="h-4 w-4 text-blue-600" />전략별 비교
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-4 py-2.5 text-left text-sm font-semibold text-slate-600">전략</th>
                    <th className="px-4 py-2.5 text-right text-sm font-semibold text-slate-600">사정율</th>
                    <th className="px-4 py-2.5 text-right text-sm font-semibold text-slate-600">투찰금액</th>
                    <th className="px-4 py-2.5 text-right text-sm font-semibold text-slate-600">낙찰확률</th>
                    <th className="px-4 py-2.5 text-center text-sm font-semibold text-slate-600">적합</th>
                  </tr>
                </thead>
                <tbody>
                  {strategyOrder.map((key) => {
                    const s  = rec.strategies[key]
                    const m  = STRATEGY_META[key]
                    const ok = s.rate >= rec.floor_rate
                    return (
                      <tr
                        key={key}
                        className={cn(
                          'border-b border-slate-100 last:border-0 transition-colors',
                          m.primary ? 'bg-blue-50/60' : 'hover:bg-slate-50',
                        )}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className={cn('w-2 h-2 rounded-full shrink-0', m.accent)} />
                            <div>
                              <p className="font-semibold text-slate-900 text-sm">{m.label}</p>
                              <p className="text-xs text-slate-500 font-normal mt-0.5">{m.desc}</p>
                            </div>
                          </div>
                          {m.primary && (
                            <Badge className="mt-1 ml-4 text-xs h-4 bg-blue-500 text-white">추천</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono tabular-nums font-semibold text-slate-900">
                          {fmtRate(s.rate)}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-sm text-slate-600">
                          {fmtAmt(s.amount)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {s.win_prob > 0 ? (
                            <span className={cn(
                              'inline-block px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums',
                              s.win_prob > 0.5 ? 'bg-emerald-50 text-emerald-700' :
                              s.win_prob > 0.3 ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'
                            )}>
                              {(s.win_prob * 100).toFixed(1)}%
                            </span>
                          ) : '-'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {ok
                            ? <CheckCircle2 className="h-4 w-4 text-emerald-500 mx-auto" />
                            : <XCircle      className="h-4 w-4 text-red-400 mx-auto"   />
                          }
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="px-4 pb-3 pt-2 bg-slate-50/50 border-t border-slate-100">
              <p className="text-xs text-slate-500">
                낙찰하한율 <strong className="text-slate-600">{fmtRate(rec.floor_rate)}</strong> 이상만 유효 (✓)
              </p>
            </div>
          </CardContent>
        </Card>

        {/* 근거 패널 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-3">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Brain className="h-4 w-4 text-blue-600" />분석 근거
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-1 pb-1">
            {/* 사정율 통계 */}
            <EvidenceRow
              label="사정율 통계"
              value={fmtRate(rec.evidence.srate_stats.mean)}
              sub={`${rec.evidence.srate_stats.sample_count.toLocaleString()}건 표본`}
              extra={
                <span className="flex items-center gap-1 text-xs text-slate-500">
                  트렌드 <TrendIcon dir={rec.evidence.srate_stats.trend_direction} />
                  {rec.evidence.srate_stats.trend_direction === 'up'   && '상승'}
                  {rec.evidence.srate_stats.trend_direction === 'down' && '하락'}
                  {rec.evidence.srate_stats.trend_direction === 'stable' && '안정'}
                </span>
              }
              match={rec.evidence.prism_top
                ? Math.abs(rec.evidence.srate_stats.mean - rec.evidence.prism_top.rate) < 0.002
                : true}
            />

            {/* 프리즘 top1 */}
            {rec.evidence.prism_top ? (
              <EvidenceRow
                label="프리즘 최빈 구간"
                value={fmtRate(rec.evidence.prism_top.rate)}
                sub={`낙찰확률 ${rec.evidence.prism_top.probability.toFixed(2)}%`}
                match={Math.abs(rec.evidence.prism_top.rate - rec.recommended_rate) < 0.003}
              />
            ) : (
              <EvidenceRow label="프리즘" value="-" sub="데이터 부족" match={null} />
            )}

            {/* 예가 top1 */}
            {rec.evidence.yega_top ? (
              <EvidenceRow
                label="예가 최빈 구간"
                value={fmtRate(rec.evidence.yega_top.rate)}
                sub={`빈도 ${rec.evidence.yega_top.probability.toFixed(2)}%`}
                match={Math.abs(rec.evidence.yega_top.rate - rec.recommended_rate) < 0.003}
              />
            ) : (
              <EvidenceRow label="예가 분석" value="-" sub="데이터 부족" match={null} />
            )}

            {/* 개인화 편향 */}
            <EvidenceRow
              label="개인 편향 보정"
              value={rec.evidence.personal_bias.applied
                ? (rec.evidence.personal_bias.rate_diff_mean >= 0 ? '+' : '') +
                  (rec.evidence.personal_bias.rate_diff_mean * 100).toFixed(2) + '%p'
                : '미적용'}
              sub={rec.evidence.personal_bias.applied
                ? '투찰이력 기반 보정 반영됨'
                : '이력 부족 (투찰 기록 쌓이면 정확도 향상)'}
              match={null}
            />
          </CardContent>
        </Card>

        </div>{/* /printRef */}
      </div>
    </div>
  )
}

interface EvidenceRowProps {
  label: string
  value: string
  sub:   string
  extra?: React.ReactNode
  match: boolean | null
}

function EvidenceRow({ label, value, sub, extra, match }: EvidenceRowProps) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
      <div>
        <p className="text-sm font-medium text-slate-800">{label}</p>
        <p className="text-xs text-slate-500 mt-0.5">{sub}</p>
        {extra && <div className="mt-1">{extra}</div>}
      </div>
      <div className="text-right flex items-center gap-2">
        <p className="font-mono font-semibold tabular-nums text-slate-900">{value}</p>
        {match === true  && (
          <Badge variant="outline" className="text-xs text-emerald-700 border-emerald-200 bg-emerald-50 px-1.5">수렴</Badge>
        )}
        {match === false && (
          <Badge variant="outline" className="text-xs text-orange-600 border-orange-200 bg-orange-50 px-1.5">괴리</Badge>
        )}
      </div>
    </div>
  )
}
