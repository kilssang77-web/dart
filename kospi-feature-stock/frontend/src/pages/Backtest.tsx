import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Play, BarChart2, TrendingUp, TrendingDown } from 'lucide-react'
import { marketApi } from '@/api/market'
import { StatCard, Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import type { BacktestResult } from '@/types'

const EVENT_TYPES = [
  'VOLUME_SURGE', 'AMOUNT_SURGE', 'BREAKOUT_52W', 'BREAKOUT_26W',
  'BREAKOUT_13W', 'BREAKOUT_20D', 'LONG_WHITE_CANDLE', 'HAMMER_CANDLE',
  'MORNING_STAR', 'SUPPLY_ANOMALY', 'POST_DISCLOSURE_SURGE',
]

export function Backtest() {
  const [start,      setStart]     = useState('2024-01-01')
  const [end,        setEnd]       = useState('2024-12-31')
  const [eventType,  setEventType] = useState('VOLUME_SURGE')
  const [minScore,   setMinScore]  = useState(0.5)
  const [result,     setResult]    = useState<BacktestResult | null>(null)

  const { mutate: runBacktest, isPending } = useMutation({
    mutationFn: () =>
      marketApi.runBacktest({ start, end, event_type: eventType, min_score: minScore }),
    onSuccess: (data) => setResult(data),
  })

  const pctToNum = (s?: string) => {
    if (!s) return 0
    return parseFloat(s.replace('%', ''))
  }

  return (
    <div className="p-6 space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

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
                {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
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
            <button onClick={() => runBacktest()} disabled={isPending}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-50 text-sm font-medium transition-colors">
              {isPending
                ? <><BarChart2 size={14} className="animate-pulse" /> 분석 중…</>
                : <><Play size={14} /> 백테스트 실행</>}
            </button>
          </CardBody>
        </Card>

        <div className="lg:col-span-2 space-y-4">
          {result?.error ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-[var(--muted)] bg-[var(--card)] border border-[var(--border)] rounded-xl">
              <BarChart2 size={28} className="opacity-30" />
              <p className="text-sm">{result.error}</p>
              <p className="text-xs">기간 또는 이벤트 타입을 변경해 보세요</p>
            </div>
          ) : result?.result ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="총 거래" value={result.result.total.toString()} sub={`승 ${result.result.win} / 패 ${result.result.loss}`} valueColor="text-cyan-400" />
                <StatCard label="승률" value={result.result.win_rate} sub="보유 기간 기준" valueColor={pctToNum(result.result.win_rate) >= 55 ? 'text-red-400' : 'text-blue-400'} />
                <StatCard label="평균 수익" value={result.result.avg_return} sub={`이익 ${result.result.avg_win}`} valueColor={pctToNum(result.result.avg_return) > 0 ? 'text-red-400' : 'text-blue-400'} />
                <StatCard label="샤프 비율" value={result.result.sharpe.toFixed(2)} sub={`MDD ${result.result.max_drawdown}`} valueColor={result.result.sharpe >= 1 ? 'text-green-400' : 'text-[var(--fg)]'} />
              </div>

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
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                    <div>
                      <div className="text-xs text-[var(--muted)] mb-1">Profit Factor</div>
                      <div className={clsx('font-bold tabular', result.result.profit_factor >= 1.5 ? 'text-green-400' : 'text-[var(--fg)]')}>
                        {result.result.profit_factor}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-[var(--muted)] mb-1">평균 손실</div>
                      <div className="font-bold tabular text-blue-400">{result.result.avg_loss}</div>
                    </div>
                    <div>
                      <div className="text-xs text-[var(--muted)] mb-1">최소 스코어</div>
                      <div className="font-bold tabular text-[var(--fg)]">{result.params?.min_score ?? minScore}</div>
                    </div>
                  </div>
                </CardBody>
              </Card>

              {result.sample_trades && result.sample_trades.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>샘플 거래 (최대 20건)</CardTitle></CardHeader>
                  <CardBody className="pt-3 px-0 pb-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                            <th className="text-left py-2 pl-5 pr-3 font-medium">종목</th>
                            <th className="text-right py-2 pr-3 font-medium">진입일</th>
                            <th className="text-right py-2 pr-3 font-medium">청산일</th>
                            <th className="text-right py-2 pr-3 font-medium">손익</th>
                            <th className="text-right py-2 pr-5 font-medium">상태</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.sample_trades.map((t, i) => (
                            <tr key={i} className="border-b border-[var(--border)]/50">
                              <td className="py-2.5 pl-5 pr-3 font-mono text-xs text-[var(--fg)]">{t.code}</td>
                              <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">{t.entry}</td>
                              <td className="py-2.5 pr-3 text-right tabular text-[var(--muted)]">{t.exit}</td>
                              <td className={clsx('py-2.5 pr-3 text-right tabular font-semibold', t.pnl > 0 ? 'text-red-400' : 'text-blue-400')}>
                                {t.pnl > 0 ? '+' : ''}{t.pnl.toFixed(2)}%
                              </td>
                              <td className="py-2.5 pr-5 text-right">
                                <span className={clsx('text-[9px] px-1.5 py-0.5 rounded',
                                  t.status === 'target' ? 'bg-red-500/15 text-red-400' :
                                  t.status === 'stop'   ? 'bg-blue-500/15 text-blue-400' :
                                  'bg-[var(--border)] text-[var(--muted)]')}>
                                  {t.status === 'target' ? '목표달성' : t.status === 'stop' ? '손절' : t.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
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