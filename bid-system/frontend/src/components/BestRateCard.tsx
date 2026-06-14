import { useQuery } from '@tanstack/react-query'
import { bidsApi } from '../api'
import { BestRateResponse } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { Badge } from './ui/badge'

interface Props {
  bidId: number
  baseAmount?: number | null
  period?: '12M' | '24M' | '48M'
}

const SOURCE_LABEL: Record<BestRateResponse['source'], string> = {
  'hotzone+prism': 'Hot Zone + Prism 일치',
  hotzone:         'Hot Zone 기반',
  prism:           'Prism 빈도 기반',
  fallback:        '전국 기본값',
}

const SOURCE_COLOR: Record<BestRateResponse['source'], string> = {
  'hotzone+prism': 'bg-emerald-100 text-emerald-800',
  hotzone:         'bg-blue-100 text-blue-800',
  prism:           'bg-violet-100 text-violet-800',
  fallback:        'bg-slate-100 text-slate-600',
}

export default function BestRateCard({ bidId, baseAmount, period = '24M' }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['best-rate', bidId, period],
    queryFn:  () => bidsApi.bestRate(bidId, period),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <Card className="border-blue-200 bg-blue-50/50">
        <CardContent className="py-8 text-center text-sm text-slate-500">분석 중...</CardContent>
      </Card>
    )
  }

  if (!data || !data.recommended_srate) {
    return (
      <Card className="border-slate-200">
        <CardContent className="py-6 text-center text-sm text-slate-400">
          분석 데이터 부족 (낙찰 이력 없음)
        </CardContent>
      </Card>
    )
  }

  const confidencePct = Math.round(data.confidence * 100)
  const confColor =
    data.confidence >= 0.80 ? 'text-emerald-600' :
    data.confidence >= 0.60 ? 'text-amber-600' : 'text-slate-500'

  return (
    <Card className="border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50 shadow-sm">
      <CardHeader className="pb-3 border-b border-blue-100">
        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <span className="text-lg">🎯</span>
          AI 원클릭 최적 투찰율
          <Badge className={`ml-auto text-xs ${SOURCE_COLOR[data.source]}`}>
            {SOURCE_LABEL[data.source]}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        {/* 핵심 수치 */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-3xl font-bold text-blue-700 tracking-tight">
              {(data.recommended_srate * 100).toFixed(2)}%
            </div>
            <div className="text-xs text-slate-500 mt-0.5">추천 투찰 사정율</div>
          </div>
          <div className="text-right">
            <div className={`text-2xl font-bold ${confColor}`}>
              {confidencePct}%
            </div>
            <div className="text-xs text-slate-500 mt-0.5">신뢰도</div>
          </div>
        </div>

        {/* 투찰금액 */}
        {data.recommended_price && data.recommended_price > 0 && (
          <div className="bg-white/70 rounded-lg p-3 border border-blue-100">
            <div className="text-xs text-slate-500 mb-1">추천 투찰금액 (기초금액 × A값 × 사정율)</div>
            <div className="text-lg font-semibold text-slate-800">
              {data.recommended_price.toLocaleString()}원
            </div>
            <div className="text-xs text-slate-400 mt-0.5">
              A값 {(data.a_ratio * 100).toFixed(2)}% · {data.data_source === 'agency' ? '기관 실적 기반' : '전국 통계 기반'}
            </div>
          </div>
        )}

        {/* Hot Zone 피크 */}
        {data.hotzone_peaks.length > 0 && (
          <div>
            <div className="text-xs font-medium text-slate-600 mb-2">Hot Zone 피크</div>
            <div className="flex flex-wrap gap-1.5">
              {data.hotzone_peaks.map((p) => (
                <span
                  key={p.srate}
                  className={`px-2 py-0.5 rounded-full text-xs font-mono border
                    ${p.rank === 1
                      ? 'bg-blue-600 text-white border-blue-700'
                      : 'bg-white text-blue-700 border-blue-200'}`}
                >
                  {(p.srate * 100).toFixed(1)}%
                  <span className="ml-1 opacity-70">{(p.win_rate * 100).toFixed(0)}%낙찰</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Prism Top */}
        {data.prism_top.length > 0 && (
          <div>
            <div className="text-xs font-medium text-slate-600 mb-2">Prism 상위 구간</div>
            <div className="space-y-1">
              {data.prism_top.slice(0, 3).map((z, i) => (
                <div key={z.srate} className="flex items-center gap-2 text-xs">
                  <span className="w-4 text-slate-400">{i + 1}</span>
                  <span className="font-mono text-slate-700">{(z.srate * 100).toFixed(1)}%</span>
                  <div className="flex-1 bg-slate-100 rounded-full h-1.5">
                    <div
                      className="bg-violet-400 h-1.5 rounded-full"
                      style={{ width: `${Math.min(z.win_rate * 100 * 2, 100)}%` }}
                    />
                  </div>
                  <span className="text-slate-500">{(z.win_rate * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
