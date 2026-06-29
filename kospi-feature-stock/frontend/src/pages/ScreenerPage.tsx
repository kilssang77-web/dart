import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Search, Save, RotateCcw, ArrowUpRight, ArrowDownRight, ChevronRight } from 'lucide-react'
import { screenerApi } from '@/api/screener'
import type { ScreenerParams, ScreenerResult } from '@/api/screener'
import { Card, CardBody } from '@/components/ui/Card'
import { fmt, pctColor } from '@/lib/utils'

// ── 저장된 필터 관련 ────────────────────────────────────────────────────────
const STORAGE_KEY = 'screener_saved_filter'

function loadSaved(): ScreenerParams | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveFilter(params: ScreenerParams) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(params))
  } catch { /* noop */ }
}

// ── 슬라이더 입력 컴포넌트 ──────────────────────────────────────────────────
function SliderField({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
  onClear,
  enabled,
  onToggle,
}: {
  label:    string
  value:    number
  min:      number
  max:      number
  step:     number
  unit?:    string
  onChange: (v: number) => void
  onClear:  () => void
  enabled:  boolean
  onToggle: () => void
}) {
  return (
    <div className={clsx('space-y-1', !enabled && 'opacity-40')}>
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-xs text-[var(--fg)] font-medium cursor-pointer select-none">
          <input
            type="checkbox"
            checked={enabled}
            onChange={onToggle}
            className="w-3.5 h-3.5 accent-cyan-400"
          />
          {label}
        </label>
        <span className="text-xs tabular font-semibold text-cyan-400">
          {enabled ? `${value}${unit ?? ''}` : '—'}
        </span>
      </div>
      {enabled && (
        <input
          type="range"
          min={min} max={max} step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full accent-cyan-400 h-1.5"
        />
      )}
    </div>
  )
}

// ── 기본값 ────────────────────────────────────────────────────────────────
const DEFAULT_PARAMS: ScreenerParams = {
  rsi_min: 30,
  rsi_max: 70,
  near_52w_high_pct: 10,
  volume_ratio_min: 1.5,
  foreign_net_days: 3,
  ml_prob_min: 0.3,
  market: 'ALL',
  limit: 50,
}

const DEFAULT_ENABLED: Record<string, boolean> = {
  rsi: false,
  near52w: false,
  volume: false,
  foreign: false,
  ml: false,
  per: false,
  roe: false,
}

export function ScreenerPage() {
  const nav = useNavigate()

  const saved = loadSaved()
  const [params, setParams] = useState<ScreenerParams>(saved ?? DEFAULT_PARAMS)
  const [enabled, setEnabled] = useState<Record<string, boolean>>(DEFAULT_ENABLED)
  const [results, setResults] = useState<ScreenerResult[] | null>(null)

  const { mutate, isPending, isError } = useMutation({
    mutationFn: screenerApi.run,
    onSuccess:  (data) => setResults(data),
  })

  const toggleField = useCallback((key: string) => {
    setEnabled((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const buildRequest = (): ScreenerParams => {
    const p: ScreenerParams = { market: params.market, limit: params.limit }
    if (enabled.rsi) {
      p.rsi_min = params.rsi_min
      p.rsi_max = params.rsi_max
    }
    if (enabled.near52w) p.near_52w_high_pct = params.near_52w_high_pct
    if (enabled.volume)  p.volume_ratio_min  = params.volume_ratio_min
    if (enabled.foreign) p.foreign_net_days  = params.foreign_net_days
    if (enabled.ml)      p.ml_prob_min       = params.ml_prob_min
    if (enabled.per)     p.per_max           = params.per_max
    if (enabled.roe)     p.roe_min           = params.roe_min
    return p
  }

  const handleRun = () => {
    mutate(buildRequest())
  }

  const handleSave = () => {
    saveFilter(params)
    alert('필터가 저장되었습니다.')
  }

  const handleReset = () => {
    setParams(DEFAULT_PARAMS)
    setEnabled(DEFAULT_ENABLED)
    setResults(null)
  }

  return (
    <div className="p-5 max-w-[1600px]">
      <div className="flex flex-col lg:flex-row gap-5">

        {/* ── 좌측 필터 패널 ─────────────────────────────────────────── */}
        <div className="w-full lg:w-72 shrink-0 space-y-4">
          <Card>
            <CardBody className="space-y-5">
              {/* 시장 선택 */}
              <div className="space-y-1.5">
                <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">시장</div>
                <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
                  {(['ALL', 'KOSPI', 'KOSDAQ'] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setParams((p) => ({ ...p, market: m }))}
                      className={clsx(
                        'flex-1 py-1.5 text-xs font-medium transition-colors',
                        params.market === m
                          ? 'bg-cyan-500/20 text-cyan-400'
                          : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
                      )}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>

              {/* RSI */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">기술 지표</div>
                <SliderField
                  label="RSI 최솟값"
                  value={params.rsi_min ?? 30}
                  min={0} max={100} step={1} unit=""
                  enabled={enabled.rsi}
                  onToggle={() => toggleField('rsi')}
                  onChange={(v) => setParams((p) => ({ ...p, rsi_min: v }))}
                  onClear={() => setParams((p) => ({ ...p, rsi_min: undefined }))}
                />
                {enabled.rsi && (
                  <SliderField
                    label="RSI 최댓값"
                    value={params.rsi_max ?? 70}
                    min={0} max={100} step={1} unit=""
                    enabled={true}
                    onToggle={() => {}}
                    onChange={(v) => setParams((p) => ({ ...p, rsi_max: v }))}
                    onClear={() => {}}
                  />
                )}
                <SliderField
                  label="52주 신고가 이내"
                  value={params.near_52w_high_pct ?? 10}
                  min={1} max={30} step={1} unit="%"
                  enabled={enabled.near52w}
                  onToggle={() => toggleField('near52w')}
                  onChange={(v) => setParams((p) => ({ ...p, near_52w_high_pct: v }))}
                  onClear={() => {}}
                />
              </div>

              {/* 수급 */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">수급</div>
                <SliderField
                  label="거래량 비율"
                  value={params.volume_ratio_min ?? 1.5}
                  min={0.5} max={10} step={0.5} unit="배"
                  enabled={enabled.volume}
                  onToggle={() => toggleField('volume')}
                  onChange={(v) => setParams((p) => ({ ...p, volume_ratio_min: v }))}
                  onClear={() => {}}
                />
                <SliderField
                  label="외국인 연속 순매수"
                  value={params.foreign_net_days ?? 3}
                  min={1} max={20} step={1} unit="일"
                  enabled={enabled.foreign}
                  onToggle={() => toggleField('foreign')}
                  onChange={(v) => setParams((p) => ({ ...p, foreign_net_days: v }))}
                  onClear={() => {}}
                />
              </div>

              {/* ML */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">ML</div>
                <SliderField
                  label="ML 확률 최솟값"
                  value={Math.round((params.ml_prob_min ?? 0.3) * 100)}
                  min={10} max={90} step={5} unit="%"
                  enabled={enabled.ml}
                  onToggle={() => toggleField('ml')}
                  onChange={(v) => setParams((p) => ({ ...p, ml_prob_min: v / 100 }))}
                  onClear={() => {}}
                />
              </div>

              {/* 재무 */}
              <div className="space-y-3">
                <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">재무</div>
                <SliderField
                  label="PER 상한"
                  value={params.per_max ?? 30}
                  min={0} max={200} step={5} unit="배"
                  enabled={enabled.per}
                  onToggle={() => toggleField('per')}
                  onChange={(v) => setParams((p) => ({ ...p, per_max: v }))}
                  onClear={() => {}}
                />
                <SliderField
                  label="ROE 하한"
                  value={params.roe_min ?? 10}
                  min={0} max={50} step={1} unit="%"
                  enabled={enabled.roe}
                  onToggle={() => toggleField('roe')}
                  onChange={(v) => setParams((p) => ({ ...p, roe_min: v }))}
                  onClear={() => {}}
                />
              </div>

              {/* 결과 수 */}
              <div className="space-y-1.5">
                <div className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider">최대 결과 수</div>
                <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
                  {[50, 100, 200].map((l) => (
                    <button
                      key={l}
                      onClick={() => setParams((p) => ({ ...p, limit: l }))}
                      className={clsx(
                        'flex-1 py-1.5 text-xs font-medium transition-colors',
                        params.limit === l
                          ? 'bg-cyan-500/20 text-cyan-400'
                          : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
                      )}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              </div>

              {/* 실행 버튼 */}
              <div className="flex gap-2">
                <button
                  onClick={handleRun}
                  disabled={isPending}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-cyan-500 text-white font-semibold text-sm hover:bg-cyan-400 disabled:opacity-50 transition-colors"
                >
                  <Search size={14} />
                  {isPending ? '검색 중…' : '스크리닝'}
                </button>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleSave}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-[var(--border)] text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
                >
                  <Save size={12} /> 필터 저장
                </button>
                <button
                  onClick={handleReset}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-[var(--border)] text-xs text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
                >
                  <RotateCcw size={12} /> 초기화
                </button>
              </div>
            </CardBody>
          </Card>
        </div>

        {/* ── 우측 결과 ──────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0">
          {/* 상태 */}
          {!results && !isPending && (
            <div className="py-20 text-center">
              <Search size={28} className="text-[var(--muted)]/40 mx-auto mb-3" />
              <div className="text-sm text-[var(--muted)]">조건을 설정하고 스크리닝을 실행하세요</div>
              <div className="text-xs text-[var(--muted)]/60 mt-1">체크박스로 조건을 활성화할 수 있습니다</div>
            </div>
          )}

          {isPending && (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-12 skeleton rounded-xl" />
              ))}
            </div>
          )}

          {isError && (
            <div className="py-12 text-center text-red-400 text-sm">스크리닝 중 오류가 발생했습니다. 다시 시도해주세요.</div>
          )}

          {!isPending && results && (
            <>
              <div className="mb-3 text-sm text-[var(--muted)]">
                조건 일치 <span className="text-cyan-400 font-bold">{results.length}종목</span>
              </div>

              {results.length === 0 ? (
                <div className="py-12 text-center text-sm text-[var(--muted)]">조건에 맞는 종목이 없습니다</div>
              ) : (
                <Card>
                  <CardBody className="p-0 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]">
                          <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider">종목명</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">현재가</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">등락률</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">RSI</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">거래량비율</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">외인연속</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-wider">ML</th>
                          <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider">충족조건</th>
                          <th className="px-4 py-3" />
                        </tr>
                      </thead>
                      <tbody>
                        {results.map((item) => (
                          <tr
                            key={item.code}
                            className="border-b border-[var(--border)]/40 hover:bg-[var(--border)]/15 cursor-pointer transition-colors"
                            onClick={() => nav(`/search?code=${item.code}`)}
                          >
                            <td className="px-4 py-3">
                              <div className="flex flex-col min-w-0">
                                <span className="font-semibold text-[var(--fg)] truncate">{item.name}</span>
                                <div className="flex items-center gap-1 mt-0.5">
                                  <span className="text-[10px] text-[var(--muted)] font-mono">{item.code}</span>
                                  <span className={clsx(
                                    'text-[10px] px-1 rounded font-medium',
                                    item.market === 'KOSPI' ? 'bg-blue-500/15 text-blue-400' : 'bg-purple-500/15 text-purple-400'
                                  )}>
                                    {item.market}
                                  </span>
                                  {item.sector && (
                                    <span className="text-[10px] text-[var(--muted)] truncate max-w-[80px]">{item.sector}</span>
                                  )}
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className="tabular font-medium">{item.current_price.toLocaleString()}</span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className={clsx('tabular font-semibold', pctColor(item.change_rate))}>
                                {item.change_rate > 0 ? '+' : ''}{item.change_rate.toFixed(2)}%
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className={clsx(
                                'tabular font-medium',
                                item.rsi != null && item.rsi >= 70 ? 'text-red-400' :
                                item.rsi != null && item.rsi <= 30 ? 'text-blue-400' : 'text-[var(--fg)]'
                              )}>
                                {item.rsi != null ? item.rsi.toFixed(1) : '—'}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className={clsx(
                                'tabular',
                                item.volume_ratio >= 2 ? 'text-amber-400 font-semibold' : 'text-[var(--fg)]'
                              )}>
                                {item.volume_ratio.toFixed(1)}×
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className={clsx(
                                'tabular',
                                item.foreign_net_5d >= 3 ? 'text-cyan-400 font-semibold' : 'text-[var(--muted)]'
                              )}>
                                {item.foreign_net_5d}일
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className={clsx(
                                'tabular',
                                item.ml_prob != null && item.ml_prob >= 0.35 ? 'text-purple-400 font-semibold' : 'text-[var(--muted)]'
                              )}>
                                {item.ml_prob != null ? `${(item.ml_prob * 100).toFixed(0)}%` : '—'}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1">
                                {item.match_conditions.slice(0, 3).map((c, i) => (
                                  <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 whitespace-nowrap">
                                    {c}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <ChevronRight size={14} className="text-[var(--muted)]" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </CardBody>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
