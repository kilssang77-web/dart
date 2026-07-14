import { useQuery } from '@tanstack/react-query'
import { decisionApi } from '@/api'
import type { PositionAnalysisResponse } from '@/types'
import { MapPin, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useState } from 'react'

const fmt = (n: number) => n.toLocaleString('ko-KR')

interface Props {
  bidId: number
  baseAmount: number
}

export default function PositionPatternCard({ bidId, baseAmount }: Props) {
  const [open, setOpen] = useState(false)

  const { data, isLoading } = useQuery<PositionAnalysisResponse>({
    queryKey: ['position-analysis', bidId],
    queryFn: () => decisionApi.positionAnalysis(bidId),
    staleTime: 10 * 60 * 1000,
  })

  if (isLoading) return null
  if (!data || !data.has_data) return null

  const maxFreq = Math.max(...data.position_pattern.map(p => p.freq_pct), 0.001)
  const topSet = new Set(data.top_positions)

  const confColor =
    data.confidence >= 0.7 ? 'text-emerald-600' :
    data.confidence >= 0.4 ? 'text-amber-600' :
                              'text-gray-400'

  return (
    <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-indigo-500" />
          A값 포지션 패턴 분석
          <span className="text-xs font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
            {data.data_source === 'agency' ? `기관 ${data.sample_count}건` : `전국 ${data.sample_count}건`}
          </span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>

      {open && (
        <div className="px-5 pb-5 pt-1 border-t space-y-4">

          {/* 추천 투찰율 */}
          {data.recommended_rate != null && (
            <div className="flex items-center justify-between bg-indigo-50 rounded-lg px-4 py-3 border border-indigo-100">
              <div>
                <div className="text-xs text-indigo-600 font-medium">포지션 기반 추천 투찰율</div>
                <div className="text-2xl font-bold font-mono text-indigo-800 mt-0.5">
                  {(data.recommended_rate * 100).toFixed(4)}%
                </div>
                {data.recommended_amount != null && (
                  <div className="text-xs text-indigo-600 mt-0.5">
                    {fmt(data.recommended_amount)}원
                  </div>
                )}
              </div>
              <div className="text-right space-y-1">
                {data.expected_srate != null && (
                  <div className="text-xs text-gray-500">
                    예상 사정율{' '}
                    <span className="font-mono font-semibold text-indigo-700">
                      {(data.expected_srate * 100).toFixed(4)}%
                    </span>
                  </div>
                )}
                <div className={cn('text-xs font-semibold', confColor)}>
                  신뢰도 {Math.round(data.confidence * 100)}%
                </div>
                <div className="text-[10px] text-gray-400">
                  {data.top_positions.length > 0 ? `상위포지션: #${data.top_positions.join(' #')}` : ''}
                </div>
              </div>
            </div>
          )}

          {/* 포지션 빈도 바차트 */}
          {data.position_pattern.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-600 mb-2">
                선택 포지션 빈도 상위 8개 ({data.data_source === 'agency' ? '기관' : '전국'})
              </div>
              <div className="space-y-1.5">
                {data.position_pattern.slice(0, 8).map((p, i) => {
                  const isTop = topSet.has(p.position)
                  return (
                    <div key={p.position} className="flex items-center gap-2 text-xs">
                      <span className={cn(
                        'w-12 text-right font-mono shrink-0',
                        isTop ? 'font-semibold text-indigo-700' : 'text-gray-500'
                      )}>
                        #{String(p.position).padStart(2, '0')}
                      </span>
                      <div className="flex-1 h-3 bg-gray-100 rounded overflow-hidden">
                        <div
                          className={cn(
                            'h-full rounded transition-all',
                            i === 0 ? 'bg-indigo-500' :
                            isTop   ? 'bg-indigo-300' :
                                      'bg-gray-300'
                          )}
                          style={{ width: `${(p.freq_pct / maxFreq) * 100}%` }}
                        />
                      </div>
                      <span className="w-12 text-right font-mono text-gray-600 shrink-0">
                        {p.freq_pct.toFixed(1)}%
                      </span>
                    </div>
                  )
                })}
              </div>
              <div className="mt-3 text-[10px] text-gray-400">
                inpo21c_yega is_selected 실측 데이터 기반 — 이 기관에서 실제로 추첨된 예비가격 위치 빈도
              </div>
            </div>
          )}

          {/* 낙찰하한 정보 */}
          {baseAmount > 0 && data.eff_floor != null && data.eff_floor > 0 && (
            <div className="text-xs text-gray-500 border-t pt-3">
              낙찰하한율 <span className="font-mono">{(data.eff_floor * 100).toFixed(4)}%</span>
              {' '}→ 하한가{' '}
              <span className="font-mono font-semibold text-red-600">
                {fmt(Math.round(baseAmount * data.eff_floor))}원
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
