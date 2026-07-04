/**
 * 오늘의 입찰 — 메인 허브
 * 입찰 담당자가 출근 후 30초 안에 오늘 할 일을 파악하는 화면
 */
import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles, AlertCircle, Clock, Trophy,
  TrendingUp, TrendingDown, ChevronRight, CheckCircle2,
  Building2, Calendar, Zap, BarChart2, Search, ListChecks, Plus,
  BookOpen, ClipboardCheck, Crosshair, Bell, X, ChevronDown, ChevronUp,
  ShieldCheck, ShieldAlert, Minus, Activity, History,
} from 'lucide-react'
import { bidsApi, statsApi, selectionApi, kpiApi, executionsApi, journalApi } from '@/api'
import type {
  BidRecommendItem, OverviewStatsWithChange, ExecutionSummary,
  JournalStats, PendingResultItem, InlineDecision, RecommendationCompliance,
} from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// ── 투찰 등록 모달 (인라인 패널 → 원클릭) ──────────────────
function RegisterExecutionModal({
  bid,
  inlineData,
  onClose,
  onSubmit,
  isPending,
}: {
  bid: BidRecommendItem
  inlineData: InlineDecision
  onClose: () => void
  onSubmit: (data: {
    bid_id: number; title: string; agency_name?: string; base_amount?: number
    bid_open_date?: string; announcement_no?: string; industry_name?: string
    recommended_rate?: number; submitted_rate?: number; status: string; note?: string
  }) => void
  isPending: boolean
}) {
  const defaultRate = inlineData.recommended_rate ? (inlineData.recommended_rate * 100).toFixed(4) : ''
  const [submittedRate, setSubmittedRate] = useState(defaultRate)
  const [status, setStatus] = useState<'참여결정' | '투찰완료'>('참여결정')
  const [note, setNote] = useState('')

  const fmt = (n: number) => new Intl.NumberFormat('ko-KR').format(Math.round(n))
  const ratePct = parseFloat(submittedRate) || 0
  const submittedAmt = ratePct > 0 && bid.base_amount ? Math.round(ratePct / 100 * bid.base_amount) : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-800 flex items-center gap-2">
            <Plus className="h-4 w-4 text-blue-600" />
            투찰 등록
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-4 w-4" /></button>
        </div>

        <p className="text-xs text-slate-600 font-medium mb-1 truncate">{bid.title}</p>
        <p className="text-xs text-slate-400 mb-4">{bid.agency_name} · {fmt(bid.base_amount)}원</p>

        {/* AI 추천 투찰율 표시 */}
        {inlineData.recommended_rate && (
          <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 mb-4 flex items-center justify-between">
            <div>
              <p className="text-[10px] text-blue-500 font-medium">AI 추천 투찰율</p>
              <p className="text-xl font-bold text-blue-700 font-mono">{(inlineData.recommended_rate * 100).toFixed(4)}%</p>
            </div>
            <div className="text-right">
              <p className="text-[10px] text-blue-500">낙찰확률</p>
              <p className="text-base font-bold text-blue-600">{(inlineData.win_prob * 100).toFixed(1)}%</p>
            </div>
          </div>
        )}

        {/* 투찰율 입력 */}
        <div className="mb-3">
          <label className="text-xs font-semibold text-slate-600 mb-1.5 block">
            투찰율 (%) <span className="text-slate-400 font-normal">— 추천율 기입 또는 직접 수정</span>
          </label>
          <input
            type="number"
            step="0.0001"
            placeholder={`예: ${defaultRate || '89.7637'}`}
            value={submittedRate}
            onChange={(e) => setSubmittedRate(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {submittedAmt > 0 && (
            <p className="text-xs text-slate-500 mt-1.5">투찰금액: <span className="font-semibold text-slate-700">{fmt(submittedAmt)}원</span></p>
          )}
        </div>

        {/* 상태 선택 */}
        <div className="mb-4">
          <label className="text-xs font-semibold text-slate-600 mb-1.5 block">등록 상태</label>
          <div className="grid grid-cols-2 gap-2">
            {(['참여결정', '투찰완료'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={cn(
                  'py-2 rounded-lg text-sm font-medium border-2 transition-all',
                  status === s
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'
                )}
              >{s}</button>
            ))}
          </div>
        </div>

        {/* 메모 */}
        <div className="mb-5">
          <label className="text-xs font-semibold text-slate-600 mb-1.5 block">메모 (선택)</label>
          <input
            type="text"
            placeholder="특이사항, 전략 메모 등"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="flex gap-2">
          <Button
            className="flex-1 bg-blue-600 hover:bg-blue-700 gap-1.5"
            disabled={isPending}
            onClick={() => onSubmit({
              bid_id: bid.bid_id,
              title: bid.title,
              agency_name: bid.agency_name,
              base_amount: bid.base_amount,
              bid_open_date: bid.open_date ?? undefined,
              recommended_rate: inlineData.recommended_rate ?? undefined,
              submitted_rate: ratePct > 0 ? ratePct / 100 : undefined,
              status,
              note: note || undefined,
            })}
          >
            {isPending ? '등록 중...' : '투찰 등록'}
          </Button>
          <Button variant="outline" className="px-4" onClick={onClose}>취소</Button>
        </div>
      </div>
    </div>
  )
}

function QuickResultModal({
  item,
  onClose,
  onSubmit,
  isPending,
}: {
  item: PendingResultItem
  onClose: () => void
  onSubmit: (data: { result: '낙찰' | '패찰'; winner_rate?: number }) => void
  isPending: boolean
}) {
  const [result, setResult] = useState<'낙찰' | '패찰'>('패찰')
  const [winnerRate, setWinnerRate] = useState('')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-800">빠른 결과 입력</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-4 w-4" /></button>
        </div>
        <p className="text-xs text-slate-500 mb-4 truncate">{item.title}</p>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {(['낙찰', '패찰'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setResult(r)}
              className={cn(
                'py-3 rounded-xl font-semibold text-sm border-2 transition-all',
                result === r
                  ? r === '낙찰' ? 'bg-emerald-500 text-white border-emerald-500' : 'bg-red-500 text-white border-red-500'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
              )}
            >{r}</button>
          ))}
        </div>
        <div className="mb-4">
          <label className="text-xs font-medium text-slate-600 mb-1 block">낙찰자 투찰률 (선택)</label>
          <input
            type="number"
            step="0.0001"
            placeholder="예: 0.8712"
            value={winnerRate}
            onChange={(e) => setWinnerRate(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <Button
          className="w-full gap-2 bg-blue-600 hover:bg-blue-700"
          disabled={isPending}
          onClick={() => onSubmit({ result, winner_rate: winnerRate ? parseFloat(winnerRate) : undefined })}
        >
          {isPending ? '저장 중...' : '결과 저장'}
        </Button>
      </div>
    </div>
  )
}

function fmtAmt(n: number) {
  if (n >= 1e8) return (n / 1e8).toFixed(0) + '억'
  if (n >= 1e4) return (n / 1e4).toFixed(0) + '만'
  return n.toLocaleString()
}

function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null
  const diff = new Date(dateStr).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function DeadlineBadge({ days }: { days: number | null }) {
  if (days === null) return null
  if (days <= 0) return (
    <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-md">오늘마감</span>
  )
  if (days === 1) return (
    <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-md animate-pulse">D-1 긴급</span>
  )
  if (days <= 3) return (
    <span className="bg-orange-400 text-white text-xs font-semibold px-2 py-0.5 rounded-md">D-{days}</span>
  )
  return (
    <span className="bg-slate-100 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md">D-{days}</span>
  )
}

function VerdictBadge({ score }: { score: number | null }) {
  if (score === null) return null
  if (score >= 70) return (
    <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold px-2 py-0.5 rounded-md">GO</span>
  )
  if (score >= 45) return (
    <span className="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold px-2 py-0.5 rounded-md">관심</span>
  )
  return (
    <span className="bg-slate-50 text-slate-500 border border-slate-200 text-xs font-semibold px-2 py-0.5 rounded-md">검토</span>
  )
}

function ScoreBar({ score }: { score: number | null }) {
  const s = score ?? 0
  const color = s >= 70 ? 'bg-emerald-500' : s >= 45 ? 'bg-amber-400' : 'bg-slate-300'
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={cn('h-1.5 rounded-full transition-all', color)} style={{ width: `${s}%` }} />
      </div>
      <span className="text-xs font-mono text-slate-500 w-7 text-right shrink-0">{s.toFixed(0)}점</span>
    </div>
  )
}

// ── 인라인 결정 패널 ──────────────────────────────────────

function GradeBadge({ grade }: { grade: string }) {
  const map: Record<string, string> = {
    S: 'bg-violet-600 text-white',
    A: 'bg-emerald-600 text-white',
    B: 'bg-blue-600 text-white',
    C: 'bg-amber-500 text-white',
    F: 'bg-red-500 text-white',
  }
  return (
    <span className={cn('inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold shrink-0', map[grade] ?? 'bg-slate-300 text-slate-700')}>
      {grade}
    </span>
  )
}

function SignalBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-16 text-slate-500 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={cn('h-1.5 rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-7 text-right font-mono text-slate-500 shrink-0">{pct}%</span>
    </div>
  )
}

function InlineDecisionPanel({
  data,
  baseAmount,
  onExecute,
  onFull,
  isPending,
}: {
  data: InlineDecision
  baseAmount: number
  onExecute: () => void
  onFull: () => void
  isPending: boolean
}) {
  const decisionColor =
    data.go_decision === 'go'   ? 'text-emerald-700 bg-emerald-50 border-emerald-200' :
    data.go_decision === 'pass' ? 'text-red-700 bg-red-50 border-red-200' :
                                  'text-amber-700 bg-amber-50 border-amber-200'
  const decisionLabel =
    data.go_decision === 'go'   ? 'GO — 참여 권장' :
    data.go_decision === 'pass' ? 'NO-GO — 참여 비권장' : 'NEUTRAL — 추가 검토'
  const decisionIcon =
    data.go_decision === 'go'   ? <ShieldCheck className="h-3.5 w-3.5" /> :
    data.go_decision === 'pass' ? <ShieldAlert className="h-3.5 w-3.5" /> :
                                  <Minus className="h-3.5 w-3.5" />

  const fmt = (n: number) => new Intl.NumberFormat('ko-KR').format(Math.round(n))

  return (
    <div className="mt-2 rounded-xl border bg-slate-50 p-3 space-y-3 text-xs">
      {/* 판정 헤더 */}
      <div className="flex items-center gap-2">
        <GradeBadge grade={data.grade} />
        <span className={cn('flex items-center gap-1 px-2 py-1 rounded-lg font-semibold border text-xs', decisionColor)}>
          {decisionIcon}{decisionLabel}
        </span>
        <span className="ml-auto text-slate-400 font-mono">낙찰확률 {(data.win_prob * 100).toFixed(1)}%</span>
      </div>

      {/* 추천 투찰가 */}
      {data.recommended_rate && (
        <div className="bg-white border border-blue-100 rounded-lg px-3 py-2.5 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-slate-400 mb-0.5">AI 추천 투찰율</p>
            <p className="text-lg font-bold text-blue-700 font-mono">
              {(data.recommended_rate * 100).toFixed(4)}%
            </p>
          </div>
          {data.recommended_amount && (
            <div className="text-right">
              <p className="text-[10px] text-slate-400 mb-0.5">추천 금액</p>
              <p className="font-semibold text-slate-700">{fmt(data.recommended_amount)}원</p>
            </div>
          )}
        </div>
      )}

      {/* 신호 분석 */}
      <div className="space-y-1.5">
        <SignalBar label="낙찰확률" value={data.signals.win_prob} />
        <SignalBar label="경쟁강도" value={data.signals.competition} />
        <SignalBar label="기관승률" value={data.signals.agency_rate} />
        <SignalBar label="데이터" value={data.signals.data_quality} />
      </div>

      {/* 근거 & 위험 */}
      <div className="grid grid-cols-2 gap-2">
        {data.reasons.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-emerald-600 mb-1">✓ 긍정 신호</p>
            {data.reasons.slice(0, 2).map((r, i) => (
              <p key={i} className="text-slate-600 leading-tight mb-0.5">· {r}</p>
            ))}
          </div>
        )}
        {data.risk_factors.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-red-500 mb-1">⚠ 위험 신호</p>
            {data.risk_factors.slice(0, 2).map((r, i) => (
              <p key={i} className="text-slate-600 leading-tight mb-0.5">· {r}</p>
            ))}
          </div>
        )}
      </div>

      {/* 유사 공고 낙찰 이력 */}
      {data.similar_wins.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-500 mb-1.5 flex items-center gap-1">
            <History className="h-3 w-3" />
            유사 공고 실제 낙찰율
            {data.avg_winner_rate && (
              <span className="ml-auto text-blue-600 font-mono">평균 {(data.avg_winner_rate * 100).toFixed(3)}%</span>
            )}
          </p>
          <div className="space-y-1">
            {data.similar_wins.slice(0, 3).map((w, i) => (
              <div key={i} className="flex items-center gap-2 bg-white border border-slate-100 rounded-lg px-2 py-1.5">
                <div className="flex-1 min-w-0">
                  <p className="truncate text-slate-700 font-medium">{w.title}</p>
                  <p className="text-slate-400">{w.date?.slice(0, 7)} · {w.agency_name}</p>
                </div>
                {w.winner_rate && (
                  <span className="font-mono font-bold text-blue-700 shrink-0">
                    {(w.winner_rate * 100).toFixed(3)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 액션 버튼 */}
      <div className="flex gap-2 pt-1 border-t border-slate-200">
        <Button
          size="sm"
          className={cn(
            'flex-1 h-8 text-xs gap-1.5',
            data.go_decision === 'pass'
              ? 'bg-slate-400 hover:bg-slate-500 text-white'
              : 'bg-emerald-600 hover:bg-emerald-700 text-white',
          )}
          disabled={isPending}
          onClick={onExecute}
        >
          <Plus className="h-3 w-3" />
          참여 결정
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="flex-1 h-8 text-xs gap-1 border-blue-200 text-blue-600 hover:bg-blue-50"
          onClick={onFull}
        >
          <Crosshair className="h-3 w-3" />
          전체 분석
        </Button>
      </div>
    </div>
  )
}

// ── 추천 이행율 위젯 ─────────────────────────────────────

function ComplianceWidget({ data }: { data: RecommendationCompliance }) {
  const followed = data.outcomes.followed
  const deviated = data.outcomes.deviated
  if (data.with_recommendation === 0) return null
  return (
    <Card className="bg-white border-slate-200 shadow-sm">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <Activity className="h-4 w-4 text-violet-500" />
          AI 추천 이행 분석
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-2.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">추천 이행율</span>
          <span className="font-bold text-violet-700">
            {data.follow_rate != null ? `${(data.follow_rate * 100).toFixed(0)}%` : '-'}
          </span>
        </div>
        {data.follow_rate != null && (
          <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-1.5 bg-violet-500 rounded-full" style={{ width: `${(data.follow_rate * 100).toFixed(0)}%` }} />
          </div>
        )}
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div className="bg-emerald-50 rounded-lg p-2 text-center">
            <p className="text-[10px] text-emerald-600 font-medium">추천 따름</p>
            <p className="text-sm font-bold text-emerald-700">
              {followed.win_rate != null ? `${(followed.win_rate * 100).toFixed(0)}%` : '-'}
            </p>
            <p className="text-[10px] text-emerald-500">{followed.count}건 중 {followed.wins}낙찰</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-2 text-center">
            <p className="text-[10px] text-slate-500 font-medium">추천 무시</p>
            <p className="text-sm font-bold text-slate-600">
              {deviated.win_rate != null ? `${(deviated.win_rate * 100).toFixed(0)}%` : '-'}
            </p>
            <p className="text-[10px] text-slate-400">{deviated.count}건 중 {deviated.wins}낙찰</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

interface KPIData {
  total_bids: number
  total_wins: number
  win_rate: number
  monthly_target: number
  alerts: string[]
}

export default function TodayPage() {
  const navigate = useNavigate()
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())
  const [expandedBidId, setExpandedBidId] = useState<number | null>(null)
  const [inlineDataMap, setInlineDataMap] = useState<Record<number, InlineDecision>>({})
  const [loadingInline, setLoadingInline] = useState<Record<number, boolean>>({})
  const [registerTarget, setRegisterTarget] = useState<{ bid: BidRecommendItem; inline: InlineDecision } | null>(null)

  const toggleInlineDecision = useCallback(async (bid: BidRecommendItem, e: React.MouseEvent) => {
    e.stopPropagation()
    if (expandedBidId === bid.bid_id) {
      setExpandedBidId(null)
      return
    }
    setExpandedBidId(bid.bid_id)
    if (inlineDataMap[bid.bid_id]) return
    setLoadingInline((prev) => ({ ...prev, [bid.bid_id]: true }))
    try {
      const data = await bidsApi.inlineDecision(bid.bid_id)
      setInlineDataMap((prev) => ({ ...prev, [bid.bid_id]: data }))
    } catch {
      // keep expanded but show nothing
    } finally {
      setLoadingInline((prev) => ({ ...prev, [bid.bid_id]: false }))
    }
  }, [expandedBidId, inlineDataMap])

  const today = new Date()
  const dateStr = today.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })

  // AI 추천 공고
  const { data: recommended, isLoading: loadingRec } = useQuery<BidRecommendItem[]>({
    queryKey: ['recommended-bids'],
    queryFn: () => bidsApi.recommended(10),
    staleTime: 300_000,
  })

  // 마감 임박 공고 (7일 이내 open)
  const { data: urgentBids } = useQuery({
    queryKey: ['urgent-bids'],
    queryFn: () => bidsApi.list({ status: 'open', sort_by: 'bid_open_date', size: 20 }),
    staleTime: 120_000,
  })

  // 통계 개요
  const { data: overview } = useQuery<OverviewStatsWithChange>({
    queryKey: ['overview', 3],
    queryFn: () => statsApi.overview(3),
    staleTime: 300_000,
  })

  // KPI 대시보드
  const { data: kpi } = useQuery<KPIData>({
    queryKey: ['kpi-dashboard'],
    queryFn: () => kpiApi.dashboard('MONTHLY'),
    staleTime: 300_000,
  })

  // GO 목록
  const { data: goList } = useQuery({
    queryKey: ['go-list'],
    queryFn: () => selectionApi.goList(14),
    staleTime: 300_000,
  })

  // 피드백 루프 — 결과 입력 대기 목록
  const { data: pendingJournals } = useQuery({
    queryKey: ['journal-pending'],
    queryFn: () => journalApi.pending(),
    staleTime: 60_000,
  })

  // 피드백 통계
  const { data: journalStats } = useQuery<JournalStats>({
    queryKey: ['journal-stats'],
    queryFn: () => journalApi.stats(),
    staleTime: 300_000,
  })

  // 추천 이행율 분석
  const { data: compliance } = useQuery<RecommendationCompliance>({
    queryKey: ['recommendation-compliance'],
    queryFn: () => statsApi.recommendationCompliance(90),
    staleTime: 300_000,
  })

  // 투찰 실행 파이프라인
  const queryClient = useQueryClient()
  const { data: execSummary } = useQuery<ExecutionSummary>({
    queryKey: ['execution-summary'],
    queryFn: () => executionsApi.summary(),
    staleTime: 60_000,
  })
  const createExecMutation = useMutation({
    mutationFn: executionsApi.create,
    onSuccess: () => {
      setRegisterTarget(null)
      queryClient.invalidateQueries({ queryKey: ['execution-summary'] })
      queryClient.invalidateQueries({ queryKey: ['pending-results'] })
      navigate('/executions')
    },
  })

  // 개찰 후 결과 미입력 감지
  const { data: pendingResults } = useQuery<PendingResultItem[]>({
    queryKey: ['pending-results'],
    queryFn: () => executionsApi.pendingResults(72),
    staleTime: 60_000,
  })
  const [quickResultItem, setQuickResultItem] = useState<PendingResultItem | null>(null)
  const quickResultMutation = useMutation({
    mutationFn: (data: { id: number; result: '낙찰' | '패찰'; winner_rate?: number }) =>
      executionsApi.quickResult(data.id, { result: data.result, winner_rate: data.winner_rate }),
    onSuccess: () => {
      setQuickResultItem(null)
      queryClient.invalidateQueries({ queryKey: ['pending-results'] })
      queryClient.invalidateQueries({ queryKey: ['execution-summary'] })
    },
  })

  type PendingJournalItem = { journal_id: number; title: string; agency_name: string; bid_open_date: string | null; submitted_rate: number | null; recommended_rate: number | null }
  const pendingList: PendingJournalItem[] = ((pendingJournals as unknown as { items?: PendingJournalItem[] } | null)?.items ?? [])

  const activeExecCount =
    (execSummary?.status_counts?.['참여결정'] ?? 0) +
    (execSummary?.status_counts?.['투찰완료'] ?? 0) +
    (execSummary?.status_counts?.['개찰대기'] ?? 0)
  const todayClosings = execSummary?.today_closing ?? []

  const urgentList = (urgentBids?.items ?? []).filter((b: { bid_open_date: string | null }) => {
    const d = daysUntil(b.bid_open_date)
    return d !== null && d <= 5
  }).slice(0, 5)

  const topRec = (recommended ?? []).slice(0, 7)
  const goCount = (goList as { go: unknown[] } | null)?.go?.length ?? 0
  const winRate = kpi?.win_rate ?? overview?.avg_win_rate ?? 0
  const totalWins = kpi?.total_wins ?? 0
  const monthlyTarget = kpi?.monthly_target ?? 3

  const toggleCheck = (id: number) => {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-[1440px] mx-auto w-full">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Zap className="h-5 w-5 text-blue-600" />
              오늘의 입찰
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">{dateStr}</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/bids')}
            className="gap-1.5 border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900"
          >
            <Search className="h-3.5 w-3.5" />
            전체공고 검색
          </Button>
        </div>
      </div>

      {/* 결과 입력 모달 */}
      {quickResultItem && (
        <QuickResultModal
          item={quickResultItem}
          onClose={() => setQuickResultItem(null)}
          isPending={quickResultMutation.isPending}
          onSubmit={(data) => quickResultMutation.mutate({ id: quickResultItem.id, ...data })}
        />
      )}

      {/* 투찰 등록 모달 */}
      {registerTarget && (
        <RegisterExecutionModal
          bid={registerTarget.bid}
          inlineData={registerTarget.inline}
          onClose={() => setRegisterTarget(null)}
          isPending={createExecMutation.isPending}
          onSubmit={(data) => createExecMutation.mutate(data)}
        />
      )}

      {/* 콘텐츠 */}
      <div className="flex-1 p-6 space-y-5 max-w-[1440px] mx-auto w-full">

        {/* ── 개찰 결과 미입력 배너 ── */}
        {pendingResults && pendingResults.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <div className="flex items-center gap-3 mb-3">
              <Bell className="h-5 w-5 text-amber-500 shrink-0" />
              <div>
                <span className="font-semibold text-amber-800 text-sm">
                  개찰 완료 {pendingResults.length}건 — 결과 미입력
                </span>
                <p className="text-xs text-amber-600 mt-0.5">
                  결과를 입력하면 AI 예측 정확도가 향상됩니다
                </p>
              </div>
            </div>
            <div className="space-y-1.5">
              {pendingResults.slice(0, 3).map((item) => (
                <div key={item.id} className="flex items-center gap-2 bg-white border border-amber-100 rounded-lg px-3 py-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-slate-700 truncate">{item.title}</p>
                    <p className="text-xs text-slate-500">
                      {item.agency_name} · {item.bid_open_date ? new Date(item.bid_open_date).toLocaleDateString('ko-KR') : '?'}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    className="h-7 px-2.5 text-xs bg-amber-500 hover:bg-amber-600 text-white shrink-0"
                    onClick={() => setQuickResultItem(item)}
                  >
                    결과 입력
                  </Button>
                </div>
              ))}
              {pendingResults.length > 3 && (
                <button
                  className="text-xs text-amber-600 hover:underline w-full text-center py-1"
                  onClick={() => navigate('/executions')}
                >
                  +{pendingResults.length - 3}건 더 보기 →
                </button>
              )}
            </div>
          </div>
        )}

        {/* 상단 KPI 4개 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* AI 추천 공고 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/bids?tab=recommend')}
          >
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">AI 추천 공고</p>
                  <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{topRec.length}건</p>
                  <p className="text-xs text-slate-500 mt-1">오늘 검토 대상</p>
                </div>
                <div className="rounded-xl p-2.5 bg-blue-50 shrink-0">
                  <Sparkles className="h-5 w-5 text-blue-600" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 마감 임박 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/bids?sort=deadline')}
          >
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-red-500" />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">마감 임박</p>
                  <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{urgentList.length}건</p>
                  <p className="text-xs text-slate-500 mt-1">D-5 이내</p>
                </div>
                <div className="rounded-xl p-2.5 bg-red-50 shrink-0">
                  <AlertCircle className="h-5 w-5 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 이번달 수주율 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/performance')}
          >
            <div className={cn('absolute top-0 left-0 right-0 h-0.5', winRate >= 0.3 ? 'bg-emerald-500' : winRate >= 0.2 ? 'bg-amber-500' : 'bg-red-500')} />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">이번달 수주율</p>
                  <p className={cn('text-2xl font-bold mt-1 tabular-nums', winRate >= 0.3 ? 'text-emerald-600' : winRate >= 0.2 ? 'text-amber-600' : 'text-red-600')}>
                    {(winRate * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-slate-500 mt-1">{totalWins}건 / 목표 {monthlyTarget}건</p>
                </div>
                <div className={cn('rounded-xl p-2.5 shrink-0', winRate >= 0.3 ? 'bg-emerald-50' : winRate >= 0.2 ? 'bg-amber-50' : 'bg-red-50')}>
                  <Trophy className={cn('h-5 w-5', winRate >= 0.3 ? 'text-emerald-600' : winRate >= 0.2 ? 'text-amber-600' : 'text-red-600')} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 진행중 투찰 */}
          <Card
            className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => navigate('/executions')}
          >
            <div className={cn('absolute top-0 left-0 right-0 h-0.5', activeExecCount > 0 ? 'bg-violet-500' : 'bg-slate-300')} />
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-500">진행중 투찰</p>
                  <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{activeExecCount}건</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {todayClosings.length > 0
                      ? <span className="text-red-500 font-semibold">오늘 개찰 {todayClosings.length}건</span>
                      : '개찰대기·투찰완료·참여결정'}
                  </p>
                </div>
                <div className="rounded-xl p-2.5 bg-violet-50 shrink-0">
                  <ListChecks className="h-5 w-5 text-violet-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* AI 추천 공고 목록 */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-blue-500" />
                AI 추천 공고
                <span className="bg-blue-50 text-blue-600 border border-blue-200 text-xs font-semibold px-2 py-0.5 rounded-md ml-1">
                  수주가능성 순
                </span>
              </h2>
              <button
                className="text-xs text-blue-600 hover:text-blue-700 font-medium hover:underline"
                onClick={() => navigate('/bids?tab=recommend')}
              >
                전체보기 →
              </button>
            </div>

            {loadingRec ? (
              <div className="space-y-2">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
              </div>
            ) : topRec.length === 0 ? (
              <Card className="bg-white border-slate-200">
                <CardContent className="py-10 text-center text-slate-500 text-sm">
                  추천 공고가 없습니다. 키워드 설정을 확인해주세요.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {topRec.map((b) => {
                  const days = daysUntil(b.open_date)
                  const isChecked = checkedIds.has(b.bid_id)
                  return (
                    <Card
                      key={b.bid_id}
                      className={cn(
                        'group cursor-pointer transition-all border bg-white',
                        isChecked
                          ? 'opacity-50 border-slate-200'
                          : days !== null && days <= 1
                            ? 'border-red-200 hover:border-red-300 hover:shadow-sm'
                            : 'border-slate-200 hover:border-blue-200 hover:shadow-md',
                      )}
                      onClick={() => navigate(`/bids/${b.bid_id}`)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          {/* 체크 */}
                          <button
                            className="mt-0.5 shrink-0"
                            onClick={(e) => { e.stopPropagation(); toggleCheck(b.bid_id) }}
                          >
                            <CheckCircle2 className={cn(
                              'h-4 w-4 transition-colors',
                              isChecked ? 'text-emerald-500' : 'text-slate-200 group-hover:text-slate-300',
                            )} />
                          </button>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-1.5 flex-wrap">
                              <VerdictBadge score={b.score} />
                              {days !== null && days <= 5 && <DeadlineBadge days={days} />}
                              {b.quick_go === 'go' && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200">GO</span>
                              )}
                              {expandedBidId === b.bid_id && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-blue-100 text-blue-700 border border-blue-200">분석중</span>
                              )}
                            </div>
                            <p className="text-sm font-semibold text-slate-800 truncate group-hover:text-blue-700 transition-colors">
                              {b.title}
                            </p>
                            <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                              <span className="flex items-center gap-1">
                                <Building2 className="h-3 w-3 shrink-0" />
                                <span className="truncate max-w-[140px]">{b.agency_name}</span>
                              </span>
                              <span className="font-mono shrink-0">{fmtAmt(b.base_amount)}원</span>
                              {b.open_date && (
                                <span className="flex items-center gap-1 shrink-0">
                                  <Clock className="h-3 w-3" />
                                  {new Date(b.open_date).toLocaleDateString('ko-KR')}
                                </span>
                              )}
                            </div>
                            <div className="mt-2">
                              <ScoreBar score={b.score} />
                            </div>

                            {/* 인라인 결정 패널 */}
                            {expandedBidId === b.bid_id && (
                              loadingInline[b.bid_id] ? (
                                <div className="mt-2 space-y-1.5">
                                  <Skeleton className="h-10 w-full" />
                                  <Skeleton className="h-16 w-full" />
                                  <Skeleton className="h-12 w-full" />
                                </div>
                              ) : inlineDataMap[b.bid_id] ? (
                                <InlineDecisionPanel
                                  data={inlineDataMap[b.bid_id]}
                                  baseAmount={b.base_amount}
                                  isPending={createExecMutation.isPending}
                                  onFull={() => navigate(`/decision?bid=${b.bid_id}`)}
                                  onExecute={() => setRegisterTarget({ bid: b, inline: inlineDataMap[b.bid_id] })}
                                />
                              ) : (
                                <p className="mt-2 text-xs text-red-500">분석 데이터를 불러올 수 없습니다.</p>
                              )
                            )}
                          </div>

                          <div className="flex flex-col gap-1 shrink-0">
                            <Button
                              size="sm"
                              className={cn(
                                'h-7 px-2.5 text-xs gap-1',
                                expandedBidId === b.bid_id
                                  ? 'bg-slate-600 hover:bg-slate-700 text-white'
                                  : 'bg-blue-600 hover:bg-blue-700 text-white',
                              )}
                              onClick={(e) => toggleInlineDecision(b, e)}
                            >
                              {loadingInline[b.bid_id] ? (
                                <span className="h-3 w-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                              ) : expandedBidId === b.bid_id ? (
                                <ChevronUp className="h-3 w-3" />
                              ) : (
                                <Crosshair className="h-3 w-3" />
                              )}
                              {expandedBidId === b.bid_id ? '닫기' : 'AI 결정'}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2.5 text-xs gap-1 text-slate-500 hover:text-blue-600 hover:bg-blue-50"
                              onClick={(e) => { e.stopPropagation(); navigate(`/bids/${b.bid_id}`) }}
                            >
                              상세
                              <ChevronRight className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          {/* 우측 패널 */}
          <div className="space-y-4">
            {/* 마감 임박 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  마감 임박
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-1.5">
                {urgentList.length === 0 ? (
                  <p className="text-xs text-slate-500 py-3 text-center">D-5 이내 마감 공고 없음</p>
                ) : (
                  urgentList.map((b: { id: number; title: string; agency_name: string; base_amount: number; bid_open_date: string | null }) => {
                    const days = daysUntil(b.bid_open_date)
                    return (
                      <div
                        key={b.id}
                        className="flex items-center gap-2 hover:bg-slate-50 rounded-lg p-2 -mx-1 transition-colors group"
                      >
                        <DeadlineBadge days={days} />
                        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => navigate(`/bids/${b.id}`)}>
                          <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-blue-700 transition-colors">
                            {b.title}
                          </p>
                          <p className="text-xs text-slate-500 truncate mt-0.5">
                            {b.agency_name} · {fmtAmt(b.base_amount)}원
                          </p>
                        </div>
                        <Button
                          size="sm"
                          className="h-6 px-2 text-[10px] gap-0.5 bg-blue-600 hover:bg-blue-700 text-white shrink-0"
                          onClick={() => navigate(`/decision?bid=${b.id}`)}
                        >
                          <Crosshair className="h-2.5 w-2.5" />AI결정
                        </Button>
                      </div>
                    )
                  })
                )}
              </CardContent>
            </Card>

            {/* 오늘 개찰 마감 */}
            {todayClosings.length > 0 && (
              <Card className="bg-white border-red-200 shadow-sm ring-1 ring-red-100">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-sm font-semibold text-red-700 flex items-center gap-1.5">
                    <Clock className="h-4 w-4 text-red-500 animate-pulse" />
                    오늘 개찰 마감
                    <span className="ml-auto bg-red-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full">
                      {todayClosings.length}건
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-1.5">
                  {todayClosings.slice(0, 4).map((ex) => (
                    <div
                      key={ex.id}
                      className="flex items-center gap-2 cursor-pointer hover:bg-red-50 rounded-lg p-2 -mx-1 transition-colors group"
                      onClick={() => navigate('/executions')}
                    >
                      <div className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-red-700 transition-colors">
                          {ex.title}
                        </p>
                        <p className="text-xs text-slate-500 truncate mt-0.5">
                          {ex.status} · {ex.agency_name ?? '-'}
                        </p>
                      </div>
                      <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-red-400 shrink-0" />
                    </div>
                  ))}
                  {todayClosings.length > 4 && (
                    <p className="text-xs text-slate-500 text-center pt-1">
                      +{todayClosings.length - 4}건 더보기 →
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {/* 개찰 결과 입력 대기 */}
            {pendingList.length > 0 && (
              <Card className="bg-white border-amber-200 shadow-sm ring-1 ring-amber-100">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-sm font-semibold text-amber-700 flex items-center gap-1.5">
                    <ClipboardCheck className="h-4 w-4 text-amber-500" />
                    개찰 결과 입력 대기
                    <span className="ml-auto bg-amber-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full">
                      {pendingList.length}건
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-1.5">
                  {pendingList.slice(0, 4).map((j) => (
                    <div
                      key={j.journal_id}
                      className="flex items-center gap-2 cursor-pointer hover:bg-amber-50 rounded-lg p-2 -mx-1 transition-colors group"
                      onClick={() => navigate('/journal-history')}
                    >
                      <div className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700 truncate group-hover:text-amber-700">
                          {j.title}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {j.agency_name ?? '-'} · 개찰 {j.bid_open_date ? new Date(j.bid_open_date).toLocaleDateString('ko-KR') : '-'}
                        </p>
                      </div>
                      <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-amber-400 shrink-0" />
                    </div>
                  ))}
                  {pendingList.length > 4 && (
                    <p className="text-xs text-slate-500 text-center pt-1">
                      +{pendingList.length - 4}건 더보기 →
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {/* 추천 이행율 분석 위젯 */}
            {compliance && compliance.with_recommendation > 0 && (
              <ComplianceWidget data={compliance} />
            )}

            {/* AI 피드백 현황 */}
            {journalStats && journalStats.total > 0 && (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                    <BookOpen className="h-4 w-4 text-blue-500" />
                    AI 피드백 현황
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-slate-50 rounded-lg p-2.5 text-center">
                      <p className="text-xs text-slate-400">피드백 완결률</p>
                      <p className="text-base font-bold text-slate-800 mt-0.5">
                        {(journalStats.feedback_completeness * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-2.5 text-center">
                      <p className="text-xs text-slate-400">사정율 MAE</p>
                      <p className="text-base font-bold text-blue-700 mt-0.5 font-mono">
                        {journalStats.avg_srate_mae != null ? (journalStats.avg_srate_mae * 100).toFixed(4) + '%' : '-'}
                      </p>
                    </div>
                  </div>
                  <div className="flex justify-between text-xs text-slate-500 border-t pt-2 mt-1">
                    <span>총 {journalStats.total}건 기록</span>
                    <span>결과 대기 {journalStats.pending_result}건</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 이달 수주 현황 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <BarChart2 className="h-4 w-4 text-blue-500" />
                  이달 수주 현황
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-3">
                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">수주 목표 달성</span>
                    <span className="font-semibold text-slate-700 tabular-nums">{totalWins} / {monthlyTarget}건</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div
                      className={cn(
                        'h-2 rounded-full transition-all',
                        totalWins >= monthlyTarget ? 'bg-emerald-500' : 'bg-blue-500',
                      )}
                      style={{ width: `${Math.min(100, (totalWins / Math.max(monthlyTarget, 1)) * 100)}%` }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center">
                    <p className="text-xs text-slate-500 font-medium">수주율</p>
                    <p className={cn(
                      'text-lg font-bold tabular-nums mt-0.5',
                      winRate >= 0.3 ? 'text-emerald-600' : winRate >= 0.2 ? 'text-amber-600' : 'text-red-500',
                    )}>
                      {(winRate * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center">
                    <p className="text-xs text-slate-500 font-medium">전월대비</p>
                    <p className="text-lg font-bold flex items-center justify-center gap-0.5 mt-0.5">
                      {overview?.win_rate_change_pct != null ? (
                        <>
                          {overview.win_rate_change_pct > 0
                            ? <TrendingUp className="h-4 w-4 text-emerald-500" />
                            : <TrendingDown className="h-4 w-4 text-red-500" />}
                          <span className={cn(
                            'tabular-nums',
                            overview.win_rate_change_pct > 0 ? 'text-emerald-600' : 'text-red-500',
                          )}>
                            {Math.abs(overview.win_rate_change_pct).toFixed(1)}%p
                          </span>
                        </>
                      ) : (
                        <span className="text-slate-500 text-sm">-</span>
                      )}
                    </p>
                  </div>
                </div>

                {kpi?.alerts && kpi.alerts.length > 0 && (
                  <div className="space-y-1.5">
                    {kpi.alerts.slice(0, 2).map((alert, i) => (
                      <div key={i} className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-2.5 py-1.5 flex items-start gap-1">
                        <AlertCircle className="h-3 w-3 shrink-0 mt-0.5" />
                        {alert}
                      </div>
                    ))}
                  </div>
                )}

                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full h-8 text-xs text-slate-500 hover:text-blue-600 hover:bg-blue-50"
                  onClick={() => navigate('/performance')}
                >
                  성과센터 상세보기 →
                </Button>
              </CardContent>
            </Card>

            {/* 빠른 실행 */}
            <Card className="bg-white border-slate-200 shadow-sm">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <Calendar className="h-4 w-4 text-blue-500" />
                  빠른 실행
                </CardTitle>
              </CardHeader>
              <CardContent className="px-3 pb-3 space-y-0.5">
                {[
                  { label: 'AI 투찰 결정',    path: '/decision',       icon: Crosshair,  color: 'text-blue-600',   bg: 'bg-blue-50'    },
                  { label: '투찰 이력 분석',   path: '/journal-history',icon: BookOpen,   color: 'text-amber-600',  bg: 'bg-amber-50'   },
                  { label: '투찰 관리',        path: '/executions',     icon: ListChecks, color: 'text-violet-500', bg: 'bg-violet-50'  },
                  { label: '경쟁사 분석',      path: '/competitors',    icon: Building2,  color: 'text-purple-500', bg: 'bg-purple-50'  },
                  { label: 'GO 판정 공고',     path: '/bid-selection',  icon: Zap,        color: 'text-emerald-600',bg: 'bg-emerald-50' },
                  { label: '성과 대시보드',    path: '/performance',    icon: BarChart2,  color: 'text-slate-500',  bg: 'bg-slate-50'   },
                ].map((item) => (
                  <button
                    key={item.path}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs hover:bg-slate-50 transition-colors text-left group"
                    onClick={() => navigate(item.path)}
                  >
                    <div className={cn('flex h-6 w-6 items-center justify-center rounded-md shrink-0', item.bg)}>
                      <item.icon className={cn('h-3.5 w-3.5', item.color)} />
                    </div>
                    <span className="text-slate-600 group-hover:text-slate-900 font-medium transition-colors">{item.label}</span>
                    <ChevronRight className="h-3 w-3 text-slate-300 group-hover:text-slate-500 ml-auto shrink-0 transition-colors" />
                  </button>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
