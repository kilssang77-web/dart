import { useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Target, AlertTriangle,
  TrendingUp, TrendingDown, Minus, CheckCircle2, XCircle, Printer, Loader2,
} from 'lucide-react'
import { bidsApi } from '@/api'
import type { BidDetail, FinalRecommendResult } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const CONFIDENCE_LABEL: Record<string, { label: string; cls: string }> = {
  high:   { label: '신뢰도 높음',  cls: 'bg-green-100 text-green-800' },
  medium: { label: '신뢰도 중간',  cls: 'bg-yellow-100 text-yellow-800' },
  low:    { label: '신뢰도 낮음',  cls: 'bg-red-100 text-red-800' },
}

const STRATEGY_META: Record<string, { label: string; desc: string; primary?: boolean }> = {
  balanced:     { label: '균형형',   desc: '표준 추천 — 확률과 안전성 균형', primary: true },
  aggressive:   { label: '공격형',   desc: '낙찰률 최우선 — 낮은 금액으로 도전' },
  conservative: { label: '보수형',   desc: '안전 마진 확보 — 높은 사정율로 여유' },
  floor_safe:   { label: '하한안전', desc: '하한선 바로 위 — 실격 방지 극보수' },
}

function TrendIcon({ dir }: { dir: string }) {
  if (dir === 'up')   return <TrendingUp   className="h-4 w-4 text-red-500 inline" />
  if (dir === 'down') return <TrendingDown  className="h-4 w-4 text-blue-500 inline" />
  return <Minus className="h-4 w-4 text-muted-foreground inline" />
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
    <div className="p-6 space-y-4 max-w-3xl mx-auto">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-60 w-full" />
    </div>
  )

  if (recError) return (
    <div className="p-6 text-destructive max-w-3xl mx-auto">
      추천 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
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
    <div className="p-6 space-y-5 max-w-3xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" /> 돌아가기
          </Button>
          <span className="text-muted-foreground text-sm">/</span>
          <span className="text-sm font-medium flex items-center gap-1.5">
            <Target className="h-4 w-4 text-primary" />
            투찰가 종합 분석
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={handlePdf} disabled={printing} className="gap-1.5">
          {printing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
          PDF 출력
        </Button>
      </div>

      <div ref={printRef}>

      {/* 공고 요약 */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <p className="text-xs text-muted-foreground">{bid.agency_name}</p>
          <p className="font-semibold text-sm leading-snug mt-0.5 line-clamp-2">{bid.title}</p>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>기초금액 <strong className="text-foreground">{(bid.base_amount / 1e8).toFixed(1)}억원</strong></span>
            <span>개찰일 <strong className="text-foreground">{fmtDate(bid.bid_open_date)}</strong></span>
            <span>경쟁사 <strong className="text-foreground">{bid.competitor_count}개사</strong></span>
          </div>
        </CardContent>
      </Card>

      {/* 낙찰하한 경고 배너 */}
      {floorBreached && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            권장 사정율 <strong>{fmtRate(rec.recommended_rate)}</strong>이 낙찰하한율{' '}
            <strong>{fmtRate(rec.floor_rate)}</strong> 미달입니다. 실격 위험이 있습니다.
          </span>
        </div>
      )}

      {/* 핵심 추천 카드 */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="pt-5 pb-5 text-center space-y-2">
          <p className="text-xs text-muted-foreground uppercase tracking-wide">권장 사정율</p>
          <p className="text-5xl font-bold text-primary tabular-nums">
            {fmtRate(rec.recommended_rate)}
          </p>
          <p className="text-lg font-semibold text-foreground tabular-nums">
            {fmtAmtKo(rec.recommended_amount)}
          </p>
          <div className="flex items-center justify-center gap-2 pt-1">
            <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', conf.cls)}>
              {conf.label}
            </span>
            <span className="text-xs text-muted-foreground">
              표본 {rec.evidence.srate_stats.sample_count.toLocaleString()}건
            </span>
          </div>
          <p className="text-xs text-muted-foreground pt-1 max-w-sm mx-auto">{rec.signal}</p>
        </CardContent>
      </Card>

      {/* 4전략 비교표 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">전략별 비교</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="px-4 py-2 text-left font-medium">전략</th>
                  <th className="px-4 py-2 text-right font-medium">사정율</th>
                  <th className="px-4 py-2 text-right font-medium">투찰금액</th>
                  <th className="px-4 py-2 text-right font-medium">낙찰확률</th>
                  <th className="px-4 py-2 text-center font-medium">추천</th>
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
                        'border-b last:border-0 transition-colors',
                        m.primary ? 'bg-primary/5 font-semibold' : 'hover:bg-muted/30',
                      )}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium">{m.label}</p>
                        <p className="text-xs text-muted-foreground font-normal">{m.desc}</p>
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums">
                        {fmtRate(s.rate)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-xs">
                        {fmtAmt(s.amount)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {s.win_prob > 0 ? (s.win_prob * 100).toFixed(1) + '%' : '-'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {ok
                          ? <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                          : <XCircle      className="h-4 w-4 text-red-400 mx-auto"   />
                        }
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground px-4 pb-3 pt-1">
            낙찰하한율 <strong>{fmtRate(rec.floor_rate)}</strong> 이상만 유효 (✓)
          </p>
        </CardContent>
      </Card>

      {/* 근거 패널 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">분석 근거</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* 사정율 통계 */}
          <EvidenceRow
            label="사정율 통계"
            value={fmtRate(rec.evidence.srate_stats.mean)}
            sub={`${rec.evidence.srate_stats.sample_count.toLocaleString()}건 표본`}
            extra={
              <span className="flex items-center gap-1 text-xs">
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
    <div className="flex items-center justify-between py-2 border-b last:border-0">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
        {extra && <div className="mt-0.5">{extra}</div>}
      </div>
      <div className="text-right flex items-center gap-2">
        <p className="font-mono font-semibold tabular-nums">{value}</p>
        {match === true  && <Badge variant="outline" className="text-[10px] text-green-700 border-green-300 px-1.5">수렴</Badge>}
        {match === false && <Badge variant="outline" className="text-[10px] text-orange-600 border-orange-300 px-1.5">괴리</Badge>}
      </div>
    </div>
  )
}

