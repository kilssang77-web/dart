/**
 * 투찰 이력 분석 — bid_journal 전체 목록 + 성과 분석
 * Phase 5: 실전 투찰 패턴 학습, 낙찰률 추세, 전략별 성과
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { journalApi } from '@/api'
import type { JournalOut, JournalResultRequest, JournalStats } from '@/types'
import {
  BookOpen, Trophy, AlertCircle, CheckCircle2, Clock,
  TrendingUp, ClipboardCheck, ChevronDown, ChevronUp,
  Filter, BarChart2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const ratePct = (n: number) => (n * 100).toFixed(4) + '%'
const fmt = (n: number) => n.toLocaleString('ko-KR')

type ResultFilter = '' | '낙찰' | '패찰' | '무효' | '취소' | 'pending'

function ResultBadge({ result }: { result: string | null }) {
  if (!result) return <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">대기</span>
  const cfg: Record<string, string> = {
    '낙찰': 'bg-emerald-100 text-emerald-700',
    '패찰': 'bg-red-100 text-red-700',
    '무효': 'bg-gray-100 text-gray-600',
    '취소': 'bg-gray-100 text-gray-600',
  }
  return <span className={cn('text-xs px-1.5 py-0.5 rounded font-medium', cfg[result] || 'bg-gray-100 text-gray-600')}>{result}</span>
}

function StrategyBadge({ s }: { s: string | null }) {
  if (!s) return null
  const cfg: Record<string, string> = {
    aggressive:  'bg-red-50 text-red-600',
    balanced:    'bg-blue-50 text-blue-600',
    conservative:'bg-emerald-50 text-emerald-600',
    custom:      'bg-purple-50 text-purple-600',
  }
  const labels: Record<string, string> = { aggressive: '공격형', balanced: '균형형', conservative: '보수형', custom: '직접입력' }
  return <span className={cn('text-xs px-1.5 py-0.5 rounded font-medium', cfg[s] || 'bg-gray-50 text-gray-600')}>{labels[s] || s}</span>
}

function ResultInlineForm({ journal, onClose }: { journal: JournalOut; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<{
    result: '낙찰' | '패찰' | '무효' | '취소'
    actual_srate: string; our_rank: string; total_bidders: string
    winner_rate: string; winner_amount: string; winner_name: string; note: string
  }>({
    result: '패찰', actual_srate: '', our_rank: '', total_bidders: '',
    winner_rate: '', winner_amount: '', winner_name: '', note: '',
  })

  const mut = useMutation({
    mutationFn: () => {
      const req: JournalResultRequest = {
        result: form.result,
        actual_srate:  form.actual_srate  ? parseFloat(form.actual_srate) / 100  : null,
        our_rank:      form.our_rank      ? parseInt(form.our_rank)               : null,
        total_bidders: form.total_bidders ? parseInt(form.total_bidders)          : null,
        winner_rate:   form.winner_rate   ? parseFloat(form.winner_rate) / 100    : null,
        winner_amount: form.winner_amount ? parseInt(form.winner_amount.replace(/,/g,'')) : null,
        winner_name:   form.winner_name || null,
        note:          form.note || null,
      }
      return journalApi.recordResult(journal.id, req)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['journal-list'] })
      qc.invalidateQueries({ queryKey: ['journal-stats'] })
      qc.invalidateQueries({ queryKey: ['journal-pending'] })
      onClose()
    },
  })

  return (
    <div className="mt-3 p-4 bg-gray-50 rounded-lg border space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">결과 *</label>
          <select value={form.result} onChange={e => setForm(f => ({ ...f, result: e.target.value as typeof f.result }))}
            className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400">
            <option value="낙찰">낙찰</option>
            <option value="패찰">패찰</option>
            <option value="무효">무효</option>
            <option value="취소">취소</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">사정율 (%)</label>
          <input value={form.actual_srate} onChange={e => setForm(f => ({ ...f, actual_srate: e.target.value }))}
            placeholder="예) 90.234" className="w-full border rounded px-2 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">우리 순위</label>
          <input type="number" value={form.our_rank} onChange={e => setForm(f => ({ ...f, our_rank: e.target.value }))}
            placeholder="예) 3" className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">총 투찰업체</label>
          <input type="number" value={form.total_bidders} onChange={e => setForm(f => ({ ...f, total_bidders: e.target.value }))}
            placeholder="예) 12" className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">낙찰률 (%)</label>
          <input value={form.winner_rate} onChange={e => setForm(f => ({ ...f, winner_rate: e.target.value }))}
            placeholder="예) 90.234" className="w-full border rounded px-2 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">낙찰금액</label>
          <input value={form.winner_amount} onChange={e => setForm(f => ({ ...f, winner_amount: e.target.value }))}
            placeholder="원 단위" className="w-full border rounded px-2 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </div>
        <div className="md:col-span-2">
          <label className="text-xs text-gray-500 mb-1 block">낙찰업체명</label>
          <input value={form.winner_name} onChange={e => setForm(f => ({ ...f, winner_name: e.target.value }))}
            placeholder="업체명" className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
        </div>
      </div>
      <div className="flex gap-2">
        <button onClick={() => mut.mutate()} disabled={mut.isPending}
          className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1">
          <ClipboardCheck className="w-3.5 h-3.5" />
          {mut.isPending ? '저장 중...' : '결과 저장'}
        </button>
        <button onClick={onClose} className="px-4 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50">취소</button>
      </div>
      {mut.isError && <p className="text-xs text-red-600 flex gap-1"><AlertCircle className="w-3 h-3" />저장 실패</p>}
    </div>
  )
}

function JournalRow({ journal }: { journal: JournalOut }) {
  const [showForm, setShowForm] = useState(false)

  return (
    <div className="border rounded-lg bg-white p-4 space-y-2 hover:shadow-sm transition-shadow">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <ResultBadge result={journal.result} />
            <StrategyBadge s={journal.strategy_chosen} />
            {journal.announcement_no && (
              <span className="text-xs text-gray-400 font-mono">{journal.announcement_no}</span>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1 mt-2 text-xs">
            <div>
              <span className="text-gray-400">실제투찰률</span>
              <div className="font-mono font-semibold">{journal.submitted_rate ? ratePct(journal.submitted_rate) : '-'}</div>
            </div>
            <div>
              <span className="text-gray-400">AI 추천률</span>
              <div className="font-mono text-blue-700">{journal.recommended_rate ? ratePct(journal.recommended_rate) : '-'}</div>
            </div>
            {journal.actual_srate !== null && (
              <div>
                <span className="text-gray-400">실제 사정율</span>
                <div className="font-mono">{ratePct(journal.actual_srate)}</div>
              </div>
            )}
            {journal.winner_rate !== null && (
              <div>
                <span className="text-gray-400">낙찰자 투찰률</span>
                <div className="font-mono text-emerald-700">{ratePct(journal.winner_rate)}</div>
              </div>
            )}
            {journal.rate_gap !== null && (
              <div>
                <span className="text-gray-400">투찰률 편차</span>
                <div className={cn('font-mono font-semibold', Math.abs(journal.rate_gap) < 0.005 ? 'text-emerald-600' : 'text-amber-600')}>
                  {journal.rate_gap > 0 ? '+' : ''}{(journal.rate_gap * 100).toFixed(4)}%
                </div>
              </div>
            )}
            {journal.srate_error !== null && (
              <div>
                <span className="text-gray-400">사정율 오차</span>
                <div className={cn('font-mono font-semibold', Math.abs(journal.srate_error) < 0.003 ? 'text-emerald-600' : 'text-amber-600')}>
                  {journal.srate_error > 0 ? '+' : ''}{(journal.srate_error * 100).toFixed(4)}%
                </div>
              </div>
            )}
            {journal.our_rank !== null && (
              <div>
                <span className="text-gray-400">순위</span>
                <div className="font-semibold">{journal.our_rank}위 / {journal.total_bidders ?? '-'}사</div>
              </div>
            )}
            <div>
              <span className="text-gray-400">기록일</span>
              <div>{journal.created_at ? new Date(journal.created_at).toLocaleDateString('ko-KR') : '-'}</div>
            </div>
          </div>
        </div>

        {!journal.result && (
          <button
            onClick={() => setShowForm(p => !p)}
            className="shrink-0 flex items-center gap-1 text-xs px-3 py-1.5 bg-amber-50 text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-100 font-medium"
          >
            <ClipboardCheck className="w-3.5 h-3.5" />
            결과 입력
            {showForm ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>

      {showForm && !journal.result && (
        <ResultInlineForm journal={journal} onClose={() => setShowForm(false)} />
      )}
    </div>
  )
}

export default function JournalHistoryPage() {
  const [resultFilter, setResultFilter] = useState<ResultFilter>('')
  const [page, setPage] = useState(1)

  const { data: listData, isLoading } = useQuery({
    queryKey: ['journal-list', resultFilter, page],
    queryFn: () => journalApi.list({ result: resultFilter || undefined, page, size: 20 }),
    staleTime: 30_000,
  })

  const { data: stats } = useQuery<JournalStats>({
    queryKey: ['journal-stats'],
    queryFn: () => journalApi.stats(),
    staleTime: 60_000,
  })

  const { data: gapData } = useQuery({
    queryKey: ['journal-gap-analysis'],
    queryFn: () => journalApi.gapAnalysis(),
    staleTime: 60_000,
  })

  const journals: JournalOut[] = (listData as { items?: JournalOut[] } | null)?.items ?? []
  const total: number = (listData as { total?: number } | null)?.total ?? 0
  const totalPages = Math.ceil(total / 20)

  const filters: { label: string; value: ResultFilter }[] = [
    { label: '전체', value: '' },
    { label: '낙찰', value: '낙찰' },
    { label: '패찰', value: '패찰' },
    { label: '결과 대기', value: 'pending' },
  ]

  return (
    <div className="flex flex-col h-full min-h-0 bg-gray-50">
      <div className="bg-white border-b px-6 py-4 flex items-center gap-3 shrink-0">
        <BookOpen className="w-6 h-6 text-amber-600" />
        <div>
          <h1 className="text-lg font-bold text-gray-900">투찰 이력 분석</h1>
          <p className="text-xs text-gray-500">실전 투찰 기록 · AI 피드백 루프 현황</p>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-5xl mx-auto space-y-6">

          {/* 통계 요약 */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: '총 투찰 기록', value: stats.total + '건', icon: BookOpen, color: 'text-blue-600', bg: 'bg-blue-50' },
                { label: '낙찰', value: stats.wins + '건', icon: Trophy, color: 'text-emerald-600', bg: 'bg-emerald-50' },
                { label: '결과 입력 대기', value: stats.pending_result + '건', icon: Clock, color: 'text-amber-600', bg: 'bg-amber-50' },
                { label: '사정율 예측 MAE', value: stats.avg_srate_mae != null ? (stats.avg_srate_mae * 100).toFixed(4) + '%' : '-', icon: BarChart2, color: 'text-purple-600', bg: 'bg-purple-50' },
              ].map(({ label, value, icon: Icon, color, bg }) => (
                <div key={label} className="bg-white rounded-xl border p-4 shadow-sm flex items-center gap-3">
                  <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center shrink-0', bg)}>
                    <Icon className={cn('w-5 h-5', color)} />
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">{label}</div>
                    <div className={cn('text-lg font-bold mt-0.5', color)}>{value}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 성과 분석 */}
          {stats && stats.total > 0 && (
            <div className="bg-white rounded-xl border p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-blue-500" />
                피드백 현황
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="text-center">
                  <div className="text-gray-400 text-xs mb-1">수주율</div>
                  <div className={cn('text-xl font-bold', (stats.win_rate ?? 0) >= 0.3 ? 'text-emerald-600' : 'text-red-600')}>
                    {stats.win_rate != null ? (stats.win_rate * 100).toFixed(1) + '%' : '-'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-gray-400 text-xs mb-1">패찰 시 편차 (avg)</div>
                  <div className="text-xl font-bold text-amber-600 font-mono">
                    {stats.avg_rate_gap_loss != null ? (stats.avg_rate_gap_loss * 100).toFixed(4) + '%' : '-'}
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">낙찰자와의 거리</div>
                </div>
                <div className="text-center">
                  <div className="text-gray-400 text-xs mb-1">피드백 완결률</div>
                  <div className={cn('text-xl font-bold', stats.feedback_completeness >= 0.8 ? 'text-emerald-600' : 'text-amber-600')}>
                    {(stats.feedback_completeness * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-gray-400 text-xs mb-1">AI 편차 (avg rate delta)</div>
                  <div className="text-xl font-bold text-blue-600 font-mono">
                    {stats.avg_rate_delta != null ? (stats.avg_rate_delta * 100).toFixed(4) + '%' : '-'}
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">AI 추천 vs 실제 투찰</div>
                </div>
              </div>

              {/* 패찰 편차 해석 */}
              {stats.avg_rate_gap_loss != null && (
                <div className={cn(
                  'mt-4 text-xs p-3 rounded-lg flex items-start gap-2',
                  Math.abs(stats.avg_rate_gap_loss) < 0.005 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                )}>
                  {Math.abs(stats.avg_rate_gap_loss) < 0.005
                    ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    : <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />}
                  <span>
                    패찰 시 평균 편차 {(Math.abs(stats.avg_rate_gap_loss) * 100).toFixed(4)}% —&nbsp;
                    {stats.avg_rate_gap_loss > 0
                      ? '우리가 낙찰자보다 낮게 입찰 중. 투찰률을 소폭 상향 검토.'
                      : '우리가 낙찰자보다 높게 입찰 중. 투찰률을 소폭 하향 검토.'}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* 투찰 패턴 분석 — gap analysis */}
          {gapData && gapData.summary.total > 0 && (
            <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
              <div className="px-5 py-3 border-b bg-blue-50 flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-blue-600" />
                <span className="font-semibold text-sm text-blue-800">투찰 패턴 분석</span>
                <span className="text-xs text-blue-600">— 우리 투찰 vs 낙찰자 거리</span>
              </div>
              <div className="p-5 space-y-5">
                {/* 4대 지표 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div className="text-center bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-400 mb-1">분석 건수</div>
                    <div className="text-xl font-bold text-gray-800">{gapData.summary.total}건</div>
                  </div>
                  <div className="text-center bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-400 mb-1">낙찰자와 평균 거리</div>
                    <div className={cn('text-xl font-bold font-mono', (gapData.summary.avg_abs_gap_pct ?? 0) > 5 ? 'text-red-600' : 'text-amber-600')}>
                      {gapData.summary.avg_abs_gap_pct?.toFixed(1) ?? '-'}%
                    </div>
                  </div>
                  <div className="text-center bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-400 mb-1">방향성 (낙찰자 대비)</div>
                    <div className={cn('text-xl font-bold font-mono', (gapData.summary.avg_signed_gap_pct ?? 0) > 0 ? 'text-blue-600' : 'text-red-600')}>
                      {gapData.summary.avg_signed_gap_pct != null ? (gapData.summary.avg_signed_gap_pct > 0 ? '+' : '') + gapData.summary.avg_signed_gap_pct.toFixed(1) + '%' : '-'}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {(gapData.summary.avg_signed_gap_pct ?? 0) > 0 ? '낙찰자 위에서 패찰' : '낙찰자 아래서 패찰'}
                    </div>
                  </div>
                  <div className="text-center bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-400 mb-1">1% 이내 근접 투찰</div>
                    <div className={cn('text-xl font-bold', gapData.summary.within_1pct > 0 ? 'text-emerald-600' : 'text-gray-400')}>
                      {gapData.summary.within_1pct}건
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">아깝게 패찰</div>
                  </div>
                </div>

                {/* Gap 분포 히스토그램 */}
                <div>
                  <div className="text-xs font-semibold text-gray-600 mb-2">낙찰자와의 거리 분포 (버킷: 1% 단위)</div>
                  <div className="flex items-end gap-0.5 h-16 bg-gray-50 rounded-lg p-2">
                    {gapData.histogram.map((b, i) => {
                      const maxCnt = Math.max(...gapData.histogram.map(x => x.count), 1)
                      const h = (b.count / maxCnt) * 100
                      const isClose = i <= 1
                      return (
                        <div
                          key={i}
                          className="relative flex-1 group cursor-default"
                          title={`${i}~${i+1}%: ${b.count}건`}
                        >
                          <div
                            className={cn('w-full rounded-t transition-all', isClose ? 'bg-emerald-400' : i <= 4 ? 'bg-amber-300' : 'bg-red-300')}
                            style={{ height: `${Math.max(h, b.count > 0 ? 4 : 0)}%` }}
                          />
                        </div>
                      )
                    })}
                  </div>
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span className="text-emerald-600">← 근접 (낙찰 가능)</span>
                    <span>낙찰자와의 거리</span>
                    <span className="text-red-500">멀수록 개선 필요 →</span>
                  </div>
                </div>

                {/* 월별 추세 */}
                {gapData.monthly.length > 1 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-600 mb-2">월별 평균 gap 추세 (낮을수록 개선)</div>
                    <div className="flex items-end gap-1 h-12">
                      {gapData.monthly.map((m, i) => {
                        const maxGap = Math.max(...gapData.monthly.map(x => x.avg_gap ?? 0), 1)
                        const h = ((m.avg_gap ?? 0) / maxGap) * 100
                        const isLatest = i === gapData.monthly.length - 1
                        return (
                          <div key={m.month} className="flex-1 flex flex-col items-center gap-0.5" title={`${m.month}: ${m.avg_gap?.toFixed(1)}% (${m.total}건)`}>
                            <div
                              className={cn('w-full rounded-t', isLatest ? 'bg-blue-500' : 'bg-gray-300')}
                              style={{ height: `${Math.max(h, 4)}%` }}
                            />
                            <span className="text-xs text-gray-400 truncate w-full text-center" style={{ fontSize: '10px' }}>
                              {m.month.slice(5)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* 인사이트 메시지 */}
                <div className={cn(
                  'text-xs p-3 rounded-lg flex items-start gap-2',
                  (gapData.summary.avg_abs_gap_pct ?? 0) > 10
                    ? 'bg-red-50 text-red-700 border border-red-100'
                    : (gapData.summary.avg_abs_gap_pct ?? 0) > 3
                      ? 'bg-amber-50 text-amber-700 border border-amber-100'
                      : 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                )}>
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>
                    {(gapData.summary.avg_signed_gap_pct ?? 0) > 0
                      ? `우리가 낙찰자보다 평균 ${gapData.summary.avg_abs_gap_pct?.toFixed(1)}% 높게 투찰 중. `
                      : `우리가 낙찰자보다 평균 ${gapData.summary.avg_abs_gap_pct?.toFixed(1)}% 낮게 투찰 중. `}
                    {(gapData.summary.avg_abs_gap_pct ?? 0) > 5
                      ? 'AI 추천 투찰률 적극 활용으로 격차를 줄이세요.'
                      : '현재 투찰 패턴이 안정적입니다. AI 추천을 참고해 정밀도를 높이세요.'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* 목록 필터 */}
          <div className="flex items-center gap-3">
            <Filter className="w-4 h-4 text-gray-400" />
            <div className="flex gap-1">
              {filters.map(f => (
                <button
                  key={f.value}
                  onClick={() => { setResultFilter(f.value); setPage(1) }}
                  className={cn(
                    'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                    resultFilter === f.value
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border text-gray-600 hover:bg-gray-50'
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <span className="text-xs text-gray-400 ml-auto">총 {fmt(total)}건</span>
          </div>

          {/* 이력 목록 */}
          {isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map(i => (
                <div key={i} className="h-24 bg-white rounded-xl border animate-pulse" />
              ))}
            </div>
          ) : journals.length === 0 ? (
            <div className="bg-white rounded-xl border p-16 text-center">
              <BookOpen className="w-10 h-10 text-gray-200 mx-auto mb-3" />
              <div className="text-gray-400 text-sm">투찰 기록이 없습니다.<br />AI 투찰 결정 화면에서 투찰률을 기록해보세요.</div>
            </div>
          ) : (
            <div className="space-y-3">
              {journals.map(j => <JournalRow key={j.id} journal={j} />)}
            </div>
          )}

          {/* 페이지네이션 */}
          {totalPages > 1 && (
            <div className="flex justify-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-4 py-2 border rounded-lg text-sm disabled:opacity-40 hover:bg-gray-50"
              >
                이전
              </button>
              <span className="px-4 py-2 text-sm text-gray-600">{page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-4 py-2 border rounded-lg text-sm disabled:opacity-40 hover:bg-gray-50"
              >
                다음
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
