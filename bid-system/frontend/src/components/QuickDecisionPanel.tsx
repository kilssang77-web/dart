import { useQuery } from '@tanstack/react-query'
import { decisionApi } from '@/api'
import type { QuickDecisionResponse } from '@/types'
import { CheckCircle2, XCircle, MinusCircle, TrendingUp, AlertCircle, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

const fmt = (n: number) => n.toLocaleString('ko-KR')

interface Props {
  bidId: number
}

export default function QuickDecisionPanel({ bidId }: Props) {
  const { data, isLoading } = useQuery<QuickDecisionResponse>({
    queryKey: ['quick-decision', bidId],
    queryFn: () => decisionApi.quickDecision(bidId),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border shadow-sm p-4 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
        <div className="h-8 bg-gray-200 rounded w-1/2" />
      </div>
    )
  }
  if (!data) return null

  const goConfig = {
    go: {
      label: 'GO — 참여 권장',
      icon: CheckCircle2,
      bg: 'bg-emerald-600',
      border: 'border-emerald-500',
      text: 'text-white',
      badge: 'bg-emerald-500',
    },
    pass: {
      label: 'PASS — 참여 비권장',
      icon: XCircle,
      bg: 'bg-red-600',
      border: 'border-red-500',
      text: 'text-white',
      badge: 'bg-red-500',
    },
    neutral: {
      label: 'NEUTRAL — 신중 검토',
      icon: MinusCircle,
      bg: 'bg-amber-500',
      border: 'border-amber-400',
      text: 'text-white',
      badge: 'bg-amber-400',
    },
  } as const

  const cfg = goConfig[data.go_decision]
  const Icon = cfg.icon

  const scoreBar = Math.round(data.go_score * 100)

  return (
    <div className={cn('rounded-xl border-2 overflow-hidden shadow-sm', cfg.border)}>
      {/* 헤더 — 판정 */}
      <div className={cn('px-5 py-4 flex items-center justify-between', cfg.bg)}>
        <div className="flex items-center gap-3">
          <Icon className="w-6 h-6 text-white" />
          <div>
            <div className={cn('text-base font-bold', cfg.text)}>{cfg.label}</div>
            <div className="text-xs opacity-80 text-white mt-0.5">
              AI 종합 판정 점수 {scoreBar}점 / 100점
            </div>
          </div>
        </div>
        {/* 점수 바 */}
        <div className="w-24 h-3 bg-white/30 rounded-full overflow-hidden">
          <div
            className="h-full bg-white rounded-full transition-all"
            style={{ width: `${scoreBar}%` }}
          />
        </div>
      </div>

      <div className="px-5 py-4 bg-white space-y-4">
        {/* 추천 투찰율 & 확률 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1">AI 추천 투찰율 (기초대비)</div>
            {data.recommended_rate != null ? (
              <>
                <div className="text-xl font-bold font-mono text-blue-800">
                  {(data.recommended_rate * 100).toFixed(4)}%
                </div>
                {data.recommended_amount != null && (
                  <div className="text-xs text-blue-600 mt-0.5">
                    {fmt(data.recommended_amount)}원
                  </div>
                )}
              </>
            ) : (
              <div className="text-sm text-gray-400">데이터 부족</div>
            )}
          </div>

          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              AI 낙찰 예상 확률
            </div>
            {data.win_prob != null ? (
              <div className={cn(
                'text-xl font-bold',
                data.win_prob >= 0.35 ? 'text-emerald-700' :
                data.win_prob >= 0.20 ? 'text-amber-700' :
                                        'text-red-600'
              )}>
                {(data.win_prob * 100).toFixed(1)}%
              </div>
            ) : (
              <div className="text-sm text-gray-400">계산 불가</div>
            )}
            <div className="flex items-center gap-1 text-xs text-gray-400 mt-0.5">
              <Users className="w-3 h-3" />
              경쟁 {data.expected_competitors}개사 기준
            </div>
          </div>
        </div>

        {/* 긍정 근거 */}
        {data.reasons.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">참여 근거</div>
            {data.reasons.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                <span>{r}</span>
              </div>
            ))}
          </div>
        )}

        {/* 위험 요인 */}
        {data.risk_factors.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">주의 요인</div>
            {data.risk_factors.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                <span>{r}</span>
              </div>
            ))}
          </div>
        )}

        {/* 부가 정보 */}
        <div className="flex flex-wrap gap-3 pt-1 border-t text-xs text-gray-500">
          {data.agency_win_rate != null && (
            <span>기관 낙찰율 <strong className="text-gray-700">{(data.agency_win_rate * 100).toFixed(1)}%</strong></span>
          )}
          {data.best_rate_source && (
            <span>추천근거 <strong className="text-gray-700">{
              data.best_rate_source === 'winner+hotzone' ? '실낙찰+HotZone' :
              data.best_rate_source === 'winner'         ? '실낙찰 분포' :
              data.best_rate_source === 'hotzone+prism'  ? 'HotZone+프리즘' :
              data.best_rate_source === 'hotzone'        ? 'HotZone' :
              data.best_rate_source === 'prism'          ? '프리즘' :
                                                           '통계 추정'
            }</strong></span>
          )}
          <span>신뢰도 <strong className="text-gray-700">{Math.round(data.confidence * 100)}%</strong></span>
          <span>낙찰하한율 <strong className="font-mono text-red-600">{(data.floor_rate * 100).toFixed(4)}%</strong></span>
        </div>
      </div>
    </div>
  )
}
