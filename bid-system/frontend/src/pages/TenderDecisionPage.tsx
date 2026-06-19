import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { decisionApi, journalApi } from '@/api'
import type { BidContext, SimulateBidResponse, ZoneItem, JournalOut, AgencyWinHistogram, CompetitorPredictionResponse } from '@/types'
import BestRateCard from '@/components/BestRateCard'
import {
  Search, Target, Zap, TrendingUp, Shield, AlertCircle, CheckCircle2,
  Info, Users, X, BookOpen, ClipboardCheck, Trophy, ChevronRight, ChevronLeft,
  BarChart3, Award, ChevronDown, ChevronUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'

/* ─────────────────────────────────────────────────────────────
   유틸
───────────────────────────────────────────────────────────── */
const fmt = (n: number) => n.toLocaleString('ko-KR')
const pct = (n: number, d = 4) => (n * 100).toFixed(d) + '%'
const ratePct = (n: number) => (n * 100).toFixed(4) + '%'

/* ─────────────────────────────────────────────────────────────
   Step Indicator (2단계)
───────────────────────────────────────────────────────────── */
const STEPS = [
  { id: 1, label: '공고 선택',     icon: Search },
  { id: 2, label: 'AI 투찰 결정', icon: Target },
] as const

function StepIndicator({ current, maxReached, onNav }: { current: number; maxReached: number; onNav: (s: number) => void }) {
  return (
    <div className="flex items-center gap-0 bg-white border-b px-6 py-3 shrink-0">
      {STEPS.map((s, idx) => {
        const done = s.id < current
        const active = s.id === current
        const clickable = s.id <= maxReached
        const Icon = s.icon
        return (
          <div key={s.id} className="flex items-center gap-0">
            <button
              onClick={() => clickable && onNav(s.id)}
              disabled={!clickable}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all',
                active
                  ? 'bg-blue-600 text-white shadow-sm'
                  : done
                    ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 cursor-pointer'
                    : clickable
                      ? 'text-gray-600 hover:bg-gray-100 cursor-pointer'
                      : 'text-gray-300 cursor-not-allowed',
              )}
            >
              {done ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> : <Icon className="w-3.5 h-3.5 shrink-0" />}
              <span className="hidden sm:inline">{s.label}</span>
              <span className="sm:hidden font-mono">{s.id}</span>
            </button>
            {idx < STEPS.length - 1 && <ChevronRight className="w-4 h-4 text-gray-300 mx-1 shrink-0" />}
          </div>
        )
      })}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   Win Prob Badge
───────────────────────────────────────────────────────────── */
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
function YegaGrid({ values, onChange, baseAmount }: { values: (string | number)[]; onChange: (vals: (string | number)[]) => void; baseAmount: number }) {
  const update = (i: number, v: string) => {
    const next = [...values]
    next[i] = v
    onChange(next)
  }

  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLDivElement>) => {
    const text = e.clipboardData.getData('text')
    const nums = text
      .split(/[\t\n\r,;\s]+/)
      .map(s => s.replace(/,/g, '').trim())
      .filter(s => /^\d{6,}$/.test(s))
      .slice(0, 15)
    if (nums.length >= 3) {
      e.preventDefault()
      const next = Array(15).fill('') as string[]
      nums.forEach((v, i) => { next[i] = v })
      onChange(next)
    }
  }, [onChange])

  const filledCount = values.filter(v => v !== '' && v !== 0).length

  return (
    <div>
      <div className="grid grid-cols-3 gap-2" onPaste={handlePaste}>
        {values.map((v, i) => {
          const num = typeof v === 'string' ? Number(v.replace(/,/g, '')) : v
          const rate = num && baseAmount ? (num / baseAmount * 100).toFixed(4) : ''
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
              {rate && <div className="text-right text-xs text-gray-400 mt-0.5 font-mono">{rate}%</div>}
            </div>
          )
        })}
      </div>
      {filledCount > 0 && filledCount < 15 && (
        <p className="text-xs text-amber-600 mt-2">{filledCount}/15 입력됨 — 엑셀에서 복사 후 붙여넣기(Ctrl+V)로 한번에 입력 가능</p>
      )}
      {filledCount === 0 && (
        <p className="text-xs text-gray-400 mt-2">엑셀 15개 셀 복사 후 이 영역에 붙여넣기(Ctrl+V)하면 자동 입력됩니다</p>
      )}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   기관별 실증 낙찰 분포 차트
───────────────────────────────────────────────────────────── */
function AgencyWinHistogramChart({ data }: { data: AgencyWinHistogram }) {
  if (!data.bins.length) return null

  const topRates = new Set(data.top_zones.map(z => z.rate))
  const maxTotal = Math.max(...data.bins.map(b => b.total_count), 1)

  return (
    <div className="space-y-3">
      {data.top_zones.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.top_zones.map((z, i) => (
            <div
              key={i}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border',
                i === 0 ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-blue-50 text-blue-700 border-blue-200',
              )}
            >
              <Award className="w-3 h-3" />
              {i + 1}위 {(z.rate * 100).toFixed(4)}%
              <span className="opacity-70">({z.win_count}/{z.total_count}건 낙찰)</span>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-px h-20 bg-gray-50 rounded-lg p-2">
        {data.bins.map((b, i) => {
          const h = (b.total_count / maxTotal) * 100
          const isTop = topRates.has(b.rate)
          return (
            <div
              key={i}
              className="relative flex-1 group cursor-default"
              title={`${(b.rate * 100).toFixed(4)}% | 전체 ${b.total_count}건 | 낙찰 ${b.win_count}건 (${(b.win_rate * 100).toFixed(1)}%)`}
            >
              <div
                className={cn('w-full rounded-t transition-all', isTop ? 'bg-emerald-400' : 'bg-gray-300 group-hover:bg-gray-400')}
                style={{ height: `${h}%`, minHeight: b.total_count > 0 ? '2px' : '0' }}
              />
              {b.win_count > 0 && (
                <div
                  className={cn('absolute bottom-0 w-full rounded-t', isTop ? 'bg-emerald-600' : 'bg-blue-400')}
                  style={{ height: `${(b.win_count / maxTotal) * 100}%`, minHeight: '2px' }}
                />
              )}
            </div>
          )
        })}
      </div>
      <div className="flex justify-between text-xs text-gray-400">
        <span className="font-mono">{data.bins.length > 0 ? (data.bins[0].rate * 100).toFixed(4) + '%' : ''}</span>
        <span className="text-gray-500">
          {data.data_source === 'agency' ? `기관 실증 ${data.inpo21c_n.toLocaleString()}건` : '전국 평균 집계'}
          &nbsp;|&nbsp;낙찰 {data.total_wins}건
        </span>
        <span className="font-mono">{data.bins.length > 0 ? (data.bins[data.bins.length - 1].rate * 100).toFixed(4) + '%' : ''}</span>
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-gray-300" /> 전체 투찰</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-blue-400" /> 낙찰</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-emerald-400" /> TOP 구간</span>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   승률 곡선 (LightGBM win_prob_model)
───────────────────────────────────────────────────────────── */
function WinProbCurveChart({ data, strategies }: { data: import('@/types').WinProbCurve; strategies?: { rate: number; label: string; color: string }[] }) {
  if (!data.curve.length) {
    return (
      <div className="flex items-center justify-center h-16 text-xs text-gray-400">
        모델 미학습 — 관리자 페이지에서 학습 후 사용 가능
      </div>
    )
  }

  const maxProb = Math.max(...data.curve.map(p => p.win_prob), 0.001)
  const floorBid = data.floor_rate

  return (
    <div className="space-y-2">
      <div className="relative h-24 bg-gray-50 rounded-lg p-2 overflow-hidden">
        <div className="flex items-end gap-0 h-full">
          {data.curve.map((p, i) => {
            const h = (p.win_prob / maxProb) * 100
            const isFloor = p.bid_rate < floorBid
            const isStrategy = strategies?.some(s => Math.abs(s.rate - p.bid_rate) < 0.0008)
            const strategyMatch = strategies?.find(s => Math.abs(s.rate - p.bid_rate) < 0.0008)
            return (
              <div key={i} className="relative flex-1 group" title={`투찰율 ${(p.bid_rate * 100).toFixed(4)}% → 낙찰확률 ${(p.win_prob * 100).toFixed(2)}%`}>
                <div
                  className={cn(
                    'w-full rounded-t transition-all',
                    isFloor ? 'bg-red-200' : isStrategy ? strategyMatch?.color ?? 'bg-emerald-500' : 'bg-blue-200 group-hover:bg-blue-300',
                  )}
                  style={{ height: `${Math.max(h, 1)}%` }}
                />
              </div>
            )
          })}
        </div>
        <div
          className="absolute top-0 bottom-0 w-px bg-red-400 opacity-60"
          style={{
            left: `${((floorBid - data.curve[0]?.bid_rate) / (data.curve[data.curve.length - 1]?.bid_rate - data.curve[0]?.bid_rate)) * 100}%`,
          }}
          title={`낙찰하한 ${(floorBid * 100).toFixed(4)}%`}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-400">
        <span className="font-mono">{(data.curve[0]?.bid_rate * 100).toFixed(4)}%</span>
        <span className="text-gray-500">사정율 {(data.srate * 100).toFixed(4)}% · 경쟁 {data.n_competitors}사 기준</span>
        <span className="font-mono">{(data.curve[data.curve.length - 1]?.bid_rate * 100).toFixed(4)}%</span>
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-500 flex-wrap">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-blue-200" /> 모델 예측 승률</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-red-200" /> 낙찰하한 이하</span>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   히스토그램
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
          <div key={i} className="relative flex-1 group" title={`사정율 ${ratePct(d.bin_center)} | 확률 ${(d.prob * 100).toFixed(2)}%`}>
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
              <td className="py-1 px-2 text-right"><WinProbBadge prob={z.win_prob} /></td>
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
   접을 수 있는 섹션
───────────────────────────────────────────────────────────── */
function Collapsible({ title, icon: Icon, iconColor, defaultOpen = false, badge, children }: {
  title: string
  icon: React.ElementType
  iconColor: string
  defaultOpen?: boolean
  badge?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className={cn('w-4 h-4', iconColor)} />
          {title}
          {badge && <span className="text-xs font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded">{badge}</span>}
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {open && <div className="px-5 pb-5 pt-1 border-t">{children}</div>}
    </div>
  )
}

/* ─────────────────────────────────────────────────────────────
   메인 페이지
───────────────────────────────────────────────────────────── */
export default function TenderDecisionPage() {
  const [searchParams] = useSearchParams()

  const [step, setStep] = useState(1)
  const [maxReached, setMaxReached] = useState(1)

  const [bidId, setBidId] = useState<number | null>(null)
  const [bidTitle, setBidTitle] = useState('')
  const [mode, setMode] = useState<'estimated' | 'real'>('estimated')
  const [yegaInputs, setYegaInputs] = useState<(string | number)[]>(Array(15).fill(''))
  const [result, setResult] = useState<SimulateBidResponse | null>(null)
  const [activeTab, setActiveTab] = useState<'zones' | 'hist' | 'combo'>('zones')
  const [competitorRateText, setCompetitorRateText] = useState('')
  const [journalRecord, setJournalRecord] = useState<JournalOut | null>(null)
  const [showResultPanel, setShowResultPanel] = useState(false)
  const [submittedRateInput, setSubmittedRateInput] = useState('')
  const [strategyChosen, setStrategyChosen] = useState('balanced')
  const [resultForm, setResultForm] = useState<{
    result: '낙찰' | '패찰' | '무효' | '취소'
    actual_srate: string
    our_rank: string
    total_bidders: string
    winner_rate: string
    winner_amount: string
    winner_biz_no: string
    winner_name: string
    note: string
  }>({
    result: '패찰',
    actual_srate: '',
    our_rank: '',
    total_bidders: '',
    winner_rate: '',
    winner_amount: '',
    winner_biz_no: '',
    winner_name: '',
    note: '',
  })

  const { data: ctx, isLoading: ctxLoading } = useQuery<BidContext>({
    queryKey: ['bid-context', bidId],
    queryFn: () => decisionApi.context(bidId!),
    enabled: bidId !== null,
  })

  const { data: agencyHistogram } = useQuery<AgencyWinHistogram>({
    queryKey: ['agency-win-histogram', bidId],
    queryFn: () => decisionApi.agencyWinHistogram(bidId!),
    enabled: bidId !== null,
    staleTime: 5 * 60 * 1000,
  })

  const { data: winProbCurveData } = useQuery<import('@/types').WinProbCurve>({
    queryKey: ['win-prob-curve', bidId],
    queryFn: () => decisionApi.winProbCurve(bidId!),
    enabled: bidId !== null,
    staleTime: 5 * 60 * 1000,
  })

  const { data: competitorPred } = useQuery<CompetitorPredictionResponse>({
    queryKey: ['competitor-prediction', bidId],
    queryFn: () => decisionApi.competitorPrediction(bidId!),
    enabled: bidId !== null,
    staleTime: 5 * 60 * 1000,
  })

  const parsedCompetitorRates = (): number[] | null => {
    if (!competitorRateText.trim()) return null
    const raw = competitorRateText
      .split(/[\n,;\s]+/)
      .map(s => s.trim().replace('%', ''))
      .filter(Boolean)
      .map(s => {
        const n = parseFloat(s)
        if (isNaN(n)) return null
        return n > 1 ? n / 100 : n
      })
      .filter((n): n is number => n !== null && n >= 0.80 && n <= 1.00)
    return raw.length >= 2 ? raw : null
  }

  const simulateMut = useMutation({
    mutationFn: (opts?: { forceReal?: boolean }) => {
      const useReal = opts?.forceReal ?? (mode === 'real')
      const yega_values = useReal
        ? yegaInputs.map(v => Number(String(v).replace(/,/g, ''))).filter(n => n > 0)
        : null
      return decisionApi.simulate(bidId!, {
        yega_values: yega_values && yega_values.length === 15 ? yega_values : null,
        our_bid_rate: null,
        competitor_rates: parsedCompetitorRates(),
        n_sim: 30_000,
      })
    },
    onSuccess: (data) => {
      setResult(data)
      setJournalRecord(null)
      setShowResultPanel(false)
      setSubmittedRateInput('')
      setStrategyChosen('balanced')
    },
  })

  /* 공고 선택 시 자동 시뮬레이션 실행 */
  useEffect(() => {
    if (bidId !== null) {
      simulateMut.mutate({ forceReal: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bidId])

  /* URL ?bid=X 파라미터로 진입 시 해당 공고 자동 선택 */
  useEffect(() => {
    const paramBidId = searchParams.get('bid')
    if (paramBidId) {
      const id = Number(paramBidId)
      if (!isNaN(id) && id > 0) {
        setBidId(id)
        setBidTitle('')
        setResult(null)
        setYegaInputs(Array(15).fill(''))
        setCompetitorRateText('')
        setJournalRecord(null)
        setShowResultPanel(false)
        setSubmittedRateInput('')
        setStrategyChosen('balanced')
        setMode('estimated')
        setStep(2)
        setMaxReached(2)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ctx 로드 후 bidTitle 업데이트 */
  useEffect(() => {
    if (ctx?.title && !bidTitle) {
      setBidTitle(ctx.title)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx?.title])

  const journalMut = useMutation({
    mutationFn: () => {
      const rate = parseFloat(submittedRateInput) / 100
      return journalApi.create({
        bid_id: bidId!,
        pred_log_id: result?.pred_log_id ?? null,
        recommended_rate: result?.optimal?.rate ?? null,
        recommended_amount: result?.optimal?.amount ?? null,
        pred_win_prob: result?.optimal?.win_prob ?? null,
        pred_srate_center: ctx?.srate_center ?? null,
        strategy_chosen: strategyChosen,
        submitted_rate: rate,
        submitted_amount: result ? Math.round(result.base_amount * rate) : null,
        floor_rate: result?.floor_rate ?? null,
      })
    },
    onSuccess: (data) => setJournalRecord(data),
  })

  const resultMut = useMutation({
    mutationFn: () =>
      journalApi.recordResult(journalRecord!.id, {
        result: resultForm.result,
        actual_srate: resultForm.actual_srate ? parseFloat(resultForm.actual_srate) / 100 : null,
        our_rank: resultForm.our_rank ? parseInt(resultForm.our_rank) : null,
        total_bidders: resultForm.total_bidders ? parseInt(resultForm.total_bidders) : null,
        winner_rate: resultForm.winner_rate ? parseFloat(resultForm.winner_rate) / 100 : null,
        winner_amount: resultForm.winner_amount ? parseInt(resultForm.winner_amount.replace(/,/g, '')) : null,
        winner_biz_no: resultForm.winner_biz_no || null,
        winner_name: resultForm.winner_name || null,
        note: resultForm.note || null,
      }),
    onSuccess: (data) => {
      setJournalRecord(data)
      setShowResultPanel(false)
    },
  })

  const goStep = (s: number) => {
    setStep(s)
    setMaxReached(prev => Math.max(prev, s))
  }

  const handleBidSelect = (id: number, title: string) => {
    setBidId(id)
    setBidTitle(title)
    setResult(null)
    setYegaInputs(Array(15).fill(''))
    setCompetitorRateText('')
    setJournalRecord(null)
    setShowResultPanel(false)
    setSubmittedRateInput('')
    setStrategyChosen('balanced')
    setMode('estimated')
    goStep(2)
  }

  const realCount = yegaInputs.filter(v => Number(String(v).replace(/,/g, '')) > 0).length
  const canReSimulate = bidId !== null && (mode === 'estimated' || realCount === 15)

  const resetAll = () => {
    setBidId(null)
    setBidTitle('')
    setResult(null)
    setStep(1)
    setMaxReached(1)
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-gray-50">
      {/* 헤더 */}
      <div className="bg-white border-b px-6 py-3 flex items-center gap-3 shrink-0">
        <Target className="w-5 h-5 text-blue-600" />
        <div className="flex-1">
          <h1 className="text-base font-bold text-gray-900">AI 투찰 결정</h1>
          {bidTitle && <p className="text-xs text-gray-400 truncate max-w-lg">{bidTitle}</p>}
        </div>
        {bidId && (
          <button
            onClick={resetAll}
            className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1 px-3 py-1.5 border rounded-lg hover:bg-gray-50"
          >
            <Search className="w-3.5 h-3.5" />
            새 공고 선택
          </button>
        )}
      </div>

      {/* Step Indicator */}
      <StepIndicator current={step} maxReached={maxReached} onNav={goStep} />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto">

          {/* ══════════════ STEP 1: 공고 선택 ══════════════ */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="bg-white rounded-xl border p-6 shadow-sm">
                <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                  <Search className="w-4 h-4 text-blue-500" />
                  투찰할 공고를 검색하세요
                </h2>
                <BidSearch onSelect={handleBidSelect} />
                <p className="mt-4 text-xs text-gray-400">
                  공고를 선택하면 <strong>자동으로 AI 시뮬레이션</strong>이 실행되고 즉시 추천 투찰률을 확인할 수 있습니다.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm">
                  <div className="font-semibold text-blue-800 mb-1 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-500" />
                    공고 선택 즉시 자동 분석
                  </div>
                  <div className="text-xs text-blue-700 leading-relaxed">
                    공고 선택 → AI가 자동으로 Monte Carlo 30,000회 시뮬레이션을 실행합니다.
                    추가 클릭 없이 바로 최적 투찰률을 확인하세요.
                  </div>
                </div>
                <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 text-sm">
                  <div className="font-semibold text-emerald-800 mb-1 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-emerald-500" />
                    실측 모드 지원
                  </div>
                  <div className="text-xs text-emerald-700 leading-relaxed">
                    예비가격 15개를 입수하면 실측 모드로 재시뮬레이션하세요.
                    C(15,4)=1,365 전수 열거로 정확도가 크게 향상됩니다.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ══════════════ STEP 2: AI 분석 & 투찰 결정 ══════════════ */}
          {step === 2 && (
            <div className="space-y-5">

              {/* ── 공고 정보 (compact) ── */}
              {ctx && (
                <div className="bg-white rounded-xl border p-4 shadow-sm">
                  <div className="text-sm font-semibold text-gray-800 mb-3 bg-blue-50 p-3 rounded-lg border border-blue-100 line-clamp-2">
                    {ctx.title}
                  </div>
                  <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-xs">
                    {[
                      { label: '기초금액', val: ctx.base_amount > 0 ? (ctx.base_amount / 1e8).toFixed(2) + '억' : '-' },
                      { label: '발주기관', val: ctx.agency_name },
                      { label: '공종', val: ctx.industry_name || '-' },
                      { label: '개찰일', val: String(ctx.bid_open_date || '-') },
                      { label: '낙찰하한율', val: pct(ctx.floor_rate) },
                      { label: '예상 경쟁사', val: ctx.expected_competitors + '개사' },
                    ].map(({ label, val }) => (
                      <div key={label}>
                        <div className="text-gray-400">{label}</div>
                        <div className="font-medium text-gray-700 mt-0.5">{val}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {ctxLoading && (
                <div className="bg-white rounded-xl border p-8 text-center text-gray-400 shadow-sm animate-pulse">
                  공고 데이터 로딩 중...
                </div>
              )}

              {/* ── AI 원클릭 최적 투찰율 (BestRateCard) ── */}
              {ctx && <BestRateCard bidId={ctx.bid_id} baseAmount={ctx.base_amount} />}

              {/* ── 시뮬레이션 결과 (자동 실행) ── */}
              {simulateMut.isPending && (
                <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl p-6 text-white shadow-lg animate-pulse">
                  <div className="flex items-center gap-3">
                    <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <div>
                      <div className="font-semibold text-blue-100">Monte Carlo 시뮬레이션 실행 중...</div>
                      <div className="text-sm text-blue-200 mt-0.5">30,000회 반복으로 최적 투찰률을 계산하고 있습니다</div>
                    </div>
                  </div>
                </div>
              )}

              {result && (
                <>
                  {/* 최적 투찰가 Hero */}
                  <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl p-6 text-white shadow-lg">
                    <div className="flex items-center justify-between flex-wrap gap-4">
                      <div>
                        <div className="text-blue-200 text-sm mb-1">
                          AI 최적 투찰가 ({result.mode === 'real' ? '실측 C(15,4) 전수' : '추정 Monte Carlo 30,000회'})
                        </div>
                        {result.optimal && result.optimal.amount ? (
                          <>
                            <div className="text-4xl font-bold tracking-tight">
                              {fmt(result.optimal.amount)}
                              <span className="text-xl ml-2">원</span>
                            </div>
                            <div className="flex items-center gap-4 mt-2 text-blue-100 text-sm">
                              <span>투찰율(기초대비) <strong className="text-white font-mono">{ratePct(result.optimal.rate)}</strong></span>
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

                  {/* 3전략 카드 */}
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
                              <span className="text-gray-500">투찰율(기초대비)</span>
                              <span className="font-mono">{ratePct(s.rate)}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                              <span className="text-gray-500">평균 순위</span>
                              <span className="font-semibold">{s.avg_rank?.toFixed(1) ?? '-'}위</span>
                            </div>
                            {s.expected_profit != null && s.expected_profit > 0 && (
                              <div className="flex justify-between text-xs pt-1 border-t border-dashed">
                                <span className="text-gray-500">기대이익</span>
                                <span className="font-mono font-semibold text-emerald-600">
                                  {s.expected_profit >= 1e8
                                    ? (s.expected_profit / 1e8).toFixed(1) + '억'
                                    : (s.expected_profit / 1e4).toFixed(0) + '만원'}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}

              {simulateMut.isError && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  {ctx?.base_amount === 0
                    ? '기초금액 정보가 없어 시뮬레이션을 실행할 수 없습니다.'
                    : '시뮬레이션 실행 중 오류가 발생했습니다.'}
                  <button onClick={() => simulateMut.mutate({})} className="ml-auto text-xs underline">재시도</button>
                </div>
              )}

              {/* ── 실증 낙찰 분포 (collapsible) ── */}
              {agencyHistogram && agencyHistogram.data_source !== 'none' && (
                <Collapsible
                  title="실증 낙찰 분포"
                  icon={Award}
                  iconColor="text-emerald-500"
                  defaultOpen={true}
                  badge={agencyHistogram.data_source === 'agency' ? `기관 ${agencyHistogram.inpo21c_n.toLocaleString()}건` : '전국 평균'}
                >
                  <div className="pt-3">
                    <AgencyWinHistogramChart data={agencyHistogram} />
                    {agencyHistogram.top_zones.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-dashed text-xs text-gray-500">
                        <span className="font-semibold text-gray-700">분석:</span>{' '}
                        {agencyHistogram.data_source === 'agency' ? '이 기관에서' : '전국 평균 기준'}
                        {' '}낙찰 확률이 가장 높은 투찰율은{' '}
                        <strong className="text-emerald-700 font-mono">
                          {(agencyHistogram.top_zones[0].rate * 100).toFixed(4)}%
                        </strong>
                        {` 구간으로, ${agencyHistogram.top_zones[0].total_count}건 중 ${agencyHistogram.top_zones[0].win_count}건 낙찰 `}
                        <strong className="text-emerald-700">
                          ({(agencyHistogram.top_zones[0].win_rate * 100).toFixed(1)}%)
                        </strong>
                        {` 실적이 있습니다.`}
                      </div>
                    )}
                  </div>
                </Collapsible>
              )}

              {/* ── AI 낙찰확률 곡선 (collapsible) ── */}
              {winProbCurveData && (
                <Collapsible
                  title="AI 낙찰확률 곡선"
                  icon={TrendingUp}
                  iconColor="text-blue-500"
                  defaultOpen={false}
                  badge="LightGBM"
                >
                  <div className="pt-3">
                    <WinProbCurveChart data={winProbCurveData} />
                    {winProbCurveData.curve.length > 0 && (() => {
                      const floorBid = winProbCurveData.floor_rate * winProbCurveData.srate
                      const validCurve = winProbCurveData.curve.filter(p => p.bid_rate >= floorBid)
                      const bestValid = validCurve.length
                        ? validCurve.reduce((a, b) => a.win_prob > b.win_prob ? a : b)
                        : winProbCurveData.curve.reduce((a, b) => a.win_prob > b.win_prob ? a : b)
                      return (
                        <div className="mt-3 pt-3 border-t border-dashed text-xs text-gray-500">
                          <span className="font-semibold text-gray-700">분석:</span>{' '}
                          모델 예측 기준 낙찰 확률 최고 투찰율은{' '}
                          <strong className="text-blue-700 font-mono">
                            {(bestValid.bid_rate * 100).toFixed(4)}%
                          </strong>
                          {` (P=${(bestValid.win_prob * 100).toFixed(2)}%). `}
                          경쟁사 {winProbCurveData.n_competitors}사, 사정율 {(winProbCurveData.srate * 100).toFixed(4)}% 기준.
                        </div>
                      )
                    })()}
                  </div>
                </Collapsible>
              )}

              {/* ── 사정율 & 경쟁 환경 (collapsible) ── */}
              {ctx && (
                <Collapsible
                  title="사정율 & 경쟁 환경 분석"
                  icon={BarChart3}
                  iconColor="text-violet-500"
                  defaultOpen={false}
                >
                  <div className="pt-3 grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div className="space-y-3">
                      <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">사정율(예정가격) 예측</div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-500">예측 사정율 (중심)</span>
                        <span className="text-2xl font-bold text-blue-700 font-mono">{pct(ctx.srate_center)}</span>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>표준편차</span>
                        <span className="font-mono">{pct(ctx.srate_std, 3)}</span>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>예측 예정가격</span>
                        <span className="font-mono font-semibold text-blue-600">
                          {fmt(Math.round(ctx.base_amount * ctx.srate_center))}원
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>낙찰하한가 (추정)</span>
                        <span className="font-mono font-semibold text-red-600">
                          {fmt(Math.round(ctx.base_amount * ctx.srate_center * ctx.floor_rate))}원
                        </span>
                      </div>
                      {ctx.agency_srate_profile && (
                        <div className="mt-2 pt-2 border-t border-dashed space-y-1.5">
                          <div className="text-xs font-semibold text-gray-500">기관별 세분화 프로파일</div>
                          <div className="flex justify-between text-xs text-gray-500">
                            <span>블렌딩 중심</span>
                            <span className="font-mono">{ctx.agency_srate_profile.blended_center ? pct(ctx.agency_srate_profile.blended_center) : '-'}</span>
                          </div>
                          <div className="flex justify-between text-xs text-gray-500">
                            <span>신뢰도</span>
                            <span className={cn('font-mono font-semibold', (ctx.agency_srate_profile.confidence || 0) >= 0.5 ? 'text-emerald-600' : 'text-amber-600')}>
                              {ctx.agency_srate_profile.confidence ? (ctx.agency_srate_profile.confidence * 100).toFixed(0) + '%' : '-'}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="space-y-3">
                      <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">경쟁 환경</div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">예상 경쟁사 수</span>
                        <span className="font-bold text-gray-800">{ctx.expected_competitors}개사</span>
                      </div>
                      {ctx.pos_weights && (
                        <div>
                          <div className="text-xs text-gray-400 mb-2">예비가격 위치별 추첨 빈도</div>
                          <div className="flex items-end gap-0.5 h-10">
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

                  {/* ── 경쟁사별 투찰 구간 예측 ── */}
                  {competitorPred && competitorPred.competitors.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-dashed">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide flex items-center gap-1">
                          <Users className="w-3.5 h-3.5 text-indigo-500" />
                          경쟁사별 예측 투찰 구간 (P25–P75)
                        </div>
                        <span className={cn(
                          'text-[10px] px-2 py-0.5 rounded-full font-medium',
                          competitorPred.match_type === 'agency' ? 'bg-emerald-50 text-emerald-700' :
                          competitorPred.match_type === 'industry' ? 'bg-amber-50 text-amber-700' :
                          'bg-gray-50 text-gray-500'
                        )}>
                          {competitorPred.match_type === 'agency' ? `기관 매칭 (${competitorPred.data_points}개사)` :
                           competitorPred.match_type === 'industry' ? `공종 전국 (${competitorPred.data_points}개사)` :
                           `전국 (${competitorPred.data_points}개사)`}
                        </span>
                      </div>
                      <div className="space-y-2">
                        {competitorPred.competitors.slice(0, 12).map((c, i) => {
                          const aggrColor = c.aggression === 'aggressive' ? 'text-red-600' :
                            c.aggression === 'conservative' ? 'text-blue-600' :
                            c.aggression === 'volatile' ? 'text-amber-600' : 'text-gray-500'
                          const aggrLabel = c.aggression === 'aggressive' ? '고가' :
                            c.aggression === 'conservative' ? '저가' :
                            c.aggression === 'volatile' ? '변동' : '균형'
                          const rangeWidth = c.p75_pct != null && c.p25_pct != null ? (c.p75_pct - c.p25_pct) : 0
                          // 시각화: 87%~95% 범위 기준으로 bar 위치 계산
                          const SCALE_MIN = 87, SCALE_MAX = 95
                          const leftPct = c.p25_pct != null ? Math.max(0, ((c.p25_pct - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)) * 100) : 0
                          const widthPct = Math.max(1, (rangeWidth / (SCALE_MAX - SCALE_MIN)) * 100)
                          return (
                            <div key={i} className="group">
                              <div className="flex items-center gap-2 text-xs mb-0.5">
                                <span className="w-4 text-gray-300 shrink-0">{i + 1}</span>
                                <span className="w-28 truncate text-gray-700 font-medium shrink-0" title={c.company_name}>{c.company_name}</span>
                                <div className="flex-1 relative h-4 bg-gray-100 rounded overflow-hidden">
                                  <div
                                    className="absolute top-0 h-full bg-indigo-200 rounded"
                                    style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                                  />
                                  {c.p50_pct != null && (
                                    <div
                                      className="absolute top-0 h-full w-0.5 bg-indigo-600"
                                      style={{ left: `${Math.max(0, ((c.p50_pct - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)) * 100)}%` }}
                                    />
                                  )}
                                </div>
                                <span className="font-mono text-indigo-700 w-20 text-right shrink-0">
                                  {c.p25_pct?.toFixed(4)}%~{c.p75_pct?.toFixed(4)}%
                                </span>
                                <span className={cn('w-8 text-right shrink-0 font-semibold', aggrColor)}>{aggrLabel}</span>
                              </div>
                              <div className="hidden group-hover:flex ml-6 text-[10px] text-gray-400 gap-3">
                                <span>평균 {c.avg_rate_pct.toFixed(4)}%</span>
                                <span>σ {c.std_pct?.toFixed(4) ?? '-'}%</span>
                                <span>투찰 {c.total_bids}회</span>
                                {c.wins > 0 && <span className="text-emerald-600">낙찰 {c.wins}회</span>}
                                {c.last_seen && <span>최근 {c.last_seen}</span>}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                      <div className="mt-2 flex items-center gap-4 text-[10px] text-gray-400">
                        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 bg-indigo-200 rounded" /> P25–P75 구간</span>
                        <span className="flex items-center gap-1"><span className="inline-block w-0.5 h-3 bg-indigo-600" /> 중앙값(P50)</span>
                        <span className="ml-auto">87% ─────── 95%</span>
                      </div>
                    </div>
                  )}
                </Collapsible>
              )}

              {/* ── 상세 시뮬레이션 결과 (collapsible) ── */}
              {result && (
                <Collapsible
                  title="상세 시뮬레이션 분석"
                  icon={BarChart3}
                  iconColor="text-amber-500"
                  defaultOpen={false}
                  badge={result.mode === 'real' ? 'C(15,4) 전수' : 'Monte Carlo'}
                >
                  <div className="pt-3">
                    <div className="flex border-b mb-4">
                      {([['zones', '구간별 낙찰확률'], ['hist', '예정가격 분포'], ['combo', '조합 분석']] as const).map(([t, label]) => (
                        <button
                          key={t}
                          onClick={() => setActiveTab(t)}
                          className={cn('px-4 py-2.5 text-sm font-medium border-b-2 transition-colors', activeTab === t ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700')}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    {activeTab === 'zones' && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-gray-700">상위 낙찰 구간</span>
                          <span className="text-xs text-gray-400">전체 {result.all_zones.length}개 구간 스캔</span>
                        </div>
                        <ZoneTable zones={result.top_zones} baseAmount={result.base_amount} />
                        <details className="mt-3">
                          <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
                            전체 구간 보기 ({result.all_zones.length}개)
                          </summary>
                          <div className="mt-2"><ZoneTable zones={result.all_zones} baseAmount={result.base_amount} /></div>
                        </details>
                      </div>
                    )}
                    {activeTab === 'hist' && (
                      <div className="space-y-3">
                        <div className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                          예정가격 사정율 분포
                          <span className="text-xs font-normal text-gray-400">({result.mode === 'real' ? 'C(15,4)=1,365 전수' : 'Monte Carlo 30,000회'})</span>
                        </div>
                        <HistogramChart data={result.histogram} optimalRate={result.optimal?.srate} />
                        <div className="flex justify-between text-xs text-gray-400 mt-1">
                          <span>← 낮은 사정율</span><span>높은 사정율 →</span>
                        </div>
                        <div className="grid grid-cols-4 gap-3 mt-4 text-xs">
                          {['P10', 'P25', 'P50', 'P90'].map((label, pi) => {
                            const val = result.histogram[Math.floor(result.histogram.length * [0.1, 0.25, 0.5, 0.9][pi])]?.bin_center
                            return (
                              <div key={label} className="bg-gray-50 rounded-lg p-2.5">
                                <div className="text-gray-400">{label}</div>
                                <div className="font-mono font-semibold mt-0.5">{val ? ratePct(val) : '-'}</div>
                              </div>
                            )
                          })}
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
                                    <td className="py-1 px-2 font-mono text-indigo-600">{c.combo.map(n => `#${n}`).join(' ')}</td>
                                  )}
                                  <td className="py-1 px-2 text-right font-mono">{fmt(c.amount)}</td>
                                  <td className="py-1 px-2 text-right font-mono">{ratePct(c.rate)}</td>
                                  <td className="py-1 px-2 text-right">{(c.prob * 100).toFixed(3)}%</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                </Collapsible>
              )}

              {/* ── 실측 모드 / 재시뮬레이션 (collapsible) ── */}
              {bidId && ctx && (
                <Collapsible
                  title="실측 모드로 재시뮬레이션"
                  icon={Zap}
                  iconColor="text-amber-500"
                  defaultOpen={false}
                  badge="예비가격 15개 입수 후"
                >
                  <div className="pt-3 space-y-4">
                    <div className="flex items-center gap-3 bg-amber-50 border border-amber-100 rounded-lg p-3 text-xs text-amber-700">
                      <Info className="w-4 h-4 shrink-0" />
                      <span>개찰 전 예비가격 15개를 입수했다면 실측 모드로 재시뮬레이션하세요. C(15,4)=1,365 전수 열거로 정확도가 크게 향상됩니다.</span>
                    </div>

                    <div className="flex items-center bg-gray-100 rounded-lg p-0.5 w-fit">
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

                    {mode === 'real' && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-gray-500">예비가격 15개 직접 입력 (원 단위)</span>
                          <span className={cn('font-semibold', realCount === 15 ? 'text-emerald-600' : 'text-amber-600')}>{realCount}/15 입력됨</span>
                        </div>
                        <YegaGrid values={yegaInputs} onChange={setYegaInputs} baseAmount={ctx.base_amount} />
                      </div>
                    )}

                    {/* 경쟁사 투찰률 입력 */}
                    <div className="space-y-2">
                      <div className="text-xs font-semibold text-gray-600">경쟁사 투찰률 입력 (선택)</div>
                      <div className="text-xs text-gray-400">info21c에서 확인한 경쟁사 투찰률을 입력하면 더 정확한 낙찰확률을 계산합니다.</div>
                      <div className="relative">
                        <textarea
                          value={competitorRateText}
                          onChange={e => setCompetitorRateText(e.target.value)}
                          placeholder={'예) 90.234\n89.876\n91.102\n...'}
                          rows={4}
                          className="w-full border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-violet-400 resize-none"
                        />
                        {competitorRateText && (
                          <button onClick={() => setCompetitorRateText('')} className="absolute top-2 right-2 text-gray-300 hover:text-gray-500">
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                      {parsedCompetitorRates() && (
                        <div className="text-xs text-violet-700 bg-violet-50 rounded p-2 flex flex-wrap gap-1">
                          {parsedCompetitorRates()!.map((r, i) => (
                            <span key={i} className="font-mono bg-violet-100 px-1.5 py-0.5 rounded">{(r * 100).toFixed(4)}%</span>
                          ))}
                        </div>
                      )}
                    </div>

                    <button
                      onClick={() => simulateMut.mutate({})}
                      disabled={!canReSimulate || simulateMut.isPending}
                      className="w-full py-3 bg-amber-600 text-white rounded-lg font-semibold text-sm hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all"
                    >
                      {simulateMut.isPending ? (
                        <>
                          <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          재시뮬레이션 중...
                        </>
                      ) : (
                        <>
                          <Zap className="w-4 h-4" />
                          {mode === 'real' ? '실측 C(15,4) 재시뮬레이션' : '추정 모드 재시뮬레이션'}
                        </>
                      )}
                    </button>
                  </div>
                </Collapsible>
              )}

              {/* ── 투찰 결정 기록 ── */}
              {ctx && (
                <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
                  <div className="px-5 py-4 border-b bg-amber-50 flex items-center gap-2">
                    <BookOpen className="w-4 h-4 text-amber-600" />
                    <span className="font-semibold text-sm text-amber-800">투찰 결정 기록</span>
                    <span className="text-xs text-amber-600 ml-1">— 개찰 결과와 함께 AI 모델 피드백에 활용됩니다</span>
                  </div>

                  {journalRecord?.result ? (
                    <div className="p-5 space-y-4">
                      <div className={cn(
                        'flex items-center gap-2 p-3 rounded-lg text-sm font-semibold',
                        journalRecord.result === '낙찰' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-50 text-gray-700'
                      )}>
                        {journalRecord.result === '낙찰' ? <Trophy className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}
                        <span>결과 기록 완료: <strong>{journalRecord.result}</strong></span>
                        <span className="text-xs font-normal opacity-60 ml-1">저널 #{journalRecord.id}</span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                        {journalRecord.rate_gap !== null && (
                          <div className={cn('rounded p-2.5', Math.abs(journalRecord.rate_gap) < 0.005 ? 'bg-emerald-50' : 'bg-amber-50')}>
                            <div className="text-gray-400">투찰률 편차</div>
                            <div className={cn('font-mono font-semibold mt-0.5', Math.abs(journalRecord.rate_gap) < 0.005 ? 'text-emerald-700' : 'text-amber-700')}>
                              {journalRecord.rate_gap > 0 ? '+' : ''}{(journalRecord.rate_gap * 100).toFixed(4)}%
                            </div>
                          </div>
                        )}
                        {journalRecord.srate_error !== null && (
                          <div className={cn('rounded p-2.5', Math.abs(journalRecord.srate_error) < 0.003 ? 'bg-emerald-50' : 'bg-amber-50')}>
                            <div className="text-gray-400">사정율 예측 오차</div>
                            <div className={cn('font-mono font-semibold mt-0.5', Math.abs(journalRecord.srate_error) < 0.003 ? 'text-emerald-700' : 'text-amber-700')}>
                              {journalRecord.srate_error > 0 ? '+' : ''}{(journalRecord.srate_error * 100).toFixed(4)}%
                            </div>
                          </div>
                        )}
                        {journalRecord.our_rank !== null && (
                          <div className="bg-gray-50 rounded p-2.5">
                            <div className="text-gray-400">투찰 순위</div>
                            <div className="font-semibold mt-0.5">{journalRecord.our_rank}위 / {journalRecord.total_bidders ?? '-'}개사</div>
                          </div>
                        )}
                        {journalRecord.actual_srate !== null && (
                          <div className="bg-gray-50 rounded p-2.5">
                            <div className="text-gray-400">실제 사정율</div>
                            <div className="font-mono font-semibold mt-0.5">{ratePct(journalRecord.actual_srate)}</div>
                          </div>
                        )}
                      </div>
                    </div>

                  ) : journalRecord ? (
                    <div className="p-5 space-y-4">
                      <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 p-3 rounded-lg text-sm">
                        <CheckCircle2 className="w-4 h-4 shrink-0" />
                        <span>투찰 결정 기록 완료 (저널 #{journalRecord.id})</span>
                      </div>
                      <div className="grid grid-cols-3 gap-3 text-xs">
                        <div className="bg-gray-50 rounded p-2.5">
                          <div className="text-gray-400">실제 투찰률</div>
                          <div className="font-mono font-semibold mt-0.5">{journalRecord.submitted_rate ? ratePct(journalRecord.submitted_rate) : '-'}</div>
                        </div>
                        <div className="bg-gray-50 rounded p-2.5">
                          <div className="text-gray-400">AI 추천률</div>
                          <div className="font-mono font-semibold mt-0.5">{journalRecord.recommended_rate ? ratePct(journalRecord.recommended_rate) : '-'}</div>
                        </div>
                        <div className="bg-gray-50 rounded p-2.5">
                          <div className="text-gray-400">선택 전략</div>
                          <div className="font-semibold mt-0.5">{journalRecord.strategy_chosen || '-'}</div>
                        </div>
                      </div>
                      <button
                        onClick={() => setShowResultPanel(p => !p)}
                        className="w-full flex items-center justify-between px-4 py-3 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
                      >
                        <div className="flex items-center gap-2">
                          <ClipboardCheck className="w-4 h-4" />
                          개찰 결과 입력
                        </div>
                        <span className="text-xs opacity-80">{showResultPanel ? '접기 ▲' : '펼치기 ▼'}</span>
                      </button>
                      {showResultPanel && (
                        <div className="border rounded-lg p-4 space-y-4">
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="text-xs text-gray-500 mb-1 block">결과 *</label>
                              <select
                                value={resultForm.result}
                                onChange={e => setResultForm(f => ({ ...f, result: e.target.value as typeof f.result }))}
                                className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                              >
                                <option value="낙찰">낙찰</option>
                                <option value="패찰">패찰</option>
                                <option value="무효">무효</option>
                                <option value="취소">취소</option>
                              </select>
                            </div>
                            <div>
                              <label className="text-xs text-gray-500 mb-1 block">실제 사정율 (%)</label>
                              <input
                                value={resultForm.actual_srate}
                                onChange={e => setResultForm(f => ({ ...f, actual_srate: e.target.value }))}
                                placeholder="예) 90.234"
                                className="w-full border rounded px-2 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"
                              />
                            </div>
                            <div>
                              <label className="text-xs text-gray-500 mb-1 block">우리 순위</label>
                              <input
                                value={resultForm.our_rank}
                                onChange={e => setResultForm(f => ({ ...f, our_rank: e.target.value }))}
                                placeholder="예) 3"
                                type="number"
                                className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                              />
                            </div>
                            <div>
                              <label className="text-xs text-gray-500 mb-1 block">총 투찰업체 수</label>
                              <input
                                value={resultForm.total_bidders}
                                onChange={e => setResultForm(f => ({ ...f, total_bidders: e.target.value }))}
                                placeholder="예) 12"
                                type="number"
                                className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                              />
                            </div>
                          </div>
                          <details>
                            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">낙찰자 정보 (선택)</summary>
                            <div className="mt-3 grid grid-cols-2 gap-3">
                              <div>
                                <label className="text-xs text-gray-500 mb-1 block">낙찰률 (%)</label>
                                <input value={resultForm.winner_rate} onChange={e => setResultForm(f => ({ ...f, winner_rate: e.target.value }))} placeholder="예) 90.234" className="w-full border rounded px-2 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500 mb-1 block">낙찰금액 (원)</label>
                                <input value={resultForm.winner_amount} onChange={e => setResultForm(f => ({ ...f, winner_amount: e.target.value }))} placeholder="원 단위" className="w-full border rounded px-2 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500 mb-1 block">낙찰업체 사업자번호</label>
                                <input value={resultForm.winner_biz_no} onChange={e => setResultForm(f => ({ ...f, winner_biz_no: e.target.value }))} placeholder="000-00-00000" className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500 mb-1 block">낙찰업체명</label>
                                <input value={resultForm.winner_name} onChange={e => setResultForm(f => ({ ...f, winner_name: e.target.value }))} placeholder="업체명" className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
                              </div>
                            </div>
                          </details>
                          <div>
                            <label className="text-xs text-gray-500 mb-1 block">메모</label>
                            <textarea
                              value={resultForm.note}
                              onChange={e => setResultForm(f => ({ ...f, note: e.target.value }))}
                              placeholder="특이사항, 후기 등..."
                              rows={2}
                              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
                            />
                          </div>
                          <button
                            onClick={() => resultMut.mutate()}
                            disabled={resultMut.isPending}
                            className="w-full py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2"
                          >
                            {resultMut.isPending ? '저장 중...' : (<><ClipboardCheck className="w-4 h-4" />개찰 결과 저장</>)}
                          </button>
                          {resultMut.isError && (
                            <div className="text-xs text-red-600 flex items-center gap-1 bg-red-50 rounded p-2">
                              <AlertCircle className="w-3 h-3 shrink-0" />저장 중 오류가 발생했습니다.
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                  ) : (
                    <div className="p-5 space-y-4">
                      <div className="text-xs text-gray-500 leading-relaxed bg-amber-50 border border-amber-100 rounded-lg p-3">
                        실제 투찰한 투찰률을 기록하세요. 개찰 결과와 함께 AI 모델 피드백에 활용됩니다.
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs text-gray-500 mb-1 block">실제 투찰률 (%) *</label>
                          <div className="relative">
                            <input
                              value={submittedRateInput}
                              onChange={e => setSubmittedRateInput(e.target.value)}
                              placeholder={result?.optimal ? (result.optimal.rate * 100).toFixed(4) : '예) 90.2345'}
                              className="w-full border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-amber-400"
                            />
                            {result?.optimal && !submittedRateInput && (
                              <button
                                onClick={() => setSubmittedRateInput((result.optimal!.rate * 100).toFixed(4))}
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-blue-600 hover:text-blue-800 font-medium"
                              >
                                최적값 사용
                              </button>
                            )}
                          </div>
                        </div>
                        <div>
                          <label className="text-xs text-gray-500 mb-1 block">선택 전략</label>
                          <select
                            value={strategyChosen}
                            onChange={e => setStrategyChosen(e.target.value)}
                            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                          >
                            <option value="aggressive">공격형</option>
                            <option value="balanced">균형형</option>
                            <option value="conservative">보수형</option>
                            <option value="custom">직접 입력</option>
                          </select>
                        </div>
                      </div>
                      <button
                        onClick={() => journalMut.mutate()}
                        disabled={!submittedRateInput || journalMut.isPending}
                        className="w-full py-2.5 bg-amber-600 text-white rounded-lg text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 flex items-center justify-center gap-2"
                      >
                        {journalMut.isPending ? '기록 중...' : (<><BookOpen className="w-4 h-4" />투찰 결정 기록</>)}
                      </button>
                      {journalMut.isError && (
                        <div className="text-xs text-red-600 flex items-center gap-1 bg-red-50 rounded p-2">
                          <AlertCircle className="w-3 h-3 shrink-0" />기록 중 오류가 발생했습니다.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* 하단 - 공고 재선택 */}
              <div className="flex justify-between items-center pt-2">
                <button
                  onClick={() => goStep(1)}
                  className="flex items-center gap-2 px-4 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50"
                >
                  <ChevronLeft className="w-4 h-4" />
                  공고 재선택
                </button>
                <button
                  onClick={resetAll}
                  className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                >
                  <Search className="w-3.5 h-3.5" />
                  새 공고 시작
                </button>
              </div>
            </div>
          )}

          {/* ctx 없을 때 fallback */}
          {step === 2 && !ctx && !ctxLoading && (
            <div className="bg-white rounded-xl border p-10 text-center text-gray-400 text-sm shadow-sm">
              공고 데이터를 불러올 수 없습니다.
              <button onClick={() => goStep(1)} className="block mx-auto mt-3 text-blue-600 hover:underline text-xs">처음으로</button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
