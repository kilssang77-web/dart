import { useState, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { TrendingUp, Target, BrainCircuit, Info, RefreshCw, CheckCircle2, AlertCircle, Loader2, Clock, ChevronRight } from 'lucide-react'
import { marketApi } from '@/api/market'
import type { RecJourneyItem } from '@/api/market'
import { recommendationsApi } from '@/api/recommendations'
import type { Recommendation } from '@/types'
import { RecDetailModal } from '@/components/modals/RecDetailModal'
import { fmt, pctColor } from '@/lib/utils'
import { EVENT_LABELS } from '@/components/ui/Badge'

// ── 중복 제거 헬퍼 ────────────────────────────────────────────────────────────
// 동일 종목의 추천이 5분 이내 차이로 여러 건이면 첫 번째 1건만 남기고,
// 나머지 이벤트 타입은 첫 번째 행의 extraEvents 에 합산한다.
interface RecJourneyItemEx extends RecJourneyItem {
  extraEvents?: string[]
}

function deduplicateItems(items: RecJourneyItem[]): RecJourneyItemEx[] {
  // signal_time 오름차순 정렬 → 첫 번째 신호 기준으로 그룹
  const sorted = [...items].sort(
    (a, b) => new Date(a.signal_time ?? 0).getTime() - new Date(b.signal_time ?? 0).getTime()
  )
  const WINDOW_MS = 5 * 60 * 1000 // 5분 이내
  const result: RecJourneyItemEx[] = []
  const used = new Set<number>()

  for (let i = 0; i < sorted.length; i++) {
    if (used.has(sorted[i].id)) continue
    const base = { ...sorted[i], extraEvents: [] as string[] }
    const baseTime = new Date(sorted[i].signal_time ?? 0).getTime()

    for (let j = i + 1; j < sorted.length; j++) {
      if (used.has(sorted[j].id)) continue
      if (sorted[j].code !== sorted[i].code) continue
      const diff = Math.abs(new Date(sorted[j].signal_time ?? 0).getTime() - baseTime)
      if (diff <= WINDOW_MS) {
        if (sorted[j].event_type && sorted[j].event_type !== base.event_type) {
          base.extraEvents!.push(sorted[j].event_type!)
        }
        used.add(sorted[j].id)
      }
    }
    used.add(sorted[i].id)
    result.push(base)
  }

  // 다시 내림차순 (최신 → 과거)
  return result.sort(
    (a, b) => new Date(b.signal_time ?? 0).getTime() - new Date(a.signal_time ?? 0).getTime()
  )
}

// ── 수익률 셀 ─────────────────────────────────────────────────────────────────
function RCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-[var(--muted)] text-xs">—</span>
  const txt = `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
  return (
    <span className={clsx(
      'text-xs tabular font-semibold px-1 py-0.5 rounded',
      v > 0  ? 'text-red-400  bg-red-500/10'
      : v < 0 ? 'text-blue-400 bg-blue-500/10'
      :         'text-[var(--muted)]'
    )}>
      {txt}
    </span>
  )
}

// ── 결과 뱃지 ─────────────────────────────────────────────────────────────────
function ResultBadge({ item }: { item: RecJourneyItem }) {
  if (!item.tracking_complete) {
    const hasSome = item.r_1h != null || item.r_3h != null || item.r_1d != null
    return (
      <span className={clsx(
        'text-[10px] px-1.5 py-0.5 rounded-full border font-semibold whitespace-nowrap',
        hasSome
          ? 'border-yellow-500/30 text-yellow-400 bg-yellow-500/10'
          : 'border-[var(--border)] text-[var(--muted)]'
      )}>
        {hasSome ? '추적중' : '대기'}
      </span>
    )
  }
  if (item.hit_target)
    return <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-green-500/30 text-green-400 bg-green-500/10 font-semibold">목표달성</span>
  if (item.hit_stop)
    return <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-red-500/30 text-red-400 bg-red-500/10 font-semibold">손절</span>
  if (item.is_success === true)
    return <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-cyan-500/30 text-cyan-400 bg-cyan-500/10 font-semibold">성공</span>
  if (item.is_success === false)
    return <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-blue-500/30 text-blue-400 bg-blue-500/10 font-semibold">실패</span>
  return null
}

// ── 미니 여정 바 ──────────────────────────────────────────────────────────────
function MiniJourney({ item }: { item: RecJourneyItem }) {
  const pts = [item.r_1h, item.r_3h, item.r_close, item.r_1d, item.r_3d, item.r_5d, item.r_10d]
  const defined = pts.filter((p) => p != null) as number[]
  if (!defined.length) return <span className="text-[10px] text-[var(--muted)]">—</span>
  const peak = Math.max(...defined.map(Math.abs), 0.5)
  return (
    <div className="flex items-center gap-px h-5">
      {pts.map((p, i) => {
        if (p == null)
          return <div key={i} className="w-2.5 h-1 bg-[var(--border)] rounded-sm opacity-20" />
        const h = Math.max(3, Math.round(Math.abs(p) / peak * 18))
        return (
          <div
            key={i}
            className={clsx('w-2.5 rounded-sm', p >= 0 ? 'bg-red-400/75' : 'bg-blue-400/75')}
            style={{ height: `${h}px` }}
            title={`${p >= 0 ? '+' : ''}${p.toFixed(2)}%`}
          />
        )
      })}
    </div>
  )
}

// ── 이벤트별 요약 ─────────────────────────────────────────────────────────────
function EventSummary({ items }: { items: RecJourneyItem[] }) {
  const byType = useMemo(() => {
    const map: Record<string, RecJourneyItem[]> = {}
    items.forEach((i) => {
      const k = i.event_type || 'UNKNOWN'
      ;(map[k] = map[k] ?? []).push(i)
    })
    return Object.entries(map)
      .map(([et, rows]) => {
        const completed = rows.filter((r) => r.is_success !== null)
        const successes = rows.filter((r) => r.is_success === true)
        const r1ds = rows.filter((r) => r.r_1d != null).map((r) => r.r_1d!)
        const r5ds = rows.filter((r) => r.r_5d != null).map((r) => r.r_5d!)
        return {
          et,
          cnt: rows.length,
          winRate: completed.length ? successes.length / completed.length * 100 : null,
          avg1d: r1ds.length ? r1ds.reduce((a, b) => a + b, 0) / r1ds.length : null,
          avg5d: r5ds.length ? r5ds.reduce((a, b) => a + b, 0) / r5ds.length : null,
        }
      })
      .sort((a, b) => b.cnt - a.cnt)
  }, [items])

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs min-w-[600px]">
        <thead>
          <tr className="border-b border-[var(--border)] text-[var(--muted)]">
            <th className="text-left pb-2 font-semibold uppercase tracking-wider">이벤트 유형</th>
            <th className="text-right pb-2 font-semibold uppercase tracking-wider">건수</th>
            <th className="text-right pb-2 font-semibold uppercase tracking-wider">성공률</th>
            <th className="text-right pb-2 font-semibold uppercase tracking-wider">평균 +1일</th>
            <th className="text-right pb-2 font-semibold uppercase tracking-wider">평균 +5일</th>
          </tr>
        </thead>
        <tbody>
          {byType.map(({ et, cnt, winRate, avg1d, avg5d }) => (
            <tr key={et} className="border-b border-[var(--border)]/40 hover:bg-[var(--border)]/10">
              <td className="py-2 font-medium text-[var(--fg)]">{EVENT_LABELS[et] ?? et}</td>
              <td className="py-2 text-right tabular text-[var(--fg)]">{cnt}</td>
              <td className={clsx('py-2 text-right tabular font-semibold', winRate != null && winRate >= 50 ? 'text-green-400' : 'text-[var(--muted)]')}>
                {winRate != null ? `${winRate.toFixed(1)}%` : '—'}
              </td>
              <td className="py-2 text-right"><RCell v={avg1d} /></td>
              <td className="py-2 text-right"><RCell v={avg5d} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── 피드백 재학습 패널 ────────────────────────────────────────────────────────
function FeedbackRetrainPanel() {
  const queryClient = useQueryClient()
  const [triggering, setTriggering] = useState(false)

  const { data: fb, isLoading: fbLoading } = useQuery({
    queryKey:  ['feedback-stats'],
    queryFn:   () => marketApi.getFeedbackStats(),
    staleTime: 60_000,
  })

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey:        ['retrain-status'],
    queryFn:         () => marketApi.getRetrainStatus(),
    refetchInterval: (query) => query.state.data?.status === 'running' ? 4_000 : false,
    staleTime:       5_000,
  })

  const handleRetrain = useCallback(async () => {
    setTriggering(true)
    try {
      await marketApi.triggerRetrain()
      await refetchStatus()
      queryClient.invalidateQueries({ queryKey: ['retrain-status'] })
    } finally {
      setTriggering(false)
    }
  }, [queryClient, refetchStatus])

  const isRunning  = status?.status === 'running'
  const isDone     = status?.status === 'done'
  const isFailed   = status?.status === 'failed'
  const btnDisabled = isRunning || triggering

  const fmtTime = (iso: string | null | undefined) => {
    if (!iso) return ''
    try {
      return new Date(iso).toLocaleString('ko-KR', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
      })
    } catch { return '' }
  }

  return (
    <div className="bg-[var(--card)] border border-cyan-500/20 rounded-xl p-5">
      <div className="flex flex-wrap items-start gap-5">

        {/* 왼쪽: 피드백 데이터 현황 */}
        <div className="flex-1 min-w-[260px]">
          <div className="flex items-center gap-2 mb-3">
            <BrainCircuit size={14} className="text-cyan-400" />
            <span className="text-sm font-semibold text-[var(--fg)]">피드백 학습 데이터 현황</span>
          </div>
          {fbLoading ? (
            <div className="flex gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-10 w-20 skeleton rounded-lg" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-[var(--bg)] rounded-lg p-3 text-center">
                <div className="text-[10px] text-[var(--muted)] mb-1">전체 추적</div>
                <div className="text-base font-bold text-[var(--fg)] tabular">{fb?.total ?? 0}<span className="text-xs font-normal text-[var(--muted)] ml-0.5">건</span></div>
              </div>
              <div className="bg-[var(--bg)] rounded-lg p-3 text-center">
                <div className="text-[10px] text-[var(--muted)] mb-1">5일 확인</div>
                <div className={clsx('text-base font-bold tabular', (fb?.with_5d ?? 0) >= 10 ? 'text-green-400' : 'text-yellow-400')}>
                  {fb?.with_5d ?? 0}<span className="text-xs font-normal text-[var(--muted)] ml-0.5">건</span>
                </div>
              </div>
              <div className="bg-[var(--bg)] rounded-lg p-3 text-center">
                <div className="text-[10px] text-[var(--muted)] mb-1">성공률</div>
                <div className={clsx('text-base font-bold tabular', fb?.win_rate != null ? (fb.win_rate >= 50 ? 'text-green-400' : 'text-red-400') : 'text-[var(--muted)]')}>
                  {fb?.win_rate != null ? `${fb.win_rate}%` : '—'}
                </div>
              </div>
              <div className="bg-[var(--bg)] rounded-lg p-3 text-center">
                <div className="text-[10px] text-[var(--muted)] mb-1">평균 +5일</div>
                <div className={clsx('text-base font-bold tabular', fb?.avg_r5d != null ? pctColor(fb.avg_r5d) : 'text-[var(--muted)]')}>
                  {fb?.avg_r5d != null ? `${fb.avg_r5d >= 0 ? '+' : ''}${fb.avg_r5d.toFixed(2)}%` : '—'}
                </div>
              </div>
            </div>
          )}
          {fb && fb.oldest && (
            <p className="text-[10px] text-[var(--muted)] mt-2">
              데이터 기간: {fmtTime(fb.oldest)} ~ {fmtTime(fb.newest)}
            </p>
          )}
        </div>

        {/* 오른쪽: 버튼 + 상태 */}
        <div className="flex flex-col items-end justify-between gap-3 shrink-0">
          <button
            onClick={handleRetrain}
            disabled={btnDisabled}
            className={clsx(
              'flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all',
              btnDisabled
                ? 'bg-[var(--border)] text-[var(--muted)] cursor-not-allowed'
                : 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 hover:border-cyan-500/50'
            )}
          >
            {isRunning || triggering
              ? <Loader2 size={14} className="animate-spin" />
              : <RefreshCw size={14} />}
            {isRunning ? '재학습 진행 중…' : triggering ? '요청 중…' : '피드백 데이터 ML 재학습'}
          </button>

          {/* 상태 표시 */}
          {status && status.status !== 'idle' && status.status !== 'unknown' && (
            <div className="flex items-center gap-1.5 text-xs">
              {isDone   && <CheckCircle2 size={12} className="text-green-400" />}
              {isFailed && <AlertCircle  size={12} className="text-red-400" />}
              {isRunning && <Loader2 size={12} className="animate-spin text-cyan-400" />}
              <span className={clsx(
                isDone ? 'text-green-400' : isFailed ? 'text-red-400' : 'text-cyan-400'
              )}>
                {isDone   ? `완료 ${fmtTime(status.finished_at)}`
                  : isFailed ? '재학습 실패'
                  : `진행 중 (${fmtTime(status.started_at)} 시작)`}
              </span>
            </div>
          )}

          {/* 안내 문구 */}
          <p className="text-[10px] text-[var(--muted)] text-right max-w-[220px] leading-relaxed">
            {(fb?.with_5d ?? 0) < 10
              ? `5일 수익률 확인 데이터 ${fb?.with_5d ?? 0}건 (최소 10건 권장)`
              : `${fb?.with_5d ?? 0}건 피드백 데이터 기반으로 모델 재학습`}
          </p>
        </div>
      </div>
    </div>
  )
}


// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export function RecommendationJourney() {
  const nav = useNavigate()
  const [days,        setDays]        = useState(30)
  const [eventFilter, setEventFilter] = useState('')
  const [showSummary, setShowSummary] = useState(false)
  const [dedup,       setDedup]       = useState(true)
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null)
  const [loadingRecId, setLoadingRecId] = useState<number | null>(null)

  const openRecDetail = useCallback(async (recId: number | null) => {
    if (!recId) return
    setLoadingRecId(recId)
    try {
      const rec = await recommendationsApi.getById(recId)
      setSelectedRec(rec)
    } catch {
      // rec fetch 실패 시 팝업 안 열림
    } finally {
      setLoadingRecId(null)
    }
  }, [])

  const { data: items, isLoading } = useQuery({
    queryKey:  ['rec-journey', days, eventFilter],
    queryFn:   () => marketApi.getRecommendationJourney({
      days, event_type: eventFilter || undefined, limit: 300,
    }),
    staleTime: 300_000,
  })

  // 중복 제거 적용
  const displayItems = useMemo<RecJourneyItemEx[]>(() => {
    if (!items) return []
    return dedup ? deduplicateItems(items) : items.map((i) => ({ ...i, extraEvents: [] }))
  }, [items, dedup])

  const eventTypes = useMemo(() => {
    if (!items) return []
    return Array.from(new Set(items.map((i) => i.event_type).filter(Boolean))).sort() as string[]
  }, [items])

  // 당일종가 수집 중 여부 감지 (오늘 신호 중 r_close가 null인 건 존재 + 장 종료 시각)
  const closePending = useMemo(() => {
    if (!items) return false
    const todayKST = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
    const seoulHHMM = new Date().toLocaleTimeString('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' })
    // 장 종료(15:35) 이후 ~ 17:00 사이이고, 오늘 신호 중 r_close null인 건이 있으면 수집 중
    if (seoulHHMM < '15:35' || seoulHHMM > '17:00') return false
    return items.some((i) => {
      const sigDate = i.signal_time ? new Date(i.signal_time).toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' }) : ''
      return sigDate === todayKST && i.r_close == null
    })
  }, [items])

  const stats = useMemo(() => {
    if (!displayItems.length) return null
    const completed = displayItems.filter((i) => i.is_success !== null)
    const successes = displayItems.filter((i) => i.is_success === true)
    const r1ds = displayItems.filter((i) => i.r_1d != null).map((i) => i.r_1d!)
    const r5ds = displayItems.filter((i) => i.r_5d != null).map((i) => i.r_5d!)
    const hitT = displayItems.filter((i) => i.hit_target).length
    const hitS = displayItems.filter((i) => i.hit_stop).length
    return {
      total:    displayItems.length,
      rawTotal: items?.length ?? 0,
      completed: completed.length,
      winRate:  completed.length ? successes.length / completed.length * 100 : null,
      avg1d:    r1ds.length ? r1ds.reduce((a, b) => a + b, 0) / r1ds.length : null,
      avg5d:    r5ds.length ? r5ds.reduce((a, b) => a + b, 0) / r5ds.length : null,
      hitTarget: hitT,
      hitStop:   hitS,
    }
  }, [displayItems, items])

  return (
    <div className="p-5 space-y-5 max-w-[1800px]">

      {/* 페이지 설명 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-[var(--fg)] mb-1">추천 성과 추적</h2>
          <p className="text-xs text-[var(--muted)] max-w-2xl">
            매수 추천 종목의 <strong className="text-[var(--fg)]">추천 시점 → +1h → +3h → 당일종가 → +1일 → +3일 → +5일 → +10일</strong>
            주가 흐름을 보여줍니다. 미추적 구간은 <span className="text-[var(--muted)]">—</span> 로 표시되며, 시스템이 1시간마다 자동 업데이트합니다.
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[var(--muted)] shrink-0 bg-[var(--bg)] px-3 py-2 rounded-lg border border-[var(--border)]">
          <Info size={11} />
          ML 재학습 피드백 데이터
        </div>
      </div>

      {/* 당일종가 수집 중 배너 */}
      {closePending && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400 text-xs">
          <Clock size={13} className="shrink-0 animate-pulse" />
          <span>
            당일종가 수집 중 (장 마감 후 EOD 일봉 수집 진행 중 · 약 16:50 완료 예정).
            완료 후 <strong>당일종가</strong> 컬럼이 자동 표시됩니다.
          </span>
        </div>
      )}

      {/* 필터 + 요약 토글 */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-[var(--card)] border border-[var(--border)] rounded-xl">
        {/* 기간 */}
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {([7, 14, 30, 60] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={clsx(
                'px-3 py-1.5 text-xs font-medium transition-colors',
                days === d ? 'bg-cyan-500/20 text-cyan-400' : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]'
              )}
            >
              {d}일
            </button>
          ))}
        </div>

        {/* 이벤트 필터 */}
        <select
          value={eventFilter}
          onChange={(e) => setEventFilter(e.target.value)}
          className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--fg)] focus:outline-none focus:border-cyan-500/60"
        >
          <option value="">전체 이벤트</option>
          {eventTypes.map((et) => (
            <option key={et} value={et}>{EVENT_LABELS[et] ?? et}</option>
          ))}
        </select>

        {/* 중복 제거 토글 */}
        <label className="flex items-center gap-1.5 text-xs text-[var(--muted)] cursor-pointer select-none ml-auto">
          <div
            onClick={() => setDedup((v) => !v)}
            className={clsx(
              'w-8 h-4 rounded-full relative transition-colors cursor-pointer',
              dedup ? 'bg-cyan-500/60' : 'bg-[var(--border)]'
            )}
          >
            <div className={clsx(
              'absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform',
              dedup ? 'translate-x-4' : 'translate-x-0.5'
            )} />
          </div>
          <span onClick={() => setDedup((v) => !v)}>중복 제거</span>
          {stats && stats.rawTotal !== stats.total && (
            <span className="text-[10px] text-cyan-400">({stats.rawTotal} → {stats.total}건)</span>
          )}
        </label>

        {/* 통계 요약 */}
        {stats && (
          <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
            <span className="text-[var(--fg)] font-semibold">{stats.total}건</span>
            {stats.winRate != null && (
              <span className={stats.winRate >= 50 ? 'text-green-400 font-semibold' : 'text-[var(--muted)]'}>
                성공률 {stats.winRate.toFixed(1)}%
              </span>
            )}
            {stats.avg1d != null && (
              <span className={pctColor(stats.avg1d)}>평균+1일 {stats.avg1d >= 0 ? '+' : ''}{stats.avg1d.toFixed(2)}%</span>
            )}
            {stats.avg5d != null && (
              <span className={pctColor(stats.avg5d)}>평균+5일 {stats.avg5d >= 0 ? '+' : ''}{stats.avg5d.toFixed(2)}%</span>
            )}
          </div>
        )}

        <button
          onClick={() => setShowSummary((v) => !v)}
          className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1"
        >
          이벤트별 요약 {showSummary ? '▲' : '▼'}
        </button>
      </div>

      {/* 이벤트별 요약 테이블 */}
      {showSummary && displayItems.length > 0 && (
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5">
          <div className="text-xs font-semibold text-[var(--muted)] mb-3 uppercase tracking-wider">이벤트 유형별 성과 요약</div>
          <EventSummary items={displayItems} />
        </div>
      )}

      {/* 추천 상세 팝업 */}
      {selectedRec && (
        <RecDetailModal
          rec={selectedRec}
          onClose={() => setSelectedRec(null)}
          onGoDetail={() => { setSelectedRec(null); nav(`/search?code=${selectedRec.code}`) }}
          compact
        />
      )}

      {/* 메인 여정 테이블 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        {/* 컬럼 헤더 설명 */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--border)] bg-[var(--bg)]/40">
          <TrendingUp size={13} className="text-cyan-400" />
          <span className="text-xs font-semibold text-[var(--fg)]">추천 시점 → 주가 여정</span>
          <span className="text-xs text-[var(--muted)] ml-2">
            진입가 대비 각 시점 등락률 ·
            <span className="text-red-400 ml-1">+상승</span> ·
            <span className="text-blue-400 ml-1">-하락</span>
          </span>
          {isLoading && <span className="ml-auto text-xs text-[var(--muted)]">로딩 중…</span>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ minWidth: '1100px' }}>
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/20">
                <th className="text-left px-4 py-2.5 font-semibold uppercase tracking-wider w-28">종목</th>
                <th className="text-left px-3 py-2.5 font-semibold uppercase tracking-wider w-24">이벤트</th>
                <th className="text-left px-3 py-2.5 font-semibold uppercase tracking-wider w-28">추천시각</th>
                <th className="text-right px-3 py-2.5 font-semibold uppercase tracking-wider w-16">진입가</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14 text-yellow-400/80">+1h</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14 text-orange-400/80">+3h</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14">당일종가</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14">+1일</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14">+3일</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14 text-cyan-400/80">+5일</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-14">+10일</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-16">여정</th>
                <th className="text-center px-3 py-2.5 font-semibold uppercase tracking-wider w-16">결과</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--border)]/40">
                  {Array.from({ length: 13 }).map((__, j) => (
                    <td key={j} className="px-3 py-3"><div className="h-3 skeleton rounded w-full" /></td>
                  ))}
                </tr>
              ))}
              {!isLoading && displayItems.length === 0 && (
                <tr>
                  <td colSpan={13} className="py-16 text-center text-[var(--muted)]">
                    조건에 맞는 추적 데이터가 없습니다
                  </td>
                </tr>
              )}
              {displayItems.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-[var(--border)]/40 hover:bg-[var(--border)]/10 transition-colors"
                >
                  {/* 종목 */}
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => nav(`/search?code=${item.code}`)}
                      className="flex flex-col items-start group"
                    >
                      <span className="font-semibold text-[var(--fg)] group-hover:text-cyan-400 transition-colors leading-tight">
                        {item.name}
                      </span>
                      <span className="text-[10px] text-[var(--muted)] font-mono">{item.code}</span>
                    </button>
                  </td>
                  {/* 이벤트 */}
                  <td className="px-3 py-2.5">
                    <div className="flex flex-col gap-0.5">
                      <button
                        onClick={() => openRecDetail(item.rec_id)}
                        disabled={loadingRecId === item.rec_id}
                        className={clsx(
                          'flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border whitespace-nowrap transition-colors',
                          item.rec_id
                            ? 'bg-[var(--bg)] border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10 cursor-pointer'
                            : 'bg-[var(--bg)] border-[var(--border)] text-[var(--muted)] cursor-default'
                        )}
                      >
                        {loadingRecId === item.rec_id
                          ? <Loader2 size={8} className="animate-spin shrink-0" />
                          : null}
                        {EVENT_LABELS[item.event_type ?? ''] ?? item.event_type ?? '—'}
                        {item.rec_id && (
                          <>
                            <span className="opacity-40 mx-0.5">·</span>
                            <span className="font-semibold text-cyan-400">
                              {(item.extraEvents?.length ?? 0) + 1}개 신호
                            </span>
                            <ChevronRight size={8} className="shrink-0 opacity-70" />
                          </>
                        )}
                      </button>
                      {item.extraEvents && item.extraEvents.length > 0 && (
                        <span className="text-[9px] text-cyan-400/70 leading-tight">
                          +{item.extraEvents.map((e) => EVENT_LABELS[e] ?? e).join(', ')}
                        </span>
                      )}
                    </div>
                  </td>
                  {/* 추천시각 */}
                  <td className="px-3 py-2.5 tabular text-[var(--muted)] whitespace-nowrap">
                    {item.signal_time
                      ? new Date(item.signal_time).toLocaleString('ko-KR', {
                          month: '2-digit', day: '2-digit',
                          hour: '2-digit', minute: '2-digit',
                        })
                      : '—'}
                  </td>
                  {/* 진입가 */}
                  <td className="px-3 py-2.5 text-right tabular text-[var(--fg)] font-medium">
                    {item.entry_price ? fmt.price(item.entry_price) : '—'}
                  </td>
                  {/* +1h */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_1h} /></td>
                  {/* +3h */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_3h} /></td>
                  {/* 당일종가 */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_close} /></td>
                  {/* +1일 */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_1d} /></td>
                  {/* +3일 */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_3d} /></td>
                  {/* +5일 */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_5d} /></td>
                  {/* +10일 */}
                  <td className="px-3 py-2.5 text-center"><RCell v={item.r_10d} /></td>
                  {/* 미니 여정 */}
                  <td className="px-3 py-2.5">
                    <MiniJourney item={item} />
                  </td>
                  {/* 결과 */}
                  <td className="px-3 py-2.5 text-center">
                    <ResultBadge item={item} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* 하단 범례 */}
        {items && items.length > 0 && (
          <div className="px-5 py-3 border-t border-[var(--border)] bg-[var(--bg)]/20 flex flex-wrap gap-4 text-[10px] text-[var(--muted)]">
            <span>• <strong className="text-[var(--fg)]">당일종가</strong>: 추천 당일 장 마감(15:30) 종가 기준</span>
            <span>• <strong className="text-[var(--fg)]">+1일~+10일</strong>: 추천 시점 기준 영업일 수</span>
            <span>• <strong className="text-[var(--fg)]">여정 바</strong>: 좌→우 시간 흐름, 빨강=상승·파랑=하락</span>
            <span>• <strong className="text-yellow-400">추적중</strong>: 아직 해당 시점 미도달</span>
            <span className="ml-auto flex items-center gap-1">
              <Target size={9} className="text-green-400" /> 목표가 =
              {items[0]?.target_price ? ` ${fmt.price(items[0].target_price)}` : '진입가 기준 설정'}
            </span>
          </div>
        )}
      </div>

    </div>
  )
}
