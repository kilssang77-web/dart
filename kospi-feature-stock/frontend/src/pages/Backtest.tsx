import { useState, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Play, BarChart2, TrendingDown, ChevronDown, ChevronUp } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { marketApi } from '@/api/market'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge, EVENT_LABELS } from '@/components/ui/Badge'
import { ErrorState } from '@/components/ui/ErrorState'
import type { BacktestResult, BacktestTradeItem } from '@/types'

const EVENT_TYPES = [
  'VOLUME_SURGE', 'AMOUNT_SURGE', 'BREAKOUT_52W', 'BREAKOUT_26W',
  'BREAKOUT_13W', 'BREAKOUT_20D', 'LONG_WHITE_CANDLE', 'HAMMER_CANDLE',
  'MORNING_STAR', 'SUPPLY_ANOMALY', 'POST_DISCLOSURE_SURGE',
]

type TradeSort = 'date' | 'pnl' | 'score'
type TradeFilter = 'ALL' | 'win' | 'loss' | 'timeout'

export function Backtest() {
  const [start,      setStart]     = useState('2024-01-01')
  const [end,        setEnd]       = useState('2024-12-31')
  const [eventType,  setEventType] = useState('VOLUME_SURGE')
  const [minScore,   setMinScore]  = useState(0.5)
  const [stopLoss,   setStopLoss]  = useState(0.05)
  const [targetPct,  setTargetPct] = useState(0.10)
  const [result,     setResult]    = useState<BacktestResult | null>(null)
  const [tradeSort,  setTradeSort] = useState<TradeSort>('date')
  const [tradeSortDir, setTradeSortDir] = useState<'asc' | 'desc'>('asc')
  const [tradeFilter, setTradeFilter] = useState<TradeFilter>('ALL')
  const [showAllTrades, setShowAllTrades] = useState(false)

  const { mutate: runBacktest, isPending, error: mutError } = useMutation({
    mutationFn: () =>
      marketApi.runBacktest({
        start, end, event_type: eventType, min_score: minScore,
        stop_loss_pct: stopLoss, target_pct: targetPct,
      }),
    onSuccess: (data) => { setResult(data); setShowAllTrades(false) },
  })

  const pctToNum = (s?: string) => s ? parseFloat(s.replace('%', '')) : 0

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

  return (
    <div className="p-6 space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* 설정 패널 */}
        <Card>
          <CardHeader><CardTitle>백테스트 설정</CardTitle></CardHeader>
          <CardBody className="space-y-4">
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1.5">시작일</label>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-md px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500" />
            </div>
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1.5">종료일</label>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-md px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500" />
            </div>
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1.5">이벤트 타입</label>
              <select value={eventType} onChange={(e) => setEventType(e.target.value)}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-md px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500">
                {EVENT_TYPES.map((t) => <option key={t} value={t}>{EVENT_LABELS[t] ?? t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[var(--muted)] block mb-1.5">
                최소 스코어 <span className="text-cyan-400 ml-1">{minScore.toFixed(1)}</span>
              </label>
              <input type="range" min="0" max="1" step="0.1" value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-cyan-500" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1.5">
                  손절 <span className="text-blue-400">{(stopLoss*100).toFixed(0)}%</span>
                </label>
                <input type="range" min="0.02" max="0.15" step="0.01" value={stopLoss}
                  onChange={(e) => setStopLoss(Number(e.target.value))}
                  className="w-full accent-blue-500" />
              </div>
              <div>
                <label className="text-xs text-[var(--muted)] block mb-1.5">
                  목표 <span className="text-red-400">{(targetPct*100).toFixed(0)}%</span>
                </label>
                <input type="range" min="0.03" max="0.30" step="0.01" value={targetPct}
                  onChange={(e) => setTargetPct(Number(e.target.value))}
                  className="w-full accent-red-500" />
              </div>
            </div>
            <button onClick={() => runBacktest()} disabled={isPending}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-50 text-sm font-medium transition-colors">
              {isPending
                ? <><BarChart2 size={14} className="animate-pulse" /> 분석 중…</>
                : <><Play size={14} /> 백테스트 실행</>}
            </button>
          </CardBody>
        </Card>

        {/* 결과 영역 */}
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
              {/* 핵심 지표 */}
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

              {/* 세부 지표 */}
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between w-full">
                    <CardTitle>세부 지표</CardTitle>
                    <div className="flex items-center gap-2">
                      <Badge eventType={result.params?.event_type ?? eventType} size="sm" />
                      <span className="text-xs text-[var(--muted)]">{result.params?.start} ~ {result.params?.end}</span>
                    </div>
                  </div>
                </CardHeader>
                <CardBody>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    {[
                      { label: 'Profit Factor', value: result.result.profit_factor, color: result.result.profit_factor >= 1.5 ? 'text-green-400' : '' },
                      { label: '평균 이익', value: result.result.avg_win, color: 'text-red-400' },
                      { label: '평균 손실', value: result.result.avg_loss, color: 'text-blue-400' },
                      { label: 'Sortino', value: result.result.sortino.toFixed(2), color: '' },
                      { label: 'Calmar', value: result.result.calmar.toFixed(2), color: '' },
                      { label: '최대 연속손실', value: `${result.result.lose_streak}연패`, color: 'text-red-400' },
                      { label: '손절 비율', value: `${(stopLoss*100).toFixed(0)}%`, color: '' },
                      { label: '목표 비율', value: `${(targetPct*100).toFixed(0)}%`, color: '' },
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

                    {/* 드로다운 차트 */}
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

              {/* 매매 로그 전체 */}
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
                                ? f === 'win' ? 'bg-red-500/15 text-red-400 border-red-500/30'
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
                        <button
                          onClick={() => setShowAllTrades(true)}
                          className="text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
                        >
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
    </div>
  )
}

function TradeRow({ trade: t }: { trade: BacktestTradeItem }) {
  const isWin = t.status === 'win'
  const isLoss = t.status === 'loss'
  return (
    <tr className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/15">
      <td className="py-2.5 pl-5 pr-3 font-mono text-xs text-[var(--fg)]">{t.code}</td>
      <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">{t.entry_date}</td>
      <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">{t.exit_date}</td>
      <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)] text-xs">{t.entry_price.toLocaleString()}</td>
      <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold text-xs', isWin ? 'text-red-400' : isLoss ? 'text-blue-400' : 'text-[var(--muted)]')}>
        {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
      </td>
      <td className="py-2.5 pr-3 text-right tabular text-xs text-[var(--muted)]">{t.signal_score.toFixed(2)}</td>
      <td className="py-2.5 pr-5 text-right">
        <span className={clsx('text-xs px-1.5 py-0.5 rounded',
          isWin ? 'bg-red-500/15 text-red-400' :
          isLoss ? 'bg-blue-500/15 text-blue-400' :
          'bg-[var(--border)] text-[var(--muted)]')}>
          {isWin ? '목표달성' : isLoss ? '손절' : '기간만료'}
        </span>
      </td>
    </tr>
  )
}
