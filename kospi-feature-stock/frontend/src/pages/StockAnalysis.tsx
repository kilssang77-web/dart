import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  Search, TrendingUp, TrendingDown, Minus, AlertTriangle,
  CheckCircle, Target, ShieldCheck, Zap, BarChart2, X, FileText, Newspaper, BookOpen, ExternalLink,
} from 'lucide-react'
import { stocksApi } from '@/api/stocks'
import { featuresApi } from '@/api/features'
import { MarketBadge } from '@/components/ui/Badge'
import { CandleChart } from '@/components/charts/CandleChart'
import type { ChartEvent } from '@/components/charts/CandleChart'
import { fmt, pctColor } from '@/lib/utils'
import type { StockAnalysis, Stock } from '@/types'

function fmtShares(v: number): string {
  const a = Math.abs(v); const s = v >= 0 ? '+' : '-'
  if (a >= 10_000_000) return `${s}${(a / 10_000_000).toFixed(1)}천만주`
  if (a >= 1_000_000)  return `${s}${(a / 1_000_000).toFixed(1)}백만주`
  if (a >= 10_000)     return `${s}${(a / 10_000).toFixed(1)}만주`
  return `${s}${a.toLocaleString()}주`
}

// ── 방향 아이콘 ───────────────────────────────────────────────────────────────
function DirIcon({ dir, size = 16 }: { dir: string; size?: number }) {
  if (dir === '상승') return <TrendingUp  size={size} className="text-red-400" />
  if (dir === '하락') return <TrendingDown size={size} className="text-blue-400" />
  return <Minus size={size} className="text-[var(--muted)]" />
}

function dirColor(dir: string) {
  if (dir === '상승') return 'text-red-400'
  if (dir === '하락') return 'text-blue-400'
  return 'text-[var(--muted)]'
}

// ── 신뢰도 바 ─────────────────────────────────────────────────────────────────
function ConfBar({ value }: { value: number }) {
  const pct   = Math.round(value * 100)
  const color = value >= 0.7 ? 'bg-green-400' : value >= 0.5 ? 'bg-yellow-400' : 'bg-[var(--muted)]'
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular text-[var(--muted)] w-8">신뢰 {pct}%</span>
    </div>
  )
}

// ── 예측 카드 ─────────────────────────────────────────────────────────────────
function PredCard({ pred, current }: {
  pred: StockAnalysis['predictions']['short']
  current: number
}) {
  const isUp = pred.direction === '상승'
  const isDn = pred.direction === '하락'
  return (
    <div className={clsx(
      'bg-[var(--card)] border rounded-xl p-4 space-y-3',
      isUp ? 'border-red-500/30' : isDn ? 'border-blue-500/30' : 'border-[var(--border)]',
    )}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-[var(--fg)]">{pred.label}</span>
        <div className={clsx('flex items-center gap-1 text-sm font-bold', dirColor(pred.direction))}>
          <DirIcon dir={pred.direction} size={14} />
          {pred.direction}
        </div>
      </div>

      {/* 가격 범위 */}
      <div className="grid grid-cols-3 gap-1.5 text-center">
        <div className="bg-blue-500/10 rounded-lg p-2 border border-blue-500/20">
          <div className="text-xs text-blue-400">하단</div>
          <div className="text-xs font-bold tabular text-blue-400 mt-0.5">{pred.low.toLocaleString()}</div>
          <div className="text-xs text-blue-400/70 tabular">
            {(((pred.low - current) / current) * 100).toFixed(1)}%
          </div>
        </div>
        <div className={clsx('rounded-lg p-2 border', isUp ? 'bg-red-500/10 border-red-500/30' : isDn ? 'bg-blue-500/5 border-blue-500/20' : 'bg-[var(--bg)] border-[var(--border)]')}>
          <div className="text-xs text-[var(--muted)]">중간</div>
          <div className="text-sm font-bold tabular text-[var(--fg)] mt-0.5">{pred.mid.toLocaleString()}</div>
          <div className={clsx('text-xs tabular', pctColor((pred.mid - current) / current * 100))}>
            {(((pred.mid - current) / current) * 100).toFixed(1)}%
          </div>
        </div>
        <div className="bg-red-500/10 rounded-lg p-2 border border-red-500/20">
          <div className="text-xs text-red-400">상단</div>
          <div className="text-xs font-bold tabular text-red-400 mt-0.5">{pred.high.toLocaleString()}</div>
          <div className="text-xs text-red-400/70 tabular">
            +{(((pred.high - current) / current) * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      <ConfBar value={pred.confidence} />

      {/* 분석 근거 */}
      <div className="space-y-1">
        {pred.reasons.map((r, i) => (
          <div key={i} className="flex items-start gap-1.5 text-xs text-[var(--muted)]">
            <span className="mt-0.5 shrink-0 text-cyan-400">•</span>
            <span>{r}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 매매 전략 카드 ────────────────────────────────────────────────────────────
function TargetCard({
  label, target, icon, color, borderColor, bgColor, hasPurchase,
}: {
  label: string
  target: StockAnalysis['targets']['aggressive']
  icon: React.ReactNode
  color: string
  borderColor: string
  bgColor: string
  hasPurchase: boolean
}) {
  return (
    <div className={clsx('rounded-xl border p-4 space-y-3', borderColor, bgColor)}>
      <div className="flex items-center gap-2">
        <span className={clsx('p-1.5 rounded-lg', bgColor, borderColor, 'border')}>{icon}</span>
        <div>
          <div className={clsx('text-sm font-bold', color)}>{label}</div>
          <div className="text-xs text-[var(--muted)] mt-0.5">{target.desc}</div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-1.5 text-center">
        <div>
          <div className="text-xs text-[var(--muted)]">매수가</div>
          <div className="text-xs font-semibold tabular text-[var(--fg)] mt-0.5">{target.buy.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-xs text-red-400">목표가</div>
          <div className="text-xs font-semibold tabular text-red-400 mt-0.5">{target.target.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-xs text-blue-400">손절가</div>
          <div className="text-xs font-semibold tabular text-blue-400 mt-0.5">{target.stop.toLocaleString()}</div>
        </div>
      </div>
      <div className={clsx('text-center text-xs font-semibold', color)}>R:R = {target.rr}</div>
    </div>
  )
}

// ── ATR 기반 매도 전략 상수 ──────────────────────────────────────────────────
const ACTION_LABEL: Record<string, string> = {
  STOP_LOSS:          '즉시 손절',
  HOLD_TRAIL:         '보유 유지',
  PARTIAL_EXIT:       '부분 익절',
  PARTIAL_EXIT_LARGE: '적극 익절',
  FULL_EXIT:          '전량 매도',
}
const ACTION_DESC: Record<string, string> = {
  STOP_LOSS:          '손절 기준 이탈 — 즉시 손절 검토 권장',
  HOLD_TRAIL:         '신호 긍정적 — 트레일링 스탑 유지하며 보유',
  PARTIAL_EXIT:       '조건 다소 약화 — 부분 익절 후 나머지 보유',
  PARTIAL_EXIT_LARGE: '신호 부정적 — 대부분 익절 권장',
  FULL_EXIT:          '다수 부정 신호 — 전량 매도 권장',
}
const ACTION_COLOR: Record<string, string> = {
  STOP_LOSS:          'text-red-400',
  HOLD_TRAIL:         'text-green-400',
  PARTIAL_EXIT:       'text-orange-400',
  PARTIAL_EXIT_LARGE: 'text-yellow-400',
  FULL_EXIT:          'text-blue-400',
}
const ACTION_BG: Record<string, string> = {
  STOP_LOSS:          'bg-red-500/5 border-red-500/30',
  HOLD_TRAIL:         'bg-green-500/5 border-green-500/30',
  PARTIAL_EXIT:       'bg-orange-500/5 border-orange-500/30',
  PARTIAL_EXIT_LARGE: 'bg-amber-500/5 border-amber-500/30',
  FULL_EXIT:          'bg-blue-500/5 border-blue-500/30',
}

// ── 기술 지표 셀 ─────────────────────────────────────────────────────────────
function TechCell({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5 p-2.5 bg-[var(--bg)] rounded-lg">
      <span className="text-xs text-[var(--muted)]">{label}</span>
      <span className={clsx('text-xs font-bold tabular', color ?? 'text-[var(--fg)]')}>{value}</span>
      {sub && <span className="text-xs text-[var(--muted)]">{sub}</span>}
    </div>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export function StockAnalysis() {
  const [inputCode,     setInputCode]     = useState('')
  const [query,         setQuery]         = useState('')
  const [selCode,       setSelCode]       = useState('')
  const [selName,       setSelName]       = useState('')
  const [hasPurchase,   setHasPurchase]   = useState(false)
  const [purchaseInput, setPurchaseInput] = useState('')
  const [analyzing,     setAnalyzing]     = useState(false)
  const [purchasePrice, setPurchasePrice] = useState<number | undefined>()
  const [showSearch,    setShowSearch]    = useState(false)
  const [analysisKey,   setAnalysisKey]   = useState(0)

  const { data: searchResults } = useQuery({
    queryKey:  ['analysis-search', query],
    queryFn:   () => stocksApi.search(query),
    enabled:   query.length >= 1,
    staleTime: 60_000,
  })

  const { data: analysis, isLoading, isError: analysisError, refetch } = useQuery({
    queryKey:  ['analysis', selCode, purchasePrice, analysisKey],
    queryFn:   () => stocksApi.getAnalysis(selCode, purchasePrice),
    enabled:   analyzing && !!selCode,
    staleTime: 0,
  })

  const { data: dailyBars } = useQuery({
    queryKey:  ['daily-bars', selCode],
    queryFn:   () => stocksApi.getDailyBars(selCode, 120),
    enabled:   !!selCode,
    staleTime: 300_000,
  })

  const { data: chartEvents } = useQuery({
    queryKey:  ['features-chart', selCode],
    queryFn:   () =>
      featuresApi.list({ code: selCode, hours: 120 * 24, limit: 200, dedupe: false })
        .then((evts) => evts.map((e): ChartEvent => ({
          date:  e.detected_at?.slice(0, 10) ?? '',
          type:  e.event_type,
          score: e.signal_score ?? 0,
        }))),
    enabled:   !!selCode,
    staleTime: 300_000,
  })

  function selectStock(stock: Stock) {
    setSelCode(stock.code)
    setSelName(stock.name)
    setInputCode(`${stock.name} (${stock.code})`)
    setShowSearch(false)
    setAnalyzing(false)
  }

  function handleAnalyze() {
    if (!selCode) return
    const pp = hasPurchase && purchaseInput ? parseFloat(purchaseInput.replace(/,/g, '')) : undefined
    setPurchasePrice(pp)
    setAnalysisKey((k) => k + 1)
    setAnalyzing(true)
  }

  const trendDirLabel = analysis?.technical?.trend_dir ?? ''
  const isUpTrend  = ['strong_up', 'up', 'up_mild'].includes(trendDirLabel)
  const isDnTrend  = ['strong_down', 'down', 'down_mild'].includes(trendDirLabel)
  const trendColor = isUpTrend ? 'text-red-400' : isDnTrend ? 'text-blue-400' : 'text-[var(--muted)]'
  const trendBg    = isUpTrend ? 'bg-red-500/10 border-red-500/30' : isDnTrend ? 'bg-blue-500/10 border-blue-500/30' : 'bg-[var(--border)]/30 border-[var(--border)]'

  return (
    <div className="p-4 space-y-4 max-w-5xl mx-auto">

      {/* ── 입력 폼 ── */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 space-y-4">
        <div className="text-base font-bold text-[var(--fg)] flex items-center gap-2">
          <BarChart2 size={16} className="text-cyan-400" />
          종목 분석
        </div>

        {/* 종목 검색 */}
        <div className="relative">
          <label className="block text-xs text-[var(--muted)] mb-1.5">종목명 또는 코드</label>
          <div className="flex items-center gap-2 px-3 py-2 bg-[var(--bg)] border border-[var(--border)] rounded-lg focus-within:border-cyan-500">
            <Search size={13} className="text-[var(--muted)] shrink-0" />
            <input
              value={inputCode}
              onChange={(e) => {
                setInputCode(e.target.value)
                setQuery(e.target.value)
                setShowSearch(true)
                if (!e.target.value) { setSelCode(''); setSelName('') }
              }}
              onFocus={() => setShowSearch(true)}
              placeholder="삼성전자 or 005930"
              className="flex-1 bg-transparent text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none"
            />
            {inputCode && (
              <button onClick={() => { setInputCode(''); setQuery(''); setSelCode(''); setSelName(''); setShowSearch(false) }}>
                <X size={13} className="text-[var(--muted)] hover:text-[var(--fg)]" />
              </button>
            )}
          </div>

          {/* 검색 드롭다운 */}
          {showSearch && searchResults && searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-[var(--card)] border border-[var(--border)] rounded-xl shadow-lg overflow-hidden max-h-48 overflow-y-auto">
              {searchResults.slice(0, 10).map((s) => (
                <div
                  key={s.code}
                  onClick={() => selectStock(s)}
                  className="flex items-center justify-between px-3 py-2.5 hover:bg-[var(--border)]/30 cursor-pointer text-xs border-b border-[var(--border)]/40 last:border-0"
                >
                  <div>
                    <span className="font-semibold text-[var(--fg)]">{s.name}</span>
                    <span className="text-[var(--muted)] ml-2">{s.code}</span>
                  </div>
                  <MarketBadge market={s.market} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 보유 여부 */}
        <div className="space-y-2">
          <label className="flex items-center gap-2.5 cursor-pointer w-fit">
            <div
              onClick={() => setHasPurchase((v) => !v)}
              className={clsx(
                'w-10 h-5 rounded-full transition-colors relative',
                hasPurchase ? 'bg-cyan-500' : 'bg-[var(--border)]',
              )}
            >
              <div className={clsx('absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform',
                hasPurchase ? 'translate-x-5' : 'translate-x-0.5')} />
            </div>
            <span className="text-sm text-[var(--fg)]">이미 매수한 상태</span>
          </label>
          {hasPurchase && (
            <div className="flex items-center gap-2 pl-12">
              <span className="text-xs text-[var(--muted)]">매수가</span>
              <div className="flex items-center gap-1 px-2.5 py-1.5 bg-[var(--bg)] border border-[var(--border)] rounded-lg focus-within:border-cyan-500">
                <input
                  type="text"
                  value={purchaseInput}
                  onChange={(e) => setPurchaseInput(e.target.value.replace(/[^0-9,]/g, ''))}
                  placeholder="72,000"
                  className="bg-transparent text-sm tabular text-[var(--fg)] w-24 focus:outline-none placeholder:text-[var(--muted)]"
                />
                <span className="text-xs text-[var(--muted)]">원</span>
              </div>
            </div>
          )}
        </div>

        {/* 분석 버튼 */}
        <button
          onClick={handleAnalyze}
          disabled={!selCode || isLoading}
          className={clsx(
            'w-full py-2.5 rounded-xl text-sm font-semibold transition-all',
            selCode
              ? 'bg-cyan-500 hover:bg-cyan-400 text-white'
              : 'bg-[var(--border)] text-[var(--muted)] cursor-not-allowed',
          )}
        >
          {isLoading ? '분석 중…' : '📊 분석 시작'}
        </button>
      </div>

      {/* ── 분석 결과 ── */}
      {analysis && !analysis.error && (
        <div className="space-y-4">

          {/* 종목 헤더 + 현재가 + 추세 */}
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-lg font-bold text-[var(--fg)]">{analysis.name}</h2>
                  {analysis.market && <MarketBadge market={analysis.market} />}
                </div>
                <div className="text-xs text-[var(--muted)] mt-0.5">
                  {analysis.code} {analysis.sector && `· ${analysis.sector}`}
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold tabular text-[var(--fg)]">
                  {analysis.current_price?.toLocaleString()}<span className="text-sm text-[var(--muted)] ml-1">원</span>
                </div>
              </div>
            </div>

            {/* 추세 배지 */}
            <div className={clsx('mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-bold', trendColor, trendBg)}>
              {isUpTrend ? <TrendingUp size={14} /> : isDnTrend ? <TrendingDown size={14} /> : <Minus size={14} />}
              {analysis.technical.trend}
              <span className="text-xs font-normal text-[var(--muted)] ml-1">
                (점수 {analysis.technical.trend_score >= 0 ? '+' : ''}{analysis.technical.trend_score})
              </span>
            </div>

            {/* 기술 지표 그리드 */}
            <div className="mt-3 grid grid-cols-3 sm:grid-cols-6 gap-1.5">
              <TechCell label="MA5"  value={analysis.technical.ma5  ? analysis.technical.ma5.toLocaleString()  : '—'} />
              <TechCell label="MA20" value={analysis.technical.ma20 ? analysis.technical.ma20.toLocaleString() : '—'} />
              <TechCell label="MA60" value={analysis.technical.ma60 ? analysis.technical.ma60.toLocaleString() : '—'} />
              <TechCell label="RSI14" value={analysis.technical.rsi ? analysis.technical.rsi.toFixed(1) : '—'}
                color={analysis.technical.rsi_signal === 'oversold' ? 'text-red-400' : analysis.technical.rsi_signal === 'overbought' ? 'text-blue-400' : undefined}
                sub={analysis.technical.rsi_signal === 'oversold' ? '과매도' : analysis.technical.rsi_signal === 'overbought' ? '과매수' : '정상'}
              />
              <TechCell label="ATR14" value={analysis.technical.atr.toLocaleString()} sub="변동폭(원)" />
              <TechCell label="거래량비" value={`${analysis.technical.vol_ratio.toFixed(1)}x`}
                color={analysis.technical.vol_ratio >= 1.5 ? 'text-red-400' : undefined}
                sub="vs 20일 평균"
              />
            </div>

            {/* 52주 범위 */}
            {analysis.technical.w52_high && analysis.technical.w52_low && (
              <div className="mt-3 pt-3 border-t border-[var(--border)]">
                <div className="flex justify-between text-xs text-[var(--muted)] mb-1">
                  <span>52주 저가 {analysis.technical.w52_low.toLocaleString()}</span>
                  <span>52주 고가 {analysis.technical.w52_high.toLocaleString()}</span>
                </div>
                <div className="relative h-2 bg-[var(--border)] rounded-full">
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 via-transparent to-red-500/20 rounded-full" />
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white border-2 border-cyan-400 rounded-full shadow"
                    style={{ left: `calc(${Math.max(2, Math.min(98, analysis.technical.w52_pct * 100))}% - 6px)` }}
                  />
                </div>
                <div className="text-center text-xs text-cyan-400 mt-1 tabular">
                  52주 내 위치 {(analysis.technical.w52_pct * 100).toFixed(0)}%
                </div>
              </div>
            )}

            {/* 분석 근거 */}
            {analysis.technical.reasons.length > 0 && (
              <div className="mt-3 pt-3 border-t border-[var(--border)] space-y-1">
                {analysis.technical.reasons.map((r, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-xs text-[var(--muted)]">
                    <span className="text-cyan-400 shrink-0 mt-0.5">•</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── 캔들 차트 ── */}
          {dailyBars && dailyBars.length > 0 && (
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
              <div className="text-xs font-semibold text-[var(--muted)] mb-2">일봉 차트 (최근 120일)</div>
              <CandleChart data={dailyBars} height={260} showMA events={chartEvents} />
            </div>
          )}

          {/* ── 보유 중인 경우: P&L + ATR 매도 전략 ── */}
          {analysis.purchase_analysis && (() => {
            const pa  = analysis.purchase_analysis
            const ret = pa.current_return
            const tsRet = ((pa.trailing_stop - pa.purchase_price) / pa.purchase_price * 100)
            return (
              <div className="space-y-3">
                {/* P&L 헤더 */}
                <div className={clsx('bg-[var(--card)] border rounded-xl p-4', ret >= 0 ? 'border-red-500/30' : 'border-blue-500/30')}>
                  <div className="text-sm font-bold text-[var(--fg)] mb-3 flex items-center gap-2">
                    <CheckCircle size={14} className="text-cyan-400" />보유 현황
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <div className="text-xs text-[var(--muted)]">매수가</div>
                      <div className="text-base font-bold tabular text-[var(--fg)] mt-0.5">{pa.purchase_price.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-xs text-[var(--muted)]">현재가</div>
                      <div className="text-base font-bold tabular text-[var(--fg)] mt-0.5">{pa.current_price.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-xs text-[var(--muted)]">수익률</div>
                      <div className={clsx('text-xl font-bold tabular mt-0.5', ret >= 0 ? 'text-red-400' : 'text-blue-400')}>
                        {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                </div>

                {/* STOP_LOSS 경보 */}
                {pa.action === 'STOP_LOSS' && (
                  <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/40 rounded-xl">
                    <AlertTriangle size={14} className="text-red-400 shrink-0" />
                    <span className="text-sm text-red-400 font-semibold">손절 기준 이탈 — 트레일링 스탑({pa.trailing_stop.toLocaleString()}원) 이탈, 즉시 손절 검토 권장</span>
                  </div>
                )}

                {/* ATR 매도 전략 3칸 */}
                <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-2 px-1">
                  <Target size={14} className="text-cyan-400" />ATR 기반 매도 전략
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {/* 행동 권고 */}
                  <div className={clsx('rounded-xl border p-4 space-y-2', ACTION_BG[pa.action] ?? 'bg-[var(--bg)] border-[var(--border)]')}>
                    <div className="text-xs font-semibold text-[var(--muted)]">ML 종합 판단</div>
                    <div className={clsx('text-xl font-extrabold', ACTION_COLOR[pa.action] ?? 'text-[var(--fg)]')}>
                      {ACTION_LABEL[pa.action] ?? pa.action}
                    </div>
                    <div className="text-xs text-[var(--muted)] leading-snug">{ACTION_DESC[pa.action]}</div>
                    <div className="flex items-center gap-1.5 pt-1">
                      <span className="text-xs text-[var(--muted)]">신호점수</span>
                      <span className={clsx('text-sm font-bold tabular', pa.sell_score >= 0 ? 'text-green-400' : 'text-red-400')}>
                        {pa.sell_score >= 0 ? '+' : ''}{pa.sell_score}
                      </span>
                    </div>
                  </div>

                  {/* 트레일링 스탑 */}
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 space-y-2">
                    <div className="text-xs font-semibold text-[var(--muted)]">트레일링 스탑</div>
                    <div className="text-xl font-extrabold tabular text-[var(--fg)]">
                      {pa.trailing_stop.toLocaleString()}<span className="text-sm text-[var(--muted)] ml-1">원</span>
                    </div>
                    <div className="text-xs text-[var(--muted)]">현재가 − ATR×{pa.atr_mult_ts.toFixed(1)}</div>
                    <div className={clsx('text-sm font-bold tabular', tsRet >= 0 ? 'text-red-400' : 'text-blue-400')}>
                      매수가 대비 {tsRet >= 0 ? '+' : ''}{tsRet.toFixed(1)}%
                    </div>
                  </div>

                  {/* 순방향 목표 or 점수 미터 */}
                  {pa.forward_targets.length > 0 ? (
                    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 space-y-2">
                      <div className="text-xs font-semibold text-[var(--muted)]">ATR 목표가 (현재가 기준)</div>
                      {pa.forward_targets.map((t, i) => (
                        <div key={i} className="flex items-center justify-between py-1 border-b border-[var(--border)]/40 last:border-0">
                          <span className="text-xs text-[var(--muted)]">{t.label}</span>
                          <div className="text-right">
                            <span className="text-sm font-bold tabular text-[var(--fg)]">{t.price.toLocaleString()}</span>
                            <span className="text-xs text-red-400 ml-1.5">+{t.ret_pct}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 space-y-2">
                      <div className="text-xs font-semibold text-[var(--muted)]">종합 신호 점수</div>
                      <div className={clsx('text-2xl font-extrabold tabular', pa.sell_score >= 0 ? 'text-green-400' : 'text-red-400')}>
                        {pa.sell_score >= 0 ? '+' : ''}{pa.sell_score}
                      </div>
                      <div className="w-full h-2 bg-[var(--border)] rounded-full overflow-hidden">
                        <div
                          className={clsx('h-full rounded-full', pa.sell_score >= 0 ? 'bg-green-400' : 'bg-red-400')}
                          style={{ width: `${Math.min(100, Math.abs(pa.sell_score))}%` }}
                        />
                      </div>
                      <div className="text-xs text-[var(--muted)]">양수=보유, 음수=매도 권장</div>
                    </div>
                  )}
                </div>
              </div>
            )
          })()}

          {/* ── 주가 예측 (단기/중기/장기) ── */}
          <div>
            <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-2 px-1 mb-3">
              <TrendingUp size={14} className="text-cyan-400" />주가 예측
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <PredCard pred={analysis.predictions.short} current={analysis.current_price} />
              <PredCard pred={analysis.predictions.mid}   current={analysis.current_price} />
              <PredCard pred={analysis.predictions.long}  current={analysis.current_price} />
            </div>
          </div>

          {/* ── 매수 전략 (미보유 시) ── */}
          {!analysis.purchase_analysis && (
            <div>
              <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-2 px-1 mb-3">
                <Target size={14} className="text-cyan-400" />매수 전략 추천
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <TargetCard label="공격형" target={analysis.targets.aggressive}
                  icon={<Zap size={13} className="text-orange-400" />}
                  color="text-orange-400" borderColor="border-orange-500/30" bgColor="bg-orange-500/5" hasPurchase={false} />
                <TargetCard label="보수형" target={analysis.targets.conservative}
                  icon={<Target size={13} className="text-cyan-400" />}
                  color="text-cyan-400" borderColor="border-cyan-500/30" bgColor="bg-cyan-500/5" hasPurchase={false} />
                <TargetCard label="안전형" target={analysis.targets.safe}
                  icon={<ShieldCheck size={13} className="text-green-400" />}
                  color="text-green-400" borderColor="border-green-500/30" bgColor="bg-green-500/5" hasPurchase={false} />
              </div>
            </div>
          )}

          {/* ── ML 신호 ── */}
          {analysis.ml_signal && (
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
              <div className="text-sm font-semibold text-[var(--fg)] mb-3 flex items-center gap-2">
                <BarChart2 size={14} className="text-cyan-400" />ML 모델 신호
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <div className={clsx(
                  'px-3 py-1.5 rounded-lg text-sm font-bold border',
                  analysis.ml_signal.action === 'BUY'
                    ? 'bg-green-500/15 text-green-400 border-green-500/30'
                    : analysis.ml_signal.action === 'WAIT'
                    ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                    : 'bg-[var(--border)] text-[var(--muted)] border-[var(--border)]',
                )}>
                  {analysis.ml_signal.action}
                </div>
                {analysis.ml_signal.prob != null && (
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-[var(--border)] rounded-full overflow-hidden">
                      <div className={clsx('h-full rounded-full', analysis.ml_signal.prob >= 0.65 ? 'bg-green-400' : analysis.ml_signal.prob >= 0.5 ? 'bg-yellow-400' : 'bg-[var(--muted)]')}
                        style={{ width: `${analysis.ml_signal.prob * 100}%` }} />
                    </div>
                    <span className="text-sm font-bold tabular text-[var(--fg)]">{(analysis.ml_signal.prob * 100).toFixed(1)}%</span>
                  </div>
                )}
                <div className="flex gap-3 text-xs">
                  {analysis.ml_signal.entry  && <span className="text-[var(--muted)]">진입 <strong className="text-[var(--fg)]">{analysis.ml_signal.entry.toLocaleString()}</strong></span>}
                  {analysis.ml_signal.target && <span className="text-[var(--muted)]">목표 <strong className="text-red-400">{analysis.ml_signal.target.toLocaleString()}</strong></span>}
                  {analysis.ml_signal.stop   && <span className="text-[var(--muted)]">손절 <strong className="text-blue-400">{analysis.ml_signal.stop.toLocaleString()}</strong></span>}
                </div>
                {analysis.ml_signal.created_at && (
                  <span className="text-xs text-[var(--muted)] ml-auto">{fmt.dateTime(analysis.ml_signal.created_at)}</span>
                )}
              </div>
            </div>
          )}

          {/* ── 수급 요약 ── */}
          {(analysis.supply.foreign_5d !== 0 || analysis.supply.inst_5d !== 0) && (
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
              <div className="text-sm font-semibold text-[var(--fg)] mb-3">수급 신호 (최근 5일)</div>
              <div className="grid grid-cols-2 gap-3">
                <div className="text-center p-3 bg-[var(--bg)] rounded-lg">
                  <div className="text-xs text-[var(--muted)]">외국인 5일 순매수</div>
                  <div className={clsx('text-base font-bold tabular mt-1', analysis.supply.foreign_5d >= 0 ? 'text-red-400' : 'text-blue-400')}>
                    {fmtShares(analysis.supply.foreign_5d)}
                  </div>
                </div>
                <div className="text-center p-3 bg-[var(--bg)] rounded-lg">
                  <div className="text-xs text-[var(--muted)]">기관 5일 순매수</div>
                  <div className={clsx('text-base font-bold tabular mt-1', analysis.supply.inst_5d >= 0 ? 'text-red-400' : 'text-blue-400')}>
                    {fmtShares(analysis.supply.inst_5d)}
                  </div>
                </div>
              </div>
              {analysis.supply.reasons.length > 0 && (
                <div className="mt-2 space-y-0.5">
                  {analysis.supply.reasons.map((r, i) => (
                    <div key={i} className="text-xs text-[var(--muted)] flex items-start gap-1">
                      <span className="text-cyan-400">•</span>{r}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── 최근 뉴스 & 공시 ── */}
          {((analysis.news_recent && analysis.news_recent.length > 0) || (analysis.disclosures_recent && analysis.disclosures_recent.length > 0)) && (
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-2">
                <Newspaper size={14} className="text-cyan-400" />뉴스 / 공시
              </div>
              {analysis.news_recent && analysis.news_recent.length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">최근 뉴스</div>
                  {analysis.news_recent.map((n, i) => {
                    const score = n.sentiment_score ?? 0
                    const sColor = score > 0.1 ? 'text-red-400' : score < -0.1 ? 'text-blue-400' : 'text-[var(--muted)]'
                    const sLabel = score > 0.1 ? '긍정' : score < -0.1 ? '부정' : '중립'
                    return (
                      <div key={i} className="flex items-start gap-2 py-1.5 border-b border-[var(--border)]/40 last:border-0">
                        <span className={clsx('text-xs font-bold mt-0.5 shrink-0 px-1 py-0.5 rounded',
                          score > 0.1 ? 'bg-red-500/15 text-red-400' : score < -0.1 ? 'bg-blue-500/15 text-blue-400' : 'bg-[var(--border)]/40 text-[var(--muted)]')}>
                          {sLabel}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-[var(--fg)] leading-tight line-clamp-2">{n.title}</div>
                          <div className="text-xs text-[var(--muted)] mt-0.5">{fmt.dateTime(n.published_at)}</div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
              {analysis.disclosures_recent && analysis.disclosures_recent.length > 0 && (
                <div className="space-y-1">
                  <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">최근 공시</div>
                  {analysis.disclosures_recent.map((d, i) => {
                    const cat = d.category ?? 'neutral'
                    const dartUrl = d.rcept_no
                      ? `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${d.rcept_no}`
                      : null
                    return (
                      <div key={i} className="flex items-start gap-2 py-1.5 border-b border-[var(--border)]/40 last:border-0">
                        <span className={clsx('text-xs font-bold mt-0.5 shrink-0 px-1 py-0.5 rounded',
                          cat === 'favorable' ? 'bg-red-500/15 text-red-400' : cat === 'unfavorable' ? 'bg-blue-500/15 text-blue-400' : 'bg-[var(--border)]/40 text-[var(--muted)]')}>
                          {cat === 'favorable' ? '호재' : cat === 'unfavorable' ? '악재' : '중립'}
                        </span>
                        <div className="flex-1 min-w-0">
                          {dartUrl ? (
                            <a
                              href={dartUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-start gap-1 group"
                            >
                              <span className="text-sm text-[var(--fg)] leading-tight line-clamp-2 group-hover:text-cyan-400 transition-colors">{d.title}</span>
                              <ExternalLink size={11} className="shrink-0 mt-0.5 text-[var(--muted)] group-hover:text-cyan-400 transition-colors" />
                            </a>
                          ) : (
                            <div className="text-sm text-[var(--fg)] leading-tight line-clamp-2">{d.title}</div>
                          )}
                          <div className="text-xs text-[var(--muted)] mt-0.5">{fmt.dateTime(d.disclosed_at)}</div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── 종합 의견 ── */}
          {analysis.opinion && (
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <div className="text-sm font-semibold text-[var(--fg)] flex items-center gap-2">
                <BookOpen size={14} className="text-amber-400" />종합 의견
              </div>
              <div className="space-y-2">
                {analysis.opinion.split('\n').map((line, i) => {
                  const isStar = line.startsWith('★')
                  const isBullet = line.startsWith('▸')
                  if (!line.trim()) return null
                  return (
                    <div key={i} className={clsx(
                      'text-xs leading-relaxed',
                      isStar
                        ? 'mt-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-[var(--fg)] font-medium'
                        : isBullet
                        ? 'text-[var(--muted)] pl-1'
                        : 'text-[var(--muted)]',
                    )}>
                      {isStar ? line.replace('★ 종합 의견: ', '') : line}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 면책 고지 */}
          <div className="flex items-start gap-2 p-3 bg-[var(--border)]/20 border border-[var(--border)] rounded-lg text-xs text-[var(--muted)]">
            <AlertTriangle size={11} className="shrink-0 mt-0.5 text-yellow-400" />
            <span>본 분석은 기술적 지표 기반 참고 정보이며 투자 권유가 아닙니다. 투자 결정은 본인 책임 하에 신중하게 판단하세요. 과거 데이터 기반 예측은 미래 성과를 보장하지 않습니다.</span>
          </div>
        </div>
      )}

      {analysisError && (
        <div className="flex items-center gap-2 p-4 bg-[var(--card)] border border-red-500/30 rounded-xl text-sm text-red-400">
          <AlertTriangle size={14} className="text-red-400 shrink-0" />
          서버 오류 — 잠시 후 다시 시도해주세요
        </div>
      )}

      {analysis?.error && (
        <div className="flex items-center gap-2 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl text-sm text-[var(--muted)]">
          <AlertTriangle size={14} className="text-yellow-400" />
          {analysis.error}
        </div>
      )}
    </div>
  )
}
