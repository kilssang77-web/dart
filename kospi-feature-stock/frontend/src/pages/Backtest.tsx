import { useState, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  Play, BarChart2, ChevronDown, ChevronUp,
  Save, Trash2, History, CheckSquare, Square,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { marketApi } from '@/api/market'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge, EVENT_LABELS } from '@/components/ui/Badge'
import { ErrorState } from '@/components/ui/ErrorState'
import type { BacktestResult, BacktestTradeItem, SavedBacktestResult } from '@/types'

const ALL_EVENT_TYPES = [
  'VOLUME_SURGE', 'AMOUNT_SURGE', 'BREAKOUT_52W', 'BREAKOUT_26W',
  'BREAKOUT_13W', 'BREAKOUT_20D', 'LONG_WHITE_CANDLE', 'HAMMER_CANDLE',
  'MORNING_STAR', 'SUPPLY_ANOMALY', 'POST_DISCLOSURE_SURGE',
]

type TradeSort   = 'date' | 'pnl' | 'score'
type TradeFilter = 'ALL' | 'win' | 'loss' | 'timeout'

export function Backtest() {
  const [start,         setStart]        = useState('2024-01-01')
  const [end,           setEnd]          = useState('2024-12-31')
  const [eventTypes,    setEventTypes]   = useState<string[]>(['VOLUME_SURGE'])
  const [market,        setMarket]       = useState<'ALL' | 'KOSPI' | 'KOSDAQ'>('ALL')
  const [minScore,      setMinScore]     = useState(0.5)
  const [mlMinProb,     setMlMinProb]    = useState(0.0)
  const [stopLoss,      setStopLoss]     = useState(0.05)
  const [targetPct,     setTargetPct]    = useState(0.10)
  const [walkforward,   setWalkforward]  = useState(false)
  const [result,        setResult]       = useState<BacktestResult | null>(null)
  const [tradeSort,     setTradeSort]    = useState<TradeSort>('date')
  const [tradeSortDir,  setTradeSortDir] = useState<'asc' | 'desc'>('asc')
  const [tradeFilter,   setTradeFilter]  = useState<TradeFilter>('ALL')
  const [showAllTrades, setShowAllTrades]= useState(false)
  const [saveName,      setSaveName]     = useState('')
  const [showSaveRow,   setShowSaveRow]  = useState(false)

  const queryClient = useQueryClient()

  const { mutate: runBacktest, isPending, error: mutError } = useMutation({
    mutationFn: () =>
      marketApi.runBacktest({
        start, end,
        event_types: eventTypes,
        market: market === 'ALL' ? undefined : market,
        min_score: minScore,
        ml_min_prob: mlMinProb > 0 ? mlMinProb : undefined,
        stop_loss_pct: stopLoss,
        target_pct: targetPct,
        walkforward,
      }),
    onSuccess: (data) => {
      setResult(data)
      setShowAllTrades(false)
      setShowSaveRow(false)
      setSaveName(`${eventTypes.slice(0, 2).map((t) => EVENT_LABELS[t] ?? t).join('+')} ${start}~${end.slice(2)}`)
    },
  })

  const { mutate: saveResult, isPending: isSaving } = useMutation({
    mutationFn: () =>
      marketApi.saveBacktestResult({
        name: saveName,
        params: result?.params ?? {},
        result: result?.result ?? {},
        equity_curve: result?.equity_curve ?? [],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtest-results'] })
      setShowSaveRow(false)
    },
  })

  const { data: savedResults } = useQuery({
    queryKey: ['backtest-results'],
    queryFn:  marketApi.listBacktestResults,
    staleTime: 60_000,
  })

  const { mutate: deleteResult } = useMutation({
    mutationFn: (id: number) => marketApi.deleteBacktestResult(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backtest-results'] }),
  })

  const toggleEventType = (t: string) =>
    setEventTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
    )

  const pctToNum = (s?: string) => (s ? parseFloat(s.replace('%', '')) : 0)

  const sortedTrades = useMemo(() => {
    if (!result?.trade_log) return []
    let trades = result.trade_log.filter(
      (t) => tradeFilter === 'ALL' || t.status === tradeFilter
    )
    trades = [...trades].sort((a, b) => {
      let diff = 0
      if (tradeSort === 'date')  diff = a.exit_date.localeCompare(b.exit_date)
      if (tradeSort === 'pnl')   diff = a.pnl_pct - b.pnl_pct
      if (tradeSort === 'score') diff = a.signal_score - b.signal_score
      return tradeSortDir === 'asc' ? diff : -diff
    })
    return trades
  }, [result, tradeSort, tradeSortDir, tradeFilter])

  function handleTradeSort(key: TradeSort) {
    if (tradeSort === key) setTradeSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setTradeSort(key); setTradeSortDir('desc') }
  }

  const SortIcon = ({ k }: { k: TradeSort }) =>
    tradeSort !== k ? <span className="opacity-30">↕</span>
    : tradeSortDir === 'asc' ? <ChevronUp size={10} className="inline" />
    : <ChevronDown size={10} className="inline" />

  const equityFinal = result?.equity_curve?.length
    ? result.equity_curve[result.equity_curve.length - 1]?.equity
    : undefined
  const totalReturn = equityFinal ? ((equityFinal - 1) * 100).toFixed(2) : null

  const loadSaved = (saved: SavedBacktestResult) => {
    setResult({
      params:       saved.params,
      result:       saved.result,
      equity_curve: saved.equity_curve,
      trade_log:    [],
    })
  }

  return (
    <div className="p-6 space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* ── 설정 패널 ── */}
        <Card>
          <CardHeader><CardTitle>백테스트 설정</CardTitle></CardHeader>
          <CardBody className="space-y-4">

            {/* 날짜 */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">시작일</label>
                <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                  className="w-full bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500" />
              </div>
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">종료일</label>
                <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                  className="w-full bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500" />
              </div>
            </div>

            {/* 이벤트 타입 멀티셀렉트 */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs text-[var(--muted)]">
                  이벤트 타입
                  <span className="ml-1.5 text-cyan-400">{eventTypes.length}개 선택</span>
                </label>
                <div className="flex gap-2">
                  <button onClick={() => setEventTypes(ALL_EVENT_TYPES)}
                    className="text-[10px] text-cyan-400 hover:underline">전체</button>
                  <button onClick={() => setEventTypes([])}
                    className="text-[10px] text-[var(--muted)] hover:underline">초기화</button>
                </div>
              </div>
              <div className="space-y-0.5 max-h-48 overflow-y-auto pr-0.5">
                {ALL_EVENT_TYPES.map((t) => {
                  const active = eventTypes.includes(t)
                  return (
                    <button key={t} onClick={() => toggleEventType(t)}
                      className={clsx(
                        'w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-xs transition-colors text-left',
                        active
                          ? 'bg-cyan-500/12 text-cyan-300'
                          : 'text-[var(--muted)] hover:bg-[var(--border)] hover:text-[var(--fg)]'
                      )}>
                      {active
                        ? <CheckSquare size={11} className="flex-shrink-0 text-cyan-400" />
                        : <Square size={11} className="flex-shrink-0 opacity-30" />}
                      <span className="truncate">{EVENT_LABELS[t] ?? t}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 시장 */}
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1.5">시장</label>
              <div className="flex gap-1.5">
                {(['ALL', 'KOSPI', 'KOSDAQ'] as const).map((m) => (
                  <button key={m} onClick={() => setMarket(m)}
                    className={clsx(
                      'flex-1 py-1 text-xs rounded border transition-colors',
                      market === m
                        ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40'
                        : 'text-[var(--muted)] border-[var(--border)] hover:text-[var(--fg)]'
                    )}>
                    {m === 'ALL' ? '전체' : m}
                  </button>
                ))}
              </div>
            </div>

            {/* 슬라이더들 */}
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1">
                최소 스코어 <span className="text-cyan-400 ml-1">{minScore.toFixed(1)}</span>
              </label>
              <input type="range" min="0" max="1" step="0.1" value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-cyan-500" />
            </div>
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1">
                ML 최소 확률{' '}
                <span className="text-purple-400 ml-1">
                  {mlMinProb > 0 ? mlMinProb.toFixed(1) : '미사용'}
                </span>
              </label>
              <input type="range" min="0" max="0.9" step="0.1" value={mlMinProb}
                onChange={(e) => setMlMinProb(Number(e.target.value))}
                className="w-full accent-purple-500" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">
                  손절 <span className="text-blue-400">{(stopLoss * 100).toFixed(0)}%</span>
                </label>
                <input type="range" min="0.02" max="0.15" step="0.01" value={stopLoss}
                  onChange={(e) => setStopLoss(Number(e.target.value))}
                  className="w-full accent-blue-500" />
              </div>
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1">
                  목표 <span className="text-red-400">{(targetPct * 100).toFixed(0)}%</span>
                </label>
                <input type="range" min="0.03" max="0.30" step="0.01" value={targetPct}
                  onChange={(e) => setTargetPct(Number(e.target.value))}
                  className="w-full accent-red-500" />
              </div>
            </div>

            {/* 워크포워드 토글 */}
            <div className="flex items-center justify-between px-3 py-2 bg-[var(--bg)] rounded-md border border-[var(--border)]">
              <div>
                <div className="text-xs font-medium text-[var(--fg)]">워크포워드 검증</div>
                <div className="text-[10px] text-[var(--muted)] leading-tight mt-0.5">기간 4분할 순차 검증</div>
              </div>
              <button
                onClick={() => setWalkforward((v) => !v)}
                className={clsx(
                  'w-9 h-5 rounded-full relative transition-colors flex-shrink-0',
                  walkforward ? 'bg-cyan-500' : 'bg-[var(--border)]'
                )}
              >
                <span className={clsx(
                  'absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                  walkforward ? 'translate-x-4' : 'translate-x-0.5'
                )} />
              </button>
            </div>

            <button
              onClick={() => runBacktest()}
              disabled={isPending || eventTypes.length === 0}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-50 text-sm font-medium transition-colors"
            >
              {isPending
                ? <><BarChart2 size={14} className="animate-pulse" /> 분석 중…</>
                : <><Play size={14} /> 백테스트 실행</>}
            </button>
          </CardBody>
        </Card>

        {/* ── 결과 영역 ── */}
        <div className="lg:col-span-2 space-y-4">
          {mutError ? (
            <ErrorState message="백테스트 실행 중 오류가 발생했습니다" retry={() => runBacktest()} />
          ) : result?.error ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-[var(--muted)] bg-[var(--card)] border border-[var(--border)] rounded-xl">
              <BarChart2 size={28} className="opacity-30" />
              <p className="text-sm">{result.error}</p>
              <p className="text-xs">기간 또는 이벤트 타입을 변경해 보세요</p>
            </div>
          ) : result?.result ? (
            <>
              {/* 핵심 지표 4개 */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="총 거래" value={result.result.total.toString()}
                  sub={`승 ${result.result.win} / 패 ${result.result.loss}`}
                  valueColor="text-cyan-400" />
                <StatCard label="승률" value={result.result.win_rate}
                  sub={`연속최대 ${result.result.win_streak}연승`}
                  valueColor={pctToNum(result.result.win_rate) >= 55 ? 'text-red-400' : 'text-blue-400'} />
                <StatCard label="평균 수익" value={result.result.avg_return}
                  sub={`손익비 ${result.result.profit_factor}`}
                  valueColor={pctToNum(result.result.avg_return) > 0 ? 'text-red-400' : 'text-blue-400'} />
                <StatCard label="샤프 비율" value={result.result.sharpe.toFixed(2)}
                  sub={`MDD ${result.result.max_drawdown}`}
                  valueColor={result.result.sharpe >= 1 ? 'text-green-400' : 'text-[var(--fg)]'} />
              </div>

              {/* 세부 지표 + 저장 */}
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between w-full flex-wrap gap-2">
                    <CardTitle>세부 지표</CardTitle>
                    <div className="flex items-center gap-2 flex-wrap">
                      {(result.params?.event_types ?? (result.params?.event_type ? [result.params.event_type] : []))
                        .slice(0, 3)
                        .map((t) => <Badge key={t} eventType={t} size="sm" />)}
                      <span className="text-xs text-[var(--muted)]">
                        {result.params?.start} ~ {result.params?.end}
                      </span>
                      {result.params?.market && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--muted)]">
                          {result.params.market}
                        </span>
                      )}
                      <button
                        onClick={() => setShowSaveRow((v) => !v)}
                        className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] hover:border-cyan-500/40 transition-colors"
                      >
                        <Save size={11} /> 저장
                      </button>
                    </div>
                  </div>
                </CardHeader>

                {showSaveRow && (
                  <div className="px-5 pb-3 flex gap-2">
                    <input
                      value={saveName}
                      onChange={(e) => setSaveName(e.target.value)}
                      placeholder="결과 이름..."
                      className="flex-1 bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500"
                    />
                    <button
                      onClick={() => saveResult()}
                      disabled={isSaving || !saveName.trim()}
                      className="px-3 py-1 text-xs rounded bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-50 transition-colors"
                    >
                      {isSaving ? '저장 중…' : '확인'}
                    </button>
                  </div>
                )}

                <CardBody>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    {[
                      { label: 'Profit Factor', value: result.result.profit_factor,
                        color: result.result.profit_factor >= 1.5 ? 'text-green-400' : '' },
                      { label: '평균 이익',      value: result.result.avg_win,  color: 'text-red-400' },
                      { label: '평균 손실',      value: result.result.avg_loss, color: 'text-blue-400' },
                      { label: 'Sortino',        value: result.result.sortino.toFixed(2), color: '' },
                      { label: 'Calmar',         value: result.result.calmar.toFixed(2),  color: '' },
                      { label: '최대 연속손실',  value: `${result.result.lose_streak}연패`, color: 'text-red-400' },
                      { label: '손절 비율',      value: `${(stopLoss * 100).toFixed(0)}%`,  color: '' },
                      { label: '목표 비율',      value: `${(targetPct * 100).toFixed(0)}%`, color: '' },
                    ].map(({ label, value, color }) => (
                      <div key={label}>
                        <div className="text-xs text-[var(--muted)] mb-1">{label}</div>
                        <div className={clsx('font-bold tabular', color || 'text-[var(--fg)]')}>{value}</div>
                      </div>
                    ))}
                  </div>
                  {totalReturn && (
                    <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center gap-2 text-sm">
                      <span className="text-[var(--muted)]">누적 수익률 (2% 포지션 기준)</span>
                      <span className={clsx('font-bold tabular', Number(totalReturn) >= 0 ? 'text-red-400' : 'text-blue-400')}>
                        {Number(totalReturn) >= 0 ? '+' : ''}{totalReturn}%
                      </span>
                    </div>
                  )}
                </CardBody>
              </Card>

              {/* 워크포워드 구간별 결과 */}
              {result.walkforward && result.walkforward.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>워크포워드 구간별 결과</CardTitle></CardHeader>
                  <CardBody className="space-y-2">
                    {result.walkforward.map((w, i) => (
                      <div key={i} className="rounded-lg border border-[var(--border)] p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-semibold text-[var(--fg)]">
                            구간 {i + 1}: {w.period}
                          </span>
                          <span className="text-xs text-[var(--muted)]">신호 {w.signals}개</span>
                        </div>
                        {w.result ? (
                          <div className="grid grid-cols-4 gap-2 text-xs">
                            <div>
                              <span className="text-[var(--muted)]">승률 </span>
                              <span className="text-[var(--fg)] font-semibold">{w.result.win_rate}</span>
                            </div>
                            <div>
                              <span className="text-[var(--muted)]">평균수익 </span>
                              <span className={clsx('font-semibold', pctToNum(w.result.avg_return) > 0 ? 'text-red-400' : 'text-blue-400')}>
                                {w.result.avg_return}
                              </span>
                            </div>
                            <div>
                              <span className="text-[var(--muted)]">Sharpe </span>
                              <span className="text-[var(--fg)] font-semibold">{w.result.sharpe.toFixed(2)}</span>
                            </div>
                            <div>
                              <span className="text-[var(--muted)]">MDD </span>
                              <span className="text-blue-400 font-semibold">{w.result.max_drawdown}</span>
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-[var(--muted)]">신호 없음</span>
                        )}
                      </div>
                    ))}
                  </CardBody>
                </Card>
              )}

              {/* 자본금 곡선 */}
              {result.equity_curve && result.equity_curve.length > 1 && (
                <Card>
                  <CardHeader><CardTitle>자본금 곡선 (2% 포지션 기준)</CardTitle></CardHeader>
                  <CardBody>
                    <ResponsiveContainer width="100%" height={180}>
                      <AreaChart data={result.equity_curve} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                        <defs>
                          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#22d3ee" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#71717a' }}
                          tickFormatter={(v) => v.slice(5)} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 10, fill: '#71717a' }}
                          tickFormatter={(v) => v.toFixed(2)} domain={['auto', 'auto']} />
                        <Tooltip
                          formatter={(v: number, name: string) => [
                            name === 'equity' ? v.toFixed(4) : `${v.toFixed(2)}%`,
                            name === 'equity' ? '자본금' : 'PnL',
                          ]}
                          contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 11 }}
                        />
                        <ReferenceLine y={1} stroke="#52525b" strokeDasharray="3 3" />
                        <Area dataKey="equity" stroke="#22d3ee" fill="url(#equityGrad)" dot={false} strokeWidth={1.5} />
                      </AreaChart>
                    </ResponsiveContainer>

                    <ResponsiveContainer width="100%" height={80} style={{ marginTop: 8 }}>
                      <AreaChart data={result.equity_curve} margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
                        <defs>
                          <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#f87171" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="date" tick={false} />
                        <YAxis tick={{ fontSize: 9, fill: '#71717a' }} tickFormatter={(v) => `${v.toFixed(1)}%`} />
                        <Tooltip
                          formatter={(v: number) => [`${v.toFixed(2)}%`, 'Drawdown']}
                          contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 11 }}
                        />
                        <Area dataKey="drawdown" stroke="#f87171" fill="url(#ddGrad)" dot={false} strokeWidth={1} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardBody>
                </Card>
              )}

              {/* 매매 로그 */}
              {sortedTrades.length > 0 && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between w-full flex-wrap gap-2">
                      <CardTitle>매매 로그 ({sortedTrades.length}건)</CardTitle>
                      <div className="flex items-center gap-2">
                        {(['ALL', 'win', 'loss', 'timeout'] as const).map((f) => (
                          <button key={f} onClick={() => setTradeFilter(f)}
                            className={clsx(
                              'text-xs px-2 py-1 rounded border transition-colors',
                              tradeFilter === f
                                ? f === 'win'  ? 'bg-red-500/15 text-red-400 border-red-500/30'
                                : f === 'loss' ? 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                                              : 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                                : 'text-[var(--muted)] border-[var(--border)] hover:text-[var(--fg)]'
                            )}>
                            {f === 'ALL' ? '전체' : f === 'win' ? '수익' : f === 'loss' ? '손절' : '기간만료'}
                          </button>
                        ))}
                      </div>
                    </div>
                  </CardHeader>
                  <CardBody className="pt-3 px-0 pb-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                            <th className="text-left py-2 pl-5 pr-3 text-xs font-semibold uppercase">종목</th>
                            <th className="text-right py-2 pr-3 text-xs font-semibold uppercase cursor-pointer select-none"
                              onClick={() => handleTradeSort('date')}>진입일 <SortIcon k="date" /></th>
                            <th className="text-right py-2 pr-3 text-xs font-semibold uppercase">청산일</th>
                            <th className="text-right py-2 pr-3 text-xs font-semibold uppercase">진입가</th>
                            <th className="text-right py-2 pr-3 text-xs font-semibold uppercase cursor-pointer select-none"
                              onClick={() => handleTradeSort('pnl')}>손익 <SortIcon k="pnl" /></th>
                            <th className="text-right py-2 pr-3 text-xs font-semibold uppercase cursor-pointer select-none"
                              onClick={() => handleTradeSort('score')}>스코어 <SortIcon k="score" /></th>
                            <th className="text-right py-2 pr-5 text-xs font-semibold uppercase">결과</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(showAllTrades ? sortedTrades : sortedTrades.slice(0, 50)).map((t, i) => (
                            <TradeRow key={i} trade={t} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {sortedTrades.length > 50 && !showAllTrades && (
                      <div className="py-3 text-center">
                        <button onClick={() => setShowAllTrades(true)}
                          className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors">
                          나머지 {sortedTrades.length - 50}건 더 보기
                        </button>
                      </div>
                    )}
                  </CardBody>
                </Card>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-24 gap-3 text-[var(--muted)]">
              <BarChart2 size={32} className="opacity-30" />
              <p className="text-sm">왼쪽에서 기간과 이벤트 타입을 설정하고 백테스트를 실행하세요</p>
            </div>
          )}
        </div>
      </div>

      {/* ── 저장된 결과 목록 ── */}
      {savedResults && savedResults.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <History size={14} className="text-[var(--muted)]" />
              <CardTitle>저장된 백테스트 결과</CardTitle>
              <span className="text-xs text-[var(--muted)] ml-1">{savedResults.length}개</span>
            </div>
          </CardHeader>
          <CardBody className="pt-0">
            <div className="divide-y divide-[var(--border)]">
              {savedResults.map((r) => (
                <div key={r.id} className="py-3 flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-[var(--fg)] truncate">{r.name}</div>
                    <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                      <span className="text-xs text-[var(--muted)]">{r.created_at?.slice(0, 16)}</span>
                      {r.result && (
                        <>
                          <span className="text-xs text-[var(--muted)]">
                            승률 <span className={clsx('font-medium', pctToNum(r.result.win_rate) >= 55 ? 'text-red-400' : 'text-[var(--fg)]')}>{r.result.win_rate}</span>
                          </span>
                          <span className="text-xs text-[var(--muted)]">
                            Sharpe <span className={clsx('font-medium', r.result.sharpe >= 1 ? 'text-green-400' : 'text-[var(--fg)]')}>{typeof r.result.sharpe === 'number' ? r.result.sharpe.toFixed(2) : r.result.sharpe}</span>
                          </span>
                          <span className="text-xs text-[var(--muted)]">
                            거래 <span className="text-[var(--fg)] font-medium">{r.result.total}건</span>
                          </span>
                          <span className="text-xs text-[var(--muted)]">
                            MDD <span className="text-blue-400 font-medium">{r.result.max_drawdown}</span>
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => loadSaved(r)}
                    className="text-xs px-2.5 py-1 rounded border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] hover:border-cyan-500/40 transition-colors flex-shrink-0"
                  >
                    불러오기
                  </button>
                  <button
                    onClick={() => deleteResult(r.id)}
                    className="p-1 rounded text-[var(--muted)] hover:text-red-400 transition-colors flex-shrink-0"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}

function TradeRow({ trade: t }: { trade: BacktestTradeItem }) {
  const isWin  = t.status === 'win'
  const isLoss = t.status === 'loss'
  return (
    <tr className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/15">
      <td className="py-2.5 pl-5 pr-3 font-mono text-xs text-[var(--fg)]">{t.code}</td>
      <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">{t.entry_date}</td>
      <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">{t.exit_date}</td>
      <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">{t.entry_price.toLocaleString()}</td>
      <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold text-xs',
        isWin ? 'text-red-400' : isLoss ? 'text-blue-400' : 'text-[var(--muted)]')}>
        {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
      </td>
      <td className="py-2.5 pr-3 text-right tabular text-xs text-[var(--muted)]">{t.signal_score.toFixed(2)}</td>
      <td className="py-2.5 pr-5 text-right">
        <span className={clsx('text-xs px-1.5 py-0.5 rounded',
          isWin  ? 'bg-red-500/15 text-red-400' :
          isLoss ? 'bg-blue-500/15 text-blue-400' :
                   'bg-[var(--border)] text-[var(--muted)]')}>
          {isWin ? '목표달성' : isLoss ? '손절' : '기간만료'}
        </span>
      </td>
    </tr>
  )
}
