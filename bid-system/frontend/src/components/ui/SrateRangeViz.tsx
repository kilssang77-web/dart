interface SrateRangeVizProps {
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
}

export default function SrateRangeViz({ p10, p25, p50, p75, p90 }: SrateRangeVizProps) {
  const minV = p10 * 100
  const maxV = p90 * 100
  const range = maxV - minV || 0.001

  const pos = (v: number) => `${(((v * 100) - minV) / range) * 100}%`
  const intervalWidth = `${((p75 - p25) * 100 / range) * 100}%`

  return (
    <div className="space-y-3">
      <div className="relative h-10">
        {/* 전체 범위 트랙 */}
        <div className="absolute top-4 left-0 right-0 h-2 bg-slate-200 rounded-full" />

        {/* P25~P75 신뢰구간 */}
        <div
          className="absolute top-4 h-2 rounded-full"
          style={{
            left: pos(p25),
            width: intervalWidth,
            background: 'linear-gradient(to right, #bfdbfe, #3b82f6, #bfdbfe)',
          }}
        />

        {/* P10 마커 */}
        <div
          className="absolute top-3.5 w-1 h-3 bg-slate-400 rounded-full"
          style={{ left: pos(p10), transform: 'translateX(-50%)' }}
        />

        {/* P90 마커 */}
        <div
          className="absolute top-3.5 w-1 h-3 bg-slate-400 rounded-full"
          style={{ left: pos(p90), transform: 'translateX(-50%)' }}
        />

        {/* P50 중앙 포인트 */}
        <div
          className="absolute top-3 w-4 h-4 bg-blue-600 rounded-full border-2 border-white shadow-md"
          style={{ left: pos(p50), transform: 'translateX(-50%)' }}
        />
      </div>

      <div className="flex justify-between text-xs">
        <span className="text-slate-500">P10 {(p10 * 100).toFixed(3)}%</span>
        <span className="text-blue-500">P25 {(p25 * 100).toFixed(3)}%</span>
        <span className="font-semibold text-blue-700">중앙 {(p50 * 100).toFixed(3)}%</span>
        <span className="text-blue-500">P75 {(p75 * 100).toFixed(3)}%</span>
        <span className="text-slate-500">P90 {(p90 * 100).toFixed(3)}%</span>
      </div>
    </div>
  )
}
