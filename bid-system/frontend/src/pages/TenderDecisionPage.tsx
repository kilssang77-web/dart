import { useState, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { decisionApi } from '@/api'
import type { BidContext, SimulateBidResponse, ZoneItem } from '@/types'
import { Search, Target, Zap, TrendingUp, Shield, AlertCircle, CheckCircle2, ChevronRight, Info, Users, X } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ─────────────────────────────────────────────────────────────
   유틸
───────────────────────────────────────────────────────────── */
const fmt = (n: number) => n.toLocaleString('ko-KR')
const pct = (n: number, d = 3) => (n * 100).toFixed(d) + '%'
const ratePct = (n: number) => (n * 100).toFixed(3) + '%'

function WinProbBadge({ prob }: { prob: number }) {
  const p = prob * 100
  const color =
    p >= 40 ? 'bg-emerald-100 text-emerald-700 border-emerald-200' :
    p >= 20 ? 'bg-amber-100  text-amber-700  border-amber-200' :
              'bg-red-100    text-red-700    border-red-200'
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded border text-xs font-semibold', color)}>
      {p.toFixed(1)}%
    </span>
  )
}

/* ─────────────────────────────────────────────────────────────
   공고 검색 컴포넌트
───────────────────────────────────────────────────────────── */
function BidSearch({ onSelect }: { onSelect: (id: number, title: string) => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<{ id: number; title: string; announcement_no: string; base_amount: number }[]>([])
  const [searching, setSearching] = useState(false)

  const doSearch = useCallback(async () => {
    if (!q.trim()) return
    setSearching(true)
    try {
      const data = await decisionApi.searchBids(q.trim(), 10)
      setResults(Array.isArray(data) ? data : data.items || [])
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }, [q])

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
          placeholder="공고번호 또는 공고명 검색..."
          className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={doSearch}
          disabled={searching}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
        >
          <Search className="w-4 h-4" />
          {searching ? '검색 중...' : '검색'}
        </button>
      </div>
      {results.length > 0 && (
        <div className="border rounded-lg divide-y max-h-60 overflow-y-auto bg-white shadow-sm">
          {results.map(r => (
            <button
              key={r.id}
              onClick={() => { onSelect(r.id, r.title); setResults([]) }}
              className="w-full text-left px-3 py-2 hover:bg-blue-50 text-sm"
            >
              <div className="font-medium text-gray-800 truncate">{r.title}</div>
              <div className="text-xs text-gray-500 flex gap-3 mt-0.5">
                <span>{r.announcement_no}</span>
                <span>{r.base_amount > 0 ? (r.base_amount / 1e8).toFixed(1) + '억' : '-'}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   예비가격 15개 입력 그리드
───────────────────────────────────────────────────────────── */
function YegaGrid({
  values,
  onChange,
  baseAmount,
}: {
  values: (string | number)[]
  onChange: (vals: (string | number)[]) => void
  baseAmount: number
}) {
  const update = (i: number, v: string) => {
    const next = [...values]
    next[i] = v
    onChange(next)
  }

  return (
    <div className="grid grid-cols-3 gap-2">
      {values.map((v, i) => {
        const num = typeof v === 'string' ? Number(v.replace(/,/g, '')) : v
        const rate = num && baseAmount ? (num / baseAmount * 100).toFixed(3) : ''
        return (
          <div key={i} className="relative">
            <label className="absolute -top-2 left-2 bg-white px-1 text-xs text-gray-400 font-mono">
              #{String(i + 1).padStart(2, '0')}
            </label>
            <input
              value={v}
              onChange={e => update(i, e.target.value)}
              placeholder="예비가격(원)"
              className="w-full border rounded px-2 py-1.5 text-sm font-mono text-right focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            {rate && (
              <div className="text-right text-xs text-gray-400 mt-0.5 font-mono">{rate}%</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   히스토그램 바 차트
───────────────────────────────────────────────────────────── */
function HistogramChart({ data, optimalRate }: { data: { bin_center: number; prob: number }[]; optimalRate?: number }) {
  if (!data.length) return null
  const maxProb = Math.max(...data.map(d => d.prob))
  return (
    <div className="flex items-end gap-0.5 h-28">
      {data.map((d, i) => {
        const h = maxProb > 0 ? (d.prob / maxProb) * 100 : 0
        const isOptimal = optimalRate !== undefined && Math.abs(d.bin_center - optimalRate) < 0.0005
        return (
          <div
            key={i}
            className="relative flex-1 group"
            title={`사정율 ${ratePct(d.bin_center)} | 확률 ${(d.prob * 100).toFixed(2)}%`}
          >
            <div
              className={cn('w-full rounded-t transition-all', isOptimal ? 'bg-amber-400' : 'bg-blue-300 group-hover:bg-blue-400')}
              style={{ height: `${h}%`, minHeight: h > 0 ? '2px' : '0' }}
            />
          </div>
        )
      })}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   구간 테이블
───────────────────────────────────────────────────────────── */
function ZoneTable({ zones, baseAmount }: { zones: ZoneItem[]; baseAmount: number }) {
  const maxProb = Math.max(...zones.map(z => z.win_prob), 0.001)
  return (
    <div className="overflow-auto max-h-64">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-gray-50">
          <tr className="text-gray-500">
            <th className="py-1 px-2 text-left">투찰률</th>
            <th className="py-1 px-2 text-right">투찰금액</th>
            <th className="py-1 px-2 text-right">낙찰확률</th>
            <th className="py-1 px-2 text-left w-28">확률 바</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {zones.map((z, i) => (
            <tr key={i} className={cn('hover:bg-blue-50', !z.floor_ok && 'opacity-40')}>
              <td className="py-1 px-2 font-mono">{ratePct(z.rate)}</td>
              <td className="py-1 px-2 text-right font-mono">{fmt(z.amount)}</td>
              <td className="py-1 px-2 text-right">
                <WinProbBadge prob={z.win_prob} />
              </td>
              <td className="py-1 px-2">
                <div className="h-2 bg-gray-100 rounded overflow-hidden">
                  <div
                    className={cn('h-full rounded', z.win_prob >= 0.30 ? 'bg-emerald-400' : z.win_prob >= 0.15 ? 'bg-amber-400' : 'bg-red-300')}
                    style={{ width: `${(z.win_prob / maxProb) * 100}%` }}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   메인 페이지
───────────────────────────────────────────────────────────── */
export default function TenderDecisionPage() {
  const [bidId, setBidId] = useState<number | null>(null)
  const [bidTitle, setBidTitle] = useState('')
  const [mode, setMode] = useState<'estimated' | 'real'>('estimated')
  const [yegaInputs, setYegaInputs] = useState<(string | number)[]>(Array(15).fill(''))
  const [result, setResult] = useState<SimulateBidResponse | null>(null)
  const [activeTab, setActiveTab] = useState<'zones' | 'hist' | 'combo'>('zones')
  const [competitorRateText, setCompetitorRateText] = useState('')
  const [showCompetitorPanel, setShowCompetitorPanel] = useState(false)

  // 공고 컨텍스트 조회
  const { data: ctx } = useQuery<BidContext>({
    queryKey: ['bid-context', bidId],
    queryFn: () => decisionApi.context(bidId!),
    enabled: bidId !== null,
  })

  // 경쟁사 투찰률 파싱 (90.123% → 0.90123, 0.90123 → 0.90123)
  const parsedCompetitorRates = (): number[] | null => {
    if (!competitorRateText.trim()) return null
    const raw = competitorRateText
      .split(/[\n,;\s]+/)
      .map(s => s.trim().replace('%', ''))
      .filter(Boolean)
      .map(s => {
        const n = parseFloat(s)
        if (isNaN(n)) return null
        return n > 1 ? n / 100 : n  // 90.123 → 0.90123
      })
      .filter((n): n is number => n !== null && n >= 0.80 && n <= 1.00)
    return raw.length >= 2 ? raw : null
  }

  // 시뮬레이션 실행
  const simulateMut = useMutation({
    mutationFn: () => {
      const yega_values = mode === 'real'
        ? yegaInputs.map(v => Number(String(v).replace(/,/g, ''))).filter(n => n > 0)
        : null
      return decisionApi.simulate(bidId!, {
        yega_values: yega_values && yega_values.length === 15 ? yega_values : null,
        our_bid_rate: null,
        competitor_rates: parsedCompetitorRates(),
        n_sim: 30_000,
      })
    },
    onSuccess: (data) => setResult(data),
    onError: () => { /* 에러는 simulateMut.error로 표시 */ },
  })

  const handleBidSelect = (id: number, title: string) => {
    setBidId(id)
    setBidTitle(title)
    setResult(null)
    setYegaInputs(Array(15).fill(''))
    setCompetitorRateText('')
  }

  const canSimulate = bidId !== null && (
    mode === 'estimated' ||
    yegaInputs.filter(v => Number(String(v).replace(/,/g, '')) > 0).length === 15
  )

  const realCount = yegaInputs.filter(v => Number(String(v).replace(/,/g, '')) > 0).length

  return (
    <div className="flex flex-col h-full min-h-0 bg-gray-50">
      {/* 헤더 */}
      <div className="bg-white border-b px-6 py-4 flex items-center gap-3 shrink-0">
        <Target className="w-6 h-6 text-blue-600" />
        <div>
          <h1 className="text-lg font-bold text-gray-900">오늘의 투찰 결정</h1>
          <p className="text-xs text-gray-500">복수예가 시뮬레이션으로 최적 투찰가를 산출합니다</p>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-7xl mx-auto space-y-6">

          {/* ── 1단: 공고 선택 ── */}
          <div className="bg-white rounded-xl border p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <Search className="w-4 h-4 text-blue-500" />
              공고 선택
            </h2>
            <BidSearch onSelect={handleBidSelect} />

            {ctx && (
              <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-100">
                <div className="text-sm font-semibold text-gray-800 mb-2 line-clamp-1">{ctx.title}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div>
                    <div className="text-gray-400">발주기관</div>
                    <div className="font-medium text-gray-700">{ctx.agency_name}</div>
                  </div>
                  <div>
                    <div className="text-gray-400">기초금액</div>
                    <div className="font-medium text-gray-700">
                      {ctx.base_amount > 0 ? (ctx.base_amount / 1e8).toFixed(2) + '억' : '-'}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-400">낙찰하한율</div>
                    <div className="font-medium text-gray-700">{pct(ctx.floor_rate)}</div>
                  </div>
                  <div>
                    <div className="text-gray-400">예측 사정율</div>
                    <div className="font-medium text-blue-700 font-mono">{pct(ctx.srate_center)}</div>
                  </div>
                  <div>
                    <div className="text-gray-400">예상 경쟁사</div>
                    <div className="font-medium text-gray-700">{ctx.expected_competitors}개사</div>
                  </div>
                  <div>
                    <div className="text-gray-400">공고일</div>
                    <div className="font-medium text-gray-700">{ctx.notice_date || '-'}</div>
                  </div>
                  <div>
                    <div className="text-gray-400">개찰일</div>
                    <div className="font-medium text-gray-700">{ctx.bid_open_date || '-'}</div>
                  </div>
                  <div>
                    <div className="text-gray-400">공종</div>
                    <div className="font-medium text-gray-700">{ctx.industry_name || '-'}</div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {ctx && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

              {/* ── 2단 왼쪽: 복수예가 입력 ── */}
              <div className="bg-white rounded-xl border p-5 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-500" />
                    복수예가 입력
                  </h2>
                  {/* 모드 토글 */}
                  <div className="flex items-center bg-gray-100 rounded-lg p-0.5">
                    <button
                      onClick={() => setMode('estimated')}
                      className={cn('px-3 py-1.5 rounded-md text-xs font-medium transition-all', mode === 'estimated' ? 'bg-white shadow text-blue-700' : 'text-gray-500 hover:text-gray-700')}
                    >
                      추정 모드
                    </button>
                    <button
                      onClick={() => setMode('real')}
                      className={cn('px-3 py-1.5 rounded-md text-xs font-medium transition-all', mode === 'real' ? 'bg-white shadow text-blue-700' : 'text-gray-500 hover:text-gray-700')}
                    >
                      실측 모드
                    </button>
                  </div>
                </div>

                {mode === 'estimated' ? (
                  <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 p-4 text-sm text-blue-700 flex items-start gap-3">
                    <Info className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-semibold mb-1">추정 모드</div>
                      <div className="text-xs text-blue-600">
                        A값 ±2.8% 기반 Monte Carlo {(30000).toLocaleString()}회 시뮬레이션.<br />
                        개찰 전 예비가격 15개를 입수하면 <strong>실측 모드</strong>로 전환하세요.<br />
                        실측 모드는 C(15,4)=1,365 전수 열거로 정확도가 크게 향상됩니다.
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-500">예비가격 15개 직접 입력 (원 단위)</span>
                      <span className={cn('font-semibold', realCount === 15 ? 'text-emerald-600' : 'text-amber-600')}>
                        {realCount}/15 입력됨
                      </span>
                    </div>
                    <YegaGrid values={yegaInputs} onChange={setYegaInputs} baseAmount={ctx.base_amount} />
                    {realCount > 0 && realCount < 15 && (
                      <div className="text-xs text-amber-600 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        15개를 모두 입력해야 실측 모드로 시뮬레이션됩니다.
                      </div>
                    )}
                    {realCount === 15 && (
                      <div className="text-xs text-emerald-600 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        1,365개 조합 전수 열거 모드로 실행됩니다.
                      </div>
                    )}
                  </div>
                )}

                <button
                  onClick={() => simulateMut.mutate()}
                  disabled={!canSimulate || simulateMut.isPending}
                  className="mt-4 w-full py-3 bg-blue-600 text-white rounded-lg font-semibold text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all"
                >
                  {simulateMut.isPending ? (
                    <>
                      <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      시뮬레이션 중...
                    </>
                  ) : (
                    <>
                      <Target className="w-4 h-4" />
                      시뮬레이션 실행
                    </>
                  )}
                </button>

                {simulateMut.isError && (
                  <div className="mt-2 text-xs text-red-600 flex items-center gap-1 bg-red-50 rounded p-2">
                    <AlertCircle className="w-3 h-3 shrink-0" />
                    {ctx.base_amount === 0
                      ? '기초금액 정보가 없어 시뮬레이션을 실행할 수 없습니다.'
                      : '시뮬레이션 실행 중 오류가 발생했습니다. 다시 시도해주세요.'}
                  </div>
                )}
              </div>

              {/* ── 2단 오른쪽: 경쟁사 투찰률 + 예측 정보 ── */}
              <div className="space-y-4">
                {/* 경쟁사 투찰률 수동 입력 패널 */}
                <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
                  <button
                    onClick={() => setShowCompetitorPanel(p => !p)}
                    className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-violet-500" />
                      경쟁사 투찰률 입력
                      {parsedCompetitorRates() && (
                        <span className="ml-1 px-1.5 py-0.5 bg-violet-100 text-violet-700 rounded text-xs font-medium">
                          {parsedCompetitorRates()!.length}개 입력됨
                        </span>
                      )}
                    </div>
                    <span className="text-gray-400 text-xs">{showCompetitorPanel ? '접기 ▲' : '펼치기 ▼'}</span>
                  </button>
                  {showCompetitorPanel && (
                    <div className="px-5 pb-4 space-y-3 border-t">
                      <div className="pt-3 text-xs text-gray-500 leading-relaxed">
                        info21c에서 확인한 경쟁사 투찰률을 입력하면 DB 평균 대신 실제 경쟁사 분포로 낙찰확률을 계산합니다.<br />
                        형식: 한 줄에 하나씩 또는 쉼표 구분. <span className="font-mono bg-gray-100 px-1 rounded">90.123</span> 또는 <span className="font-mono bg-gray-100 px-1 rounded">0.90123</span> 모두 허용.
                      </div>
                      <div className="relative">
                        <textarea
                          value={competitorRateText}
                          onChange={e => setCompetitorRateText(e.target.value)}
                          placeholder={'예) 90.234\n89.876\n91.102\n...'}
                          rows={5}
                          className="w-full border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-violet-400 resize-none"
                        />
                        {competitorRateText && (
                          <button
                            onClick={() => setCompetitorRateText('')}
                            className="absolute top-2 right-2 text-gray-300 hover:text-gray-500"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                      {parsedCompetitorRates() ? (
                        <div className="text-xs text-violet-700 bg-violet-50 rounded p-2 flex flex-wrap gap-1">
                          {parsedCompetitorRates()!.map((r, i) => (
                            <span key={i} className="font-mono bg-violet-100 px-1.5 py-0.5 rounded">
                              {(r * 100).toFixed(3)}%
                            </span>
                          ))}
                        </div>
                      ) : competitorRateText.trim() ? (
                        <div className="text-xs text-amber-600 flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />
                          유효한 투찰률(0.80~1.00 또는 80~100%)이 2개 이상 필요합니다.
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>

                {/* 예측 정보 */}
                <div className="bg-white rounded-xl border p-5 shadow-sm space-y-4">
                <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <Info className="w-4 h-4 text-gray-400" />
                  예측 정보
                </h2>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">예측 A값 (예정가격)</span>
                    <span className="font-mono font-semibold text-blue-700">
                      {ctx.a_value ? fmt(ctx.a_value) + '원' : fmt(Math.round(ctx.base_amount * ctx.srate_center)) + '원 (추정)'}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">낙찰하한가 (추정)</span>
                    <span className="font-mono font-semibold text-red-600">
                      {fmt(Math.round(ctx.base_amount * ctx.srate_center * ctx.floor_rate))}원
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">사정율 표준편차</span>
                    <span className="font-mono text-gray-700">{pct(ctx.srate_std, 3)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">예상 경쟁사 수</span>
                    <span className="font-semibold text-gray-700">{ctx.expected_competitors}개사</span>
                  </div>
                </div>

                {ctx.pos_weights && (
                  <div>
                    <div className="text-xs text-gray-400 mb-2">예비가격 위치별 추첨 빈도 (inpo21c 실증)</div>
                    <div className="flex items-end gap-0.5 h-12">
                      {ctx.pos_weights.map((w, i) => {
                        const maxW = Math.max(...ctx.pos_weights!)
                        return (
                          <div
                            key={i}
                            className="flex-1 bg-indigo-200 rounded-t hover:bg-indigo-300 transition-all"
                            style={{ height: `${(w / maxW) * 100}%`, minHeight: '2px' }}
                            title={`위치 #${i + 1}: ${(w * 100).toFixed(1)}%`}
                          />
                        )
                      })}
                    </div>
                    <div className="flex justify-between text-xs text-gray-300 mt-0.5">
                      <span>#1</span><span>#15</span>
                    </div>
                  </div>
                )}
                </div>
              </div>
            </div>
          )}

          {/* ── 3단: 시뮬레이션 결과 ── */}
          {result && (
            <>
              {/* 최적 투찰가 — 핵심 출력 */}
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl p-6 text-white shadow-lg">
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div>
                    <div className="text-blue-200 text-sm mb-1">
                      최적 투찰가 ({result.mode === 'real' ? '실측 C(15,4) 전수' : '추정 Monte Carlo'})
                    </div>
                    {result.optimal && result.optimal.amount ? (
                      <>
                        <div className="text-4xl font-bold tracking-tight">
                          {fmt(result.optimal.amount)}
                          <span className="text-xl ml-2">원</span>
                        </div>
                        <div className="flex items-center gap-4 mt-2 text-blue-100 text-sm">
                          <span>사정율 <strong className="text-white font-mono">{ratePct(result.optimal.rate)}</strong></span>
                          <span>낙찰확률 <strong className="text-amber-300 text-base">{(result.optimal.win_prob * 100).toFixed(1)}%</strong></span>
                          <span>낙찰하한 {result.optimal.floor_ok ? <CheckCircle2 className="w-4 h-4 inline text-emerald-300" /> : <AlertCircle className="w-4 h-4 inline text-red-300" />}</span>
                        </div>
                      </>
                    ) : (
                      <div className="text-blue-200 text-sm">최적 구간을 산출할 수 없습니다.</div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-blue-200 text-xs mb-1">기초금액</div>
                    <div className="text-xl font-semibold">{(result.base_amount / 1e8).toFixed(2)}억</div>
                    <div className="text-blue-200 text-xs mt-1">낙찰하한율 {pct(result.floor_rate)}</div>
                  </div>
                </div>
              </div>

              {/* 4전략 카드 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(result.strategies).map(([key, s]) => {
                  const icons: Record<string, React.ReactNode> = {
                    aggressive: <Zap className="w-4 h-4 text-red-500" />,
                    balanced: <TrendingUp className="w-4 h-4 text-blue-500" />,
                    conservative: <Shield className="w-4 h-4 text-emerald-500" />,
                  }
                  const colors: Record<string, string> = {
                    aggressive: 'border-red-200 bg-red-50',
                    balanced: 'border-blue-200 bg-blue-50',
                    conservative: 'border-emerald-200 bg-emerald-50',
                  }
                  return (
                    <div key={key} className={cn('rounded-xl border p-4 shadow-sm', colors[key] || 'border-gray-200 bg-white')}>
                      <div className="flex items-center gap-2 mb-3">
                        {icons[key] || <Target className="w-4 h-4 text-gray-400" />}
                        <span className="font-semibold text-sm text-gray-800">{s.label}</span>
                        <WinProbBadge prob={s.win_prob} />
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-500">투찰금액</span>
                          <span className="font-mono font-semibold">{fmt(s.amount)}원</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-500">사정율</span>
                          <span className="font-mono">{ratePct(s.rate)}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-500">평균 순위</span>
                          <span className="font-semibold">{s.avg_rank?.toFixed(1) ?? '-'}위</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* 분석 탭 */}
              <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div className="flex border-b">
                  {([['zones', '구간별 낙찰확률'], ['hist', '예정가격 분포'], ['combo', '조합 분석']] as const).map(([t, label]) => (
                    <button
                      key={t}
                      onClick={() => setActiveTab(t)}
                      className={cn('px-5 py-3 text-sm font-medium border-b-2 transition-colors', activeTab === t ? 'border-blue-600 text-blue-700 bg-blue-50' : 'border-transparent text-gray-500 hover:text-gray-700')}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div className="p-5">
                  {activeTab === 'zones' && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-gray-700">
                          상위 낙찰 구간 (낙찰확률 순)
                        </span>
                        <span className="text-xs text-gray-400">전체 {result.all_zones.length}개 구간 스캔</span>
                      </div>
                      <ZoneTable zones={result.top_zones} baseAmount={result.base_amount} />
                      <details className="mt-3">
                        <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
                          전체 구간 보기 ({result.all_zones.length}개)
                        </summary>
                        <div className="mt-2">
                          <ZoneTable zones={result.all_zones} baseAmount={result.base_amount} />
                        </div>
                      </details>
                    </div>
                  )}

                  {activeTab === 'hist' && (
                    <div className="space-y-3">
                      <div className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                        예정가격 사정율 분포
                        <span className="text-xs font-normal text-gray-400">
                          ({result.mode === 'real' ? 'C(15,4)=1,365 전수' : 'Monte Carlo 30,000회'})
                        </span>
                      </div>
                      <HistogramChart data={result.histogram} optimalRate={result.optimal?.srate} />
                      <div className="flex justify-between text-xs text-gray-400 mt-1">
                        <span>← 낮은 사정율 (낙찰하한 방향)</span>
                        <span>높은 사정율 →</span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-xs">
                        {[
                          { label: 'P10 (10백분위)', val: result.histogram[Math.floor(result.histogram.length * 0.1)]?.bin_center },
                          { label: 'P25 (25백분위)', val: result.histogram[Math.floor(result.histogram.length * 0.25)]?.bin_center },
                          { label: 'P50 (중앙값)', val: result.histogram[Math.floor(result.histogram.length * 0.5)]?.bin_center },
                          { label: 'P90 (90백분위)', val: result.histogram[Math.floor(result.histogram.length * 0.9)]?.bin_center },
                        ].map(({ label, val }) => (
                          <div key={label} className="bg-gray-50 rounded-lg p-2.5">
                            <div className="text-gray-400">{label}</div>
                            <div className="font-mono font-semibold mt-0.5">{val ? ratePct(val) : '-'}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {activeTab === 'combo' && (
                    <div className="space-y-3">
                      <div className="text-sm font-semibold text-gray-700">
                        {result.mode === 'real' ? '예정가격 근접 조합 TOP 20' : '최빈 예정가격 구간 TOP 10'}
                      </div>
                      <div className="overflow-auto max-h-72">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-gray-50">
                            <tr className="text-gray-500">
                              <th className="py-1 px-2 text-left">순위</th>
                              {result.mode === 'real' && <th className="py-1 px-2 text-left">조합</th>}
                              <th className="py-1 px-2 text-right">금액</th>
                              <th className="py-1 px-2 text-right">사정율</th>
                              <th className="py-1 px-2 text-right">확률</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {result.top_combinations.map((c, i) => (
                              <tr key={i} className="hover:bg-blue-50">
                                <td className="py-1 px-2 text-gray-400">{i + 1}</td>
                                {result.mode === 'real' && (
                                  <td className="py-1 px-2 font-mono text-indigo-600">
                                    {c.combo.map(n => `#${n}`).join(' ')}
                                  </td>
                                )}
                                <td className="py-1 px-2 text-right font-mono">{fmt(c.amount)}</td>
                                <td className="py-1 px-2 text-right font-mono">{ratePct(c.rate)}</td>
                                <td className="py-1 px-2 text-right">
                                  {(c.prob * 100).toFixed(3)}%
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* 공고 미선택 상태 */}
          {!bidId && (
            <div className="bg-white rounded-xl border p-16 text-center shadow-sm">
              <Target className="w-12 h-12 text-blue-200 mx-auto mb-4" />
              <div className="text-gray-400 text-sm">
                위에서 공고를 검색하고 선택하면<br />
                복수예가 시뮬레이션과 최적 투찰가를 산출합니다.
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
