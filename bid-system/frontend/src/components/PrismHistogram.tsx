/**
 * PrismHistogram — 발주처 사정율 빈도 히스토그램 + TOP 낙찰 구간 + A값 기반 실제 투찰금액
 * info21c 프리즘 2.0 (적중분석 1/3) 대응 컴포넌트
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { bidsApi } from '../api'
import { Loader2, Trophy, TrendingUp, AlertCircle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { PrismBucket, PrismZone } from '../types'

interface Props {
  bidId: number
  baseAmount: number
  agencyName?: string
}

function fmtWon(v: number | null | undefined) {
  if (!v) return '-'
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}억`
  if (v >= 1e4) return `${Math.round(v / 1e4).toLocaleString()}만`
  return v.toLocaleString() + '원'
}

const PERIOD_LABELS = { '12M': '12개월', '24M': '24개월', '48M': '48개월' } as const
type Period = keyof typeof PERIOD_LABELS

export default function PrismHistogram({ bidId, baseAmount, agencyName }: Props) {
  const [period, setPeriod] = useState<Period>('24M')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['prism-histogram', bidId, period],
    queryFn: () => bidsApi.prismHistogram(bidId, period),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 gap-2 text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm">사정율 분포 분석 중...</span>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 py-8 text-slate-500 text-sm justify-center">
        <AlertCircle className="h-4 w-4" />데이터를 불러올 수 없습니다
      </div>
    )
  }

  const hist = data.histogram
  const topZones = data.top_zones
  const maxCount = Math.max(...hist.map((h) => h.count), 1)

  // TOP 구간 srate set for highlighting
  const topSrateSet = new Set(topZones.map((z) => z.srate))

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-700">사정율 빈도 분포</span>
          <span className={cn(
            'text-xs px-1.5 py-0.5 rounded font-semibold border',
            data.data_source === 'agency'
              ? 'bg-blue-50 text-blue-700 border-blue-200'
              : 'bg-slate-100 text-slate-500 border-slate-200'
          )}>
            {data.data_source === 'agency' ? `${agencyName ?? '발주기관'} 전용` : '전국 평균'}
          </span>
          <span className="text-xs text-slate-500">{data.total_bids.toLocaleString()}건 / 낙찰 {data.total_wins}건</span>
        </div>
        <div className="flex gap-1">
          {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                'text-xs px-2.5 py-1 rounded border transition-colors',
                period === p
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-500 border-slate-200 hover:border-blue-300'
              )}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {/* A값 정보 */}
      <div className="flex items-center gap-4 bg-blue-50 rounded-lg px-4 py-2.5 text-sm">
        <div className="flex items-center gap-1.5 text-blue-700">
          <Info className="h-3.5 w-3.5" />
          <span className="font-medium">A값(예정가) 추정비율:</span>
          <span className="font-bold tabular-nums">{(data.a_ratio * 100).toFixed(4)}%</span>
        </div>
        {baseAmount > 0 && (
          <>
            <span className="text-blue-300">|</span>
            <div className="text-blue-700">
              <span className="font-medium">예정가 추정:</span>
              <span className="font-bold ml-1">{fmtWon(Math.round(baseAmount * data.a_ratio))}</span>
            </div>
            <span className="text-blue-300">|</span>
            <div className="text-blue-600 text-xs">
              실제 투찰금액 = 기초금액({fmtWon(baseAmount)}) × A값({(data.a_ratio * 100).toFixed(4)}%) × 사정율
            </div>
          </>
        )}
      </div>

      {/* 히스토그램 */}
      {hist.length === 0 ? (
        <div className="text-center py-8 text-slate-500 text-sm">
          해당 발주기관의 빈도 데이터가 없습니다. 관리자 메뉴에서 빈도 테이블을 재구축하세요.
        </div>
      ) : (
        <div>
          <div className="flex items-end gap-px overflow-x-auto pb-1" style={{ height: 120 }}>
            {hist.map((bucket) => {
              const height = Math.max(2, Math.round((bucket.count / maxCount) * 110))
              const isTop = topSrateSet.has(bucket.srate)
              const hasWin = bucket.win_count > 0
              return (
                <div
                  key={bucket.srate}
                  className="relative flex-shrink-0 group"
                  style={{ width: 8, height: 120 }}
                  title={`사정율 ${bucket.srate.toFixed(4)}\n전체 ${bucket.count}건 / 낙찰 ${bucket.win_count}건\n낙찰률 ${(bucket.win_rate * 100).toFixed(1)}%`}
                >
                  <div
                    className={cn(
                      'absolute bottom-0 w-full rounded-t-sm transition-all',
                      isTop ? 'bg-amber-400' : hasWin ? 'bg-blue-400' : 'bg-slate-200'
                    )}
                    style={{ height }}
                  />
                  {isTop && (
                    <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-amber-500" />
                  )}
                </div>
              )
            })}
          </div>
          {/* X축 라벨 */}
          <div className="flex justify-between text-xs text-slate-500 mt-1 px-1">
            <span>{hist[0]?.srate.toFixed(4)}</span>
            <span className="text-slate-500 font-medium">← 사정율 구간 →</span>
            <span>{hist[hist.length - 1]?.srate.toFixed(4)}</span>
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-amber-400 rounded-sm inline-block" />TOP 추천 구간</span>
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-blue-400 rounded-sm inline-block" />낙찰 발생 구간</span>
            <span className="flex items-center gap-1"><span className="w-3 h-2 bg-slate-200 rounded-sm inline-block" />낙찰 없음</span>
          </div>
        </div>
      )}

      {/* TOP 10 구간 테이블 */}
      {topZones.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Trophy className="h-4 w-4 text-amber-500" />
            <span className="text-sm font-semibold text-slate-700">낙찰 확률 상위 구간</span>
            <span className="text-xs text-slate-500">(낙찰률 × log(낙찰건수) 가중 점수)</span>
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="px-3 py-2 text-left font-semibold text-slate-600">순위</th>
                  <th className="px-3 py-2 text-left font-semibold text-slate-600">사정율</th>
                  <th className="px-3 py-2 text-right font-semibold text-slate-600">낙찰률</th>
                  <th className="px-3 py-2 text-right font-semibold text-slate-600">낙찰건수</th>
                  <th className="px-3 py-2 text-right font-semibold text-slate-600">전체 참여</th>
                  {baseAmount > 0 && <th className="px-3 py-2 text-right font-semibold text-slate-600">실제 투찰금액</th>}
                </tr>
              </thead>
              <tbody>
                {topZones.map((z, i) => (
                  <tr key={z.srate} className={cn(
                    'border-b border-slate-50 hover:bg-slate-50/70 transition-colors',
                    i === 0 ? 'bg-amber-50/60' : ''
                  )}>
                    <td className="px-3 py-2">
                      <span className={cn(
                        'inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold',
                        i === 0 ? 'bg-amber-400 text-white' :
                        i === 1 ? 'bg-slate-300 text-slate-700' :
                        i === 2 ? 'bg-orange-300 text-orange-800' :
                        'bg-slate-100 text-slate-500'
                      )}>
                        {z.rank}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono font-bold text-slate-800">{z.srate.toFixed(4)}</td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn(
                        'font-semibold tabular-nums',
                        z.win_rate >= 0.2 ? 'text-emerald-600' :
                        z.win_rate >= 0.05 ? 'text-blue-600' : 'text-slate-600'
                      )}>
                        {(z.win_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-700 tabular-nums">{z.win_count}건</td>
                    <td className="px-3 py-2 text-right text-slate-500 tabular-nums">{z.count}건</td>
                    {baseAmount > 0 && (
                      <td className="px-3 py-2 text-right">
                        <span className="font-semibold text-blue-700 tabular-nums">{fmtWon(z.bid_price)}</span>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {topZones.length === 0 && hist.length > 0 && (
        <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">
          <TrendingUp className="h-4 w-4 shrink-0" />
          낙찰 건수가 5건 미만인 구간만 존재합니다. 더 많은 데이터가 수집되면 추천 구간이 표시됩니다.
        </div>
      )}
    </div>
  )
}
