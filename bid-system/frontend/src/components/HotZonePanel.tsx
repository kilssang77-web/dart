/**
 * HotZonePanel — inpo21c 실측 bid_rate 기반 Hot Zone 탐지 시각화
 * 0.877 / 0.887 / 0.897 패턴 강조 표시
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { bidsApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { Badge } from './ui/badge'
import { Loader2, Flame, TrendingUp } from 'lucide-react'
import type { HotZonePeak } from '../types'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'

interface Props {
  bidId: number
  baseAmount?: number | null
  aRatio?: number
}

type Period = '12M' | '24M' | '48M'
const PERIOD_OPTS: Period[] = ['12M', '24M', '48M']

const RANK_COLORS = ['#2563eb', '#059669', '#d97706', '#7c3aed', '#dc2626']

function PeakBadge({ peak, isTop }: { peak: HotZonePeak; isTop: boolean }) {
  return (
    <div className={`rounded-lg border p-3 text-center ${isTop ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-white'}`}>
      <div className={`text-lg font-bold font-mono ${isTop ? 'text-blue-700' : 'text-slate-700'}`}>
        {(peak.srate * 100).toFixed(1)}%
      </div>
      <div className="text-xs text-slate-500 mt-0.5">사정율</div>
      <div className={`text-sm font-semibold mt-1 ${isTop ? 'text-blue-600' : 'text-slate-600'}`}>
        {(peak.win_rate * 100).toFixed(1)}% 낙찰
      </div>
      <div className="text-xs text-slate-400">{peak.win_count}건 / {peak.total}건</div>
      {isTop && (
        <div className="mt-1.5">
          <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">
            #1 추천
          </span>
        </div>
      )}
    </div>
  )
}

export default function HotZonePanel({ bidId, baseAmount, aRatio = 0.91 }: Props) {
  const [period, setPeriod] = useState<Period>('24M')

  const { data, isLoading } = useQuery({
    queryKey: ['hot-zones', bidId, period],
    queryFn:  () => bidsApi.hotZones(bidId, period),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <Card className="border-slate-200">
        <CardContent className="flex items-center justify-center py-10 gap-2 text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Hot Zone 탐지 중...</span>
        </CardContent>
      </Card>
    )
  }

  const peaks = data?.peaks ?? []
  const kdeX = data?.kde_x ?? []
  const kdeY = data?.kde_y ?? []

  // Chart data: KDE curve points
  const chartData = kdeX.map((x, i) => ({
    rate: x,
    ratePct: +(x * 100).toFixed(1),
    signal: +(kdeY[i] * 1000).toFixed(4),  // scale for visibility
    isPeak: peaks.some((p) => Math.abs(p.srate - x) < 0.0015),
  }))

  const maxSignal = Math.max(...chartData.map((d) => d.signal), 0.001)

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader className="pb-3 border-b border-slate-100">
        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <Flame className="h-4 w-4 text-orange-500" />
          Hot Zone 탐지
          <Badge className={`ml-auto text-xs ${data?.data_source === 'agency' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
            {data?.data_source === 'agency' ? '기관 전용 데이터' : '전국 통계 기반'}
          </Badge>
          <div className="flex gap-1">
            {PERIOD_OPTS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                  period === p ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        {peaks.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">
            탐지 데이터 부족 (낙찰 이력 {data?.total_wins ?? 0}건)
          </div>
        ) : (
          <>
            {/* 피크 카드 */}
            <div className={`grid gap-3 ${peaks.length >= 3 ? 'grid-cols-3' : `grid-cols-${peaks.length}`}`}>
              {peaks.slice(0, 3).map((p, i) => (
                <PeakBadge key={p.srate} peak={p} isTop={i === 0} />
              ))}
            </div>

            {/* KDE 신호 차트 */}
            {chartData.length > 0 && (
              <div>
                <div className="text-xs text-slate-500 mb-2 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" />
                  KDE 신호 강도 (win_rate × log(낙찰건수) 가중)
                </div>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: -28, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                      dataKey="ratePct"
                      tick={{ fontSize: 10, fill: '#94a3b8' }}
                      tickFormatter={(v: number) => `${v.toFixed(0)}%`}
                      interval={Math.floor(chartData.length / 8)}
                    />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={28} />
                    <Tooltip
                      formatter={(v: number) => [v.toFixed(4), 'KDE 신호']}
                      labelFormatter={(l: number) => `사정율 ${l.toFixed(1)}%`}
                    />
                    {peaks.slice(0, 3).map((p) => (
                      <ReferenceLine
                        key={p.srate}
                        x={+(p.srate * 100).toFixed(1)}
                        stroke={RANK_COLORS[p.rank - 1] ?? '#94a3b8'}
                        strokeDasharray="4 2"
                        label={{ value: `${(p.srate * 100).toFixed(1)}%`, fontSize: 10, fill: RANK_COLORS[p.rank - 1] }}
                      />
                    ))}
                    <Bar dataKey="signal" maxBarSize={12} radius={[2, 2, 0, 0]}>
                      {chartData.map((d, i) => (
                        <Cell
                          key={i}
                          fill={d.isPeak ? '#f97316' : d.signal / maxSignal > 0.3 ? '#93c5fd' : '#e2e8f0'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* 투찰금액 계산 */}
            {baseAmount && baseAmount > 0 && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <div className="text-xs font-medium text-slate-600 mb-2">
                  피크별 추천 투찰금액
                  <span className="text-slate-400 ml-1">(기초금액 × A값({(aRatio * 100).toFixed(1)}%) × 사정율)</span>
                </div>
                <div className="space-y-1">
                  {peaks.slice(0, 3).map((p, i) => {
                    const price = Math.round(baseAmount * aRatio * p.srate)
                    return (
                      <div key={p.srate} className="flex items-center justify-between text-xs">
                        <span className={`font-mono ${i === 0 ? 'text-blue-700 font-bold' : 'text-slate-600'}`}>
                          {(p.srate * 100).toFixed(1)}%
                        </span>
                        <span className={i === 0 ? 'font-semibold text-blue-700' : 'text-slate-600'}>
                          {price.toLocaleString()}원
                        </span>
                        <span className="text-slate-400">{(p.win_rate * 100).toFixed(0)}% 낙찰률</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 통계 요약 */}
            <div className="flex gap-4 text-xs text-slate-500">
              <span>총 낙찰: {data?.total_wins.toLocaleString()}건</span>
              <span>총 투찰: {data?.total_bids.toLocaleString()}건</span>
              <span>탐지 피크: {peaks.length}개</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
