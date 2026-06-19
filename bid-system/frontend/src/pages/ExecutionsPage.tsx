import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ClipboardList, Plus, Upload, CheckCircle2, XCircle, Clock, Trophy,
  AlertTriangle, SkipForward, Loader2, ChevronDown, ChevronUp, RefreshCw,
  Search, Filter, X, FileText, LayoutList, LayoutGrid, Bell, Zap, ChevronRight,
} from 'lucide-react'
import { executionsApi, bidsApi } from '../api'
import type { BidExecution, ExecutionStatus, DefeatCauseStat, DefeatSummaryRecentItem, UpcomingOpening } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

// ── 상수 ────────────────────────────────────────────────────

const STATUS_META: Record<ExecutionStatus, { label: string; color: string; colBg: string; icon: React.ReactNode }> = {
  '검토중':   { label: '검토중',   color: 'bg-gray-100 text-gray-700 border-gray-300',       colBg: 'bg-gray-50',   icon: <Clock className="h-3 w-3" /> },
  '참여결정': { label: '참여결정', color: 'bg-blue-100 text-blue-700 border-blue-300',       colBg: 'bg-blue-50',   icon: <CheckCircle2 className="h-3 w-3" /> },
  '투찰완료': { label: '투찰완료', color: 'bg-indigo-100 text-indigo-700 border-indigo-300', colBg: 'bg-indigo-50', icon: <FileText className="h-3 w-3" /> },
  '개찰대기': { label: '개찰대기', color: 'bg-yellow-100 text-yellow-700 border-yellow-300', colBg: 'bg-yellow-50', icon: <Clock className="h-3 w-3" /> },
  '낙찰':     { label: '낙찰',     color: 'bg-green-100 text-green-700 border-green-300',     colBg: 'bg-green-50',  icon: <Trophy className="h-3 w-3" /> },
  '패찰':     { label: '패찰',     color: 'bg-red-100 text-red-700 border-red-300',           colBg: 'bg-red-50',    icon: <XCircle className="h-3 w-3" /> },
  '포기':     { label: '포기',     color: 'bg-slate-100 text-slate-500 border-slate-300',     colBg: 'bg-slate-50',  icon: <SkipForward className="h-3 w-3" /> },
}

const STATUS_ORDER: ExecutionStatus[] = ['검토중', '참여결정', '투찰완료', '개찰대기', '낙찰', '패찰', '포기']

const DEFEAT_CAUSE_COLORS: Record<string, string> = {
  '투찰률과도':  'text-red-600',
  '경쟁사과다':  'text-orange-500',
  '적격부족':    'text-purple-600',
  '시장변동':    'text-blue-600',
  '정보부족':    'text-gray-500',
  '기타':        'text-gray-400',
}

type ViewMode = 'list' | 'kanban'

// ── 금액 포맷 ────────────────────────────────────────────────

const fmt = (n: number | null | undefined) =>
  n != null ? Math.round(n / 10000).toLocaleString() + '만' : '-'

const fmtRate = (r: number | null | undefined) =>
  r != null ? (r * 100).toFixed(4) + '%' : '-'

// ── 상태 배지 ────────────────────────────────────────────────

function StatusBadge({ status }: { status: ExecutionStatus }) {
  const m = STATUS_META[status] ?? { label: status, color: 'bg-gray-100 text-gray-600 border-gray-300', icon: null }
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-sm font-medium border', m.color)}>
      {m.icon}
      {m.label}
    </span>
  )
}

// ── 요약 카드 ────────────────────────────────────────────────

function SummaryBar() {
  const { data } = useQuery({
    queryKey: ['executions-summary'],
    queryFn: executionsApi.summary,
    refetchInterval: 60_000,
  })

  const counts = (data?.status_counts ?? {}) as Partial<Record<ExecutionStatus, number>>
  const winRate = (() => {
    const won = counts['낙찰'] ?? 0
    const finished = won + (counts['패찰'] ?? 0)
    return finished > 0 ? Math.round((won / finished) * 100) : null
  })()

  return (
    <div className="grid grid-cols-4 gap-3 sm:grid-cols-7">
      {STATUS_ORDER.map((s) => (
        <Card key={s} className="p-3 text-center">
          <div className={cn('text-lg font-bold', s === '낙찰' ? 'text-green-600' : s === '패찰' ? 'text-red-500' : 'text-gray-800')}>
            {counts[s] ?? 0}
          </div>
          <div className="text-sm text-muted-foreground mt-0.5">{s}</div>
        </Card>
      ))}
      {winRate != null && (
        <Card className="p-3 text-center col-span-4 sm:col-span-7">
          <div className="text-sm text-muted-foreground">
            투찰 성공률 <span className="text-lg font-bold text-green-600">{winRate}%</span>
            &nbsp;(낙찰 {counts['낙찰'] ?? 0} / 패찰 {counts['패찰'] ?? 0})
          </div>
        </Card>
      )}
    </div>
  )
}

// ── 개찰 임박 공고 패널 ──────────────────────────────────────

const URGENCY_META = {
  today:    { label: 'D-Day', bg: 'bg-red-50',    border: 'border-red-300',    badge: 'bg-red-500 text-white',       dot: 'bg-red-500',    pulse: true  },
  tomorrow: { label: 'D-1',   bg: 'bg-orange-50', border: 'border-orange-300', badge: 'bg-orange-400 text-white',    dot: 'bg-orange-400', pulse: false },
  soon:     { label: 'D-2~3', bg: 'bg-yellow-50', border: 'border-yellow-300', badge: 'bg-yellow-400 text-white',    dot: 'bg-yellow-400', pulse: false },
  normal:   { label: '',      bg: 'bg-gray-50',   border: 'border-gray-200',   badge: 'bg-gray-300 text-gray-700',   dot: 'bg-gray-300',   pulse: false },
  past:     { label: '지남',  bg: 'bg-gray-50',   border: 'border-gray-200',   badge: 'bg-gray-300 text-gray-500',   dot: 'bg-gray-300',   pulse: false },
}

function UpcomingOpeningsPanel() {
  const navigate = useNavigate()
  const [days, setDays] = useState(7)
  const [collapsed, setCollapsed] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['upcoming-openings', days],
    queryFn: () => bidsApi.upcomingOpenings(days),
    staleTime: 3 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  const items = data?.items ?? []
  const todayCount  = items.filter((i) => i.urgency === 'today').length
  const urgentCount = items.filter((i) => ['today', 'tomorrow'].includes(i.urgency)).length

  const fmtAmt = (n: number) => n > 0 ? Math.round(n / 10000).toLocaleString() + '만' : '-'
  const dLabel = (item: UpcomingOpening) => {
    if (item.urgency === 'today') return item.hours_left > 0 ? `${item.hours_left}시간 후` : 'D-Day'
    if (item.urgency === 'tomorrow') return 'D-1'
    return `D-${item.days_left}`
  }

  return (
    <Card className={cn('border-2 transition-colors', urgentCount > 0 ? 'border-red-200' : 'border-gray-200')}>
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Bell className={cn('h-4 w-4', urgentCount > 0 ? 'text-red-500' : 'text-gray-400')} />
            개찰 임박 공고
            {urgentCount > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-500 text-white">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                </span>
                {urgentCount}건 긴급
              </span>
            )}
            {todayCount > 0 && (
              <span className="text-xs text-red-600 font-normal">오늘 개찰 {todayCount}건!</span>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="text-xs border rounded px-2 py-1 text-gray-600 bg-white"
            >
              {[3, 5, 7, 14].map((d) => (
                <option key={d} value={d}>D+{d}까지</option>
              ))}
            </select>
            <button
              onClick={() => setCollapsed((c) => !c)}
              className="text-gray-400 hover:text-gray-600"
            >
              {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </CardHeader>

      {!collapsed && (
        <CardContent className="pt-0 px-4 pb-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-400">
              향후 {days}일 내 개찰 공고 없음
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((item) => {
                const meta = URGENCY_META[item.urgency] ?? URGENCY_META.normal
                return (
                  <div
                    key={item.id}
                    className={cn(
                      'flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-shadow hover:shadow-sm',
                      meta.bg, meta.border
                    )}
                  >
                    {/* D-day 뱃지 */}
                    <div className={cn('shrink-0 w-14 text-center py-1 rounded-md text-xs font-bold', meta.badge)}>
                      {dLabel(item)}
                    </div>

                    {/* 공고 정보 */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-800 truncate">{item.title}</div>
                      <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5 flex-wrap">
                        <span className="truncate max-w-[160px]">{item.agency_name}</span>
                        {item.industry_name && <span className="text-gray-400">· {item.industry_name}</span>}
                        {item.base_amount > 0 && <span className="text-blue-600 font-medium">{fmtAmt(item.base_amount)}</span>}
                        <span className="text-gray-400 font-mono">{item.bid_open_date.slice(0, 16).replace('T', ' ')}</span>
                      </div>
                    </div>

                    {/* AI 투찰 결정 버튼 */}
                    <button
                      onClick={() => navigate(`/decision?bid=${item.id}`)}
                      className={cn(
                        'shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                        item.urgency === 'today'
                          ? 'bg-red-600 text-white hover:bg-red-700'
                          : item.urgency === 'tomorrow'
                          ? 'bg-orange-500 text-white hover:bg-orange-600'
                          : 'bg-blue-600 text-white hover:bg-blue-700'
                      )}
                    >
                      <Zap className="h-3 w-3" />
                      AI 투찰 결정
                    </button>
                  </div>
                )
              })}

              {items.length >= 50 && (
                <div className="text-center text-xs text-gray-400 pt-1">
                  상위 50건 표시. 기간을 줄이면 더 정밀하게 확인할 수 있습니다.
                </div>
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}

// ── 업로드 버튼 ──────────────────────────────────────────────

function UploadButton({
  label,
  onFile,
  loading,
}: {
  label: string
  onFile: (f: File) => void
  loading: boolean
}) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept=".xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = ''
        }}
      />
      <Button variant="outline" size="sm" onClick={() => ref.current?.click()} disabled={loading}>
        {loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Upload className="h-4 w-4 mr-1" />}
        {label}
      </Button>
    </>
  )
}

// ── 칸반 카드 ────────────────────────────────────────────────

function KanbanCard({
  exec,
  onStatusChange,
}: {
  exec: BidExecution
  onStatusChange: (id: number, status: ExecutionStatus) => void
}) {
  const nextStatuses = (() => {
    const idx = STATUS_ORDER.indexOf(exec.status)
    if (exec.status === '개찰대기') return ['낙찰', '패찰'] as ExecutionStatus[]
    if (idx < 0 || idx >= STATUS_ORDER.length - 1) return []
    return [STATUS_ORDER[idx + 1]] as ExecutionStatus[]
  })()

  return (
    <div className="bg-white border rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow group">
      {/* 제목 */}
      <div className="text-sm font-medium leading-snug line-clamp-2 mb-2 text-gray-800">
        {exec.title}
      </div>

      {/* 메타 정보 */}
      <div className="space-y-1 text-sm text-muted-foreground">
        {exec.agency_name && (
          <div className="truncate">{exec.agency_name}</div>
        )}
        <div className="flex gap-2 flex-wrap">
          {exec.base_amount != null && <span>{fmt(exec.base_amount)}</span>}
          {exec.bid_open_date && (
            <span className={cn(
              new Date(exec.bid_open_date) < new Date() && !['낙찰','패찰','포기'].includes(exec.status)
                ? 'text-red-500 font-medium'
                : ''
            )}>
              {exec.bid_open_date.slice(0, 10)}
            </span>
          )}
        </div>
        {exec.submitted_rate != null && (
          <div className="text-blue-600 font-medium">투찰 {fmtRate(exec.submitted_rate)}</div>
        )}
        {exec.status === '낙찰' && exec.winner_rate != null && (
          <div className="text-green-600 font-medium">낙찰률 {fmtRate(exec.winner_rate)}</div>
        )}
        {exec.status === '패찰' && exec.winner_rate != null && (
          <div className="text-red-500">낙찰자 {fmtRate(exec.winner_rate)}</div>
        )}
      </div>

      {/* 상태 전환 버튼 */}
      {nextStatuses.length > 0 && (
        <div className="flex gap-1 mt-2 pt-2 border-t">
          {nextStatuses.map((ns) => (
            <button
              key={ns}
              onClick={() => onStatusChange(exec.id, ns)}
              className={cn(
                'flex-1 text-xs py-1 rounded border font-medium transition-colors',
                ns === '낙찰'
                  ? 'border-green-300 text-green-700 hover:bg-green-50'
                  : ns === '패찰'
                  ? 'border-red-300 text-red-600 hover:bg-red-50'
                  : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              )}
            >
              → {ns}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── 칸반 컬럼 ────────────────────────────────────────────────

function KanbanColumn({
  status,
  items,
  onStatusChange,
}: {
  status: ExecutionStatus
  items: BidExecution[]
  onStatusChange: (id: number, status: ExecutionStatus) => void
}) {
  const meta = STATUS_META[status] ?? { label: status, color: 'bg-gray-100 text-gray-700 border-gray-300', colBg: 'bg-gray-50', icon: null }

  return (
    <div className="flex flex-col min-w-[220px] max-w-[260px] flex-shrink-0">
      {/* 컬럼 헤더 */}
      <div className={cn('flex items-center gap-2 px-3 py-2 rounded-t-lg border border-b-0', meta.colBg)}>
        <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border', meta.color)}>
          {meta.icon}
          {meta.label}
        </span>
        <span className="text-sm text-muted-foreground ml-auto font-medium">{items.length}</span>
      </div>

      {/* 카드 목록 */}
      <div className={cn('flex-1 rounded-b-lg border p-2 space-y-2 min-h-[120px]', meta.colBg)}>
        {items.length === 0 ? (
          <div className="flex items-center justify-center h-16 border-2 border-dashed border-gray-200 rounded-lg">
            <span className="text-sm text-muted-foreground">없음</span>
          </div>
        ) : (
          items.map((exec) => (
            <KanbanCard key={exec.id} exec={exec} onStatusChange={onStatusChange} />
          ))
        )}
      </div>
    </div>
  )
}

// ── 칸반 보드 ────────────────────────────────────────────────

function KanbanBoard({
  items,
  onStatusChange,
}: {
  items: BidExecution[]
  onStatusChange: (id: number, status: ExecutionStatus) => void
}) {
  const grouped = STATUS_ORDER.reduce<Record<ExecutionStatus, BidExecution[]>>(
    (acc, s) => {
      acc[s] = items.filter((e) => e.status === s)
      return acc
    },
    {} as Record<ExecutionStatus, BidExecution[]>
  )

  return (
    <div className="overflow-x-auto pb-4">
      <div className="flex gap-3 min-w-max">
        {STATUS_ORDER.map((s) => (
          <KanbanColumn
            key={s}
            status={s}
            items={grouped[s]}
            onStatusChange={onStatusChange}
          />
        ))}
      </div>
    </div>
  )
}

// ── 행 상세 패널 (목록 뷰) ───────────────────────────────────

function ExecutionRow({
  exec,
  onStatusChange,
}: {
  exec: BidExecution
  onStatusChange: (id: number, status: ExecutionStatus) => void
}) {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data: analysis } = useQuery({
    queryKey: ['defeat-analysis', exec.id],
    queryFn: () => executionsApi.defeatAnalysis(exec.id),
    enabled: open && exec.status === '패찰',
  })

  const nextStatuses = (() => {
    const idx = STATUS_ORDER.indexOf(exec.status)
    if (exec.status === '개찰대기') return ['낙찰', '패찰'] as ExecutionStatus[]
    if (idx < 0 || idx >= STATUS_ORDER.length - 1) return []
    return [STATUS_ORDER[idx + 1]] as ExecutionStatus[]
  })()

  return (
    <div className="border rounded-lg mb-2 bg-white shadow-sm">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={exec.status} />
            <span className="text-sm font-medium truncate max-w-sm">{exec.title}</span>
          </div>
          <div className="text-sm text-muted-foreground mt-0.5 flex gap-3 flex-wrap">
            <span>{exec.agency_name ?? '-'}</span>
            <span>기초 {fmt(exec.base_amount)}</span>
            {exec.bid_open_date && (
              <span>개찰 {exec.bid_open_date.slice(0, 10)}</span>
            )}
            {exec.submitted_rate && (
              <span>투찰율 {fmtRate(exec.submitted_rate)}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {nextStatuses.map((ns) => (
            <Button
              key={ns}
              size="sm"
              variant={ns === '낙찰' ? 'default' : ns === '패찰' ? 'destructive' : 'outline'}
              className="text-xs h-7"
              onClick={(e) => {
                e.stopPropagation()
                onStatusChange(exec.id, ns)
              }}
            >
              → {ns}
            </Button>
          ))}
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </div>

      {open && (
        <div className="px-4 pb-4 border-t bg-gray-50 text-sm">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
            <div>
              <div className="text-sm text-muted-foreground">공고번호</div>
              <div className="font-mono text-xs">{exec.announcement_no ?? '-'}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">낙찰하한율</div>
              <div>{fmtRate(exec.floor_rate)}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">A값</div>
              <div>{exec.a_value != null ? exec.a_value.toLocaleString() : '-'}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">추천 투찰율</div>
              <div className="text-blue-600 font-medium">{fmtRate(exec.recommended_rate)}</div>
            </div>
            {exec.winner_rate != null && (
              <>
                <div>
                  <div className="text-sm text-muted-foreground">낙찰자</div>
                  <div className="truncate">{exec.winner_name ?? '-'}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">낙찰률</div>
                  <div>{fmtRate(exec.winner_rate)}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">낙찰금액</div>
                  <div>{fmt(exec.winner_amount)}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">순위 / 참여</div>
                  <div>{exec.result_rank ?? '-'} / {exec.total_bidders ?? '-'}</div>
                </div>
              </>
            )}
          </div>

          {exec.status === '패찰' && analysis && (
            <div className="mt-3 p-3 rounded-md bg-red-50 border border-red-100">
              <div className="text-xs font-semibold text-red-600 mb-1">패찰 원인 분석</div>
              <div className="flex gap-4 flex-wrap text-xs">
                <span>
                  주원인:{' '}
                  <span className={cn('font-bold', DEFEAT_CAUSE_COLORS[analysis.cause_primary] ?? 'text-gray-600')}>
                    {analysis.cause_primary}
                  </span>
                </span>
                {analysis.winner_gap_pct != null && (
                  <span>낙찰자와 차이: {analysis.winner_gap_pct > 0 ? '+' : ''}{analysis.winner_gap_pct}%p</span>
                )}
                {analysis.next_rate_adj != null && analysis.next_rate_adj !== 0 && (
                  <span className="text-blue-600">
                    다음 조정: {analysis.next_rate_adj > 0 ? '+' : ''}{(analysis.next_rate_adj * 100).toFixed(4)}%p
                  </span>
                )}
              </div>
              {analysis.improvement && (
                <div className="text-xs text-gray-600 mt-1">{analysis.improvement}</div>
              )}
            </div>
          )}

          {exec.note && (
            <div className="mt-2 text-xs text-gray-500 italic">{exec.note}</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 신규 등록 모달 ───────────────────────────────────────────

function NewExecutionForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    title: '',
    agency_name: '',
    base_amount: '',
    bid_open_date: '',
    announcement_no: '',
    floor_rate: '',
    note: '',
  })

  const mut = useMutation({
    mutationFn: () =>
      executionsApi.create({
        title: form.title,
        agency_name: form.agency_name || undefined,
        base_amount: form.base_amount ? parseInt(form.base_amount.replace(/,/g, '')) : undefined,
        bid_open_date: form.bid_open_date || undefined,
        announcement_no: form.announcement_no || undefined,
        floor_rate: form.floor_rate ? parseFloat(form.floor_rate) : undefined,
        note: form.note || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['executions'] })
      qc.invalidateQueries({ queryKey: ['executions-summary'] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">투찰 등록 (검토중)</h2>
          <button onClick={onClose}><X className="h-5 w-5 text-muted-foreground" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-muted-foreground">공고명 *</label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="공고명 입력"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-muted-foreground">발주기관</label>
              <Input
                value={form.agency_name}
                onChange={(e) => setForm((f) => ({ ...f, agency_name: e.target.value }))}
                placeholder="발주기관명"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">개찰일</label>
              <Input
                type="date"
                value={form.bid_open_date}
                onChange={(e) => setForm((f) => ({ ...f, bid_open_date: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-muted-foreground">기초금액 (원)</label>
              <Input
                value={form.base_amount}
                onChange={(e) => setForm((f) => ({ ...f, base_amount: e.target.value }))}
                placeholder="1000000000"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">낙찰하한율</label>
              <Input
                value={form.floor_rate}
                onChange={(e) => setForm((f) => ({ ...f, floor_rate: e.target.value }))}
                placeholder="0.8775"
              />
            </div>
          </div>
          <div>
            <label className="text-sm text-muted-foreground">공고번호</label>
            <Input
              value={form.announcement_no}
              onChange={(e) => setForm((f) => ({ ...f, announcement_no: e.target.value }))}
              placeholder="20250001234"
            />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">메모</label>
            <Input
              value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              placeholder="참고사항"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="outline" onClick={onClose}>취소</Button>
          <Button
            onClick={() => mut.mutate()}
            disabled={!form.title || mut.isPending}
          >
            {mut.isPending && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
            등록
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── 메인 페이지 ──────────────────────────────────────────────

export default function ExecutionsPage() {
  const qc = useQueryClient()
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [showNew, setShowNew] = useState(false)
  const [importMsg, setImportMsg] = useState<string | null>(null)
  const [showDefeat, setShowDefeat] = useState(false)

  // 칸반 모드는 항상 전체 조회, 목록 모드는 필터 적용
  const { data, isLoading } = useQuery({
    queryKey: ['executions', viewMode === 'kanban' ? 'all' : statusFilter],
    queryFn: () =>
      executionsApi.list({
        status: viewMode === 'kanban' || statusFilter === 'all' ? undefined : statusFilter,
        size: 200,
      }),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ExecutionStatus }) =>
      executionsApi.update(id, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['executions'] })
      qc.invalidateQueries({ queryKey: ['executions-summary'] })
    },
  })

  const sucviewMut = useMutation({
    mutationFn: (file: File) => executionsApi.importSucview(file),
    onSuccess: (r) => {
      setImportMsg(`SUCVIEW 가져오기 완료: ${r.imported}건 등록, ${r.skipped}건 건너뜀, 경쟁사 ${r.competitors_added}개 추가`)
      qc.invalidateQueries({ queryKey: ['executions'] })
      qc.invalidateQueries({ queryKey: ['executions-summary'] })
    },
    onError: () => setImportMsg('업로드 실패. xlsx/xls 파일을 확인해주세요.'),
  })

  const inpoMut = useMutation({
    mutationFn: (file: File) => executionsApi.importInpoHistory(file),
    onSuccess: (r) => {
      setImportMsg(`인포 이력 가져오기 완료: ${r.imported}건 등록, ${r.skipped}건 건너뜀`)
      qc.invalidateQueries({ queryKey: ['executions'] })
      qc.invalidateQueries({ queryKey: ['executions-summary'] })
    },
    onError: () => setImportMsg('업로드 실패. xlsx/xls 파일을 확인해주세요.'),
  })

  const { data: defeatData } = useQuery({
    queryKey: ['defeat-summary'],
    queryFn: () => executionsApi.defeatSummary(),
    staleTime: 5 * 60 * 1000,
  })

  const items = data?.items ?? []
  const activeCount = items.filter((e) => !['낙찰', '패찰', '포기'].includes(e.status)).length

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-6 w-6 text-blue-600" />
          <div>
            <h1 className="text-xl font-bold">투찰 실행 관리</h1>
            <p className="text-sm text-muted-foreground">진행중 {activeCount}건 · 전체 {data?.total ?? 0}건</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          {/* 뷰 토글 */}
          <div className="flex rounded-md border overflow-hidden">
            <button
              onClick={() => setViewMode('list')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors',
                viewMode === 'list'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              )}
            >
              <LayoutList className="h-3.5 w-3.5" />
              목록
            </button>
            <button
              onClick={() => setViewMode('kanban')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors border-l',
                viewMode === 'kanban'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              칸반
            </button>
          </div>

          <UploadButton label="SUCVIEW" onFile={(f) => sucviewMut.mutate(f)} loading={sucviewMut.isPending} />
          <UploadButton label="인포이력" onFile={(f) => inpoMut.mutate(f)} loading={inpoMut.isPending} />
          <Button size="sm" onClick={() => setShowNew(true)}>
            <Plus className="h-4 w-4 mr-1" />
            신규 등록
          </Button>
        </div>
      </div>

      {/* 업로드 결과 메시지 */}
      {importMsg && (
        <div className="flex items-center gap-2 p-3 rounded-md bg-blue-50 border border-blue-200 text-sm text-blue-700">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span className="flex-1">{importMsg}</span>
          <button onClick={() => setImportMsg(null)}><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* 요약 */}
      <SummaryBar />

      {/* 개찰 임박 공고 */}
      <UpcomingOpeningsPanel />

      {/* 패찰 분석 리포트 (P4-1) */}
      {defeatData && defeatData.total_defeats > 0 && (
        <Card className="border-red-100 bg-red-50/40">
          <CardHeader className="pb-2 pt-3 px-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-red-700 flex items-center gap-2">
                <XCircle className="h-4 w-4" />
                패찰 원인 분석 ({defeatData.total_defeats}건)
                {defeatData.avg_winner_gap_pct !== null && (
                  <span className="text-xs font-normal text-red-500 ml-1">
                    평균 gap {defeatData.avg_winner_gap_pct > 0 ? '+' : ''}{defeatData.avg_winner_gap_pct.toFixed(2)}%p
                  </span>
                )}
              </CardTitle>
              <button
                onClick={() => setShowDefeat(!showDefeat)}
                className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1"
              >
                {showDefeat ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {showDefeat ? '접기' : '펼치기'}
              </button>
            </div>
            {/* 원인별 bar */}
            <div className="flex gap-2 mt-2 flex-wrap">
              {defeatData.by_cause.map((c: DefeatCauseStat) => (
                <span key={c.cause} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">
                  {c.cause} <span className="font-semibold">{c.count}건 ({c.pct}%)</span>
                </span>
              ))}
            </div>
          </CardHeader>

          {showDefeat && (
            <CardContent className="px-4 pb-3 pt-0 space-y-3">
              {/* 원인별 상세 */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {defeatData.by_cause.map((c: DefeatCauseStat) => (
                  <div key={c.cause} className="rounded-lg border border-red-200 bg-white p-3">
                    <div className="font-semibold text-red-700 text-sm">{c.cause}</div>
                    <div className="text-xs text-slate-500 mt-1">
                      {c.count}건 · {c.pct}%
                      {c.avg_gap_pct !== null && ` · 평균 gap ${c.avg_gap_pct > 0 ? '+' : ''}${c.avg_gap_pct.toFixed(2)}%p`}
                    </div>
                    {c.avg_rate_adj !== null && c.avg_rate_adj !== 0 && (
                      <div className={cn('text-xs mt-1 font-medium', c.avg_rate_adj < 0 ? 'text-blue-600' : 'text-slate-500')}>
                        권장 조정: {c.avg_rate_adj > 0 ? '+' : ''}{(c.avg_rate_adj * 100).toFixed(4)}%p
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* 최근 패찰 이력 */}
              <div>
                <div className="text-xs font-semibold text-slate-600 mb-2">최근 패찰 이력</div>
                <div className="space-y-1">
                  {defeatData.recent.map((r: DefeatSummaryRecentItem) => (
                    <div key={r.id} className="flex items-center justify-between text-xs bg-white rounded border border-slate-100 px-3 py-2">
                      <div className="truncate max-w-[50%] text-slate-700">{r.title}</div>
                      <div className="flex items-center gap-3 shrink-0 text-slate-500">
                        {r.bid_open_date && <span>{new Date(r.bid_open_date).toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' })}</span>}
                        {r.submitted_rate !== null && <span>투찰 {(r.submitted_rate * 100).toFixed(4)}%</span>}
                        {r.winner_rate !== null && <span>낙찰 {(r.winner_rate * 100).toFixed(4)}%</span>}
                        {r.gap_pct !== null && (
                          <span className={cn('font-semibold', r.gap_pct > 0 ? 'text-red-500' : 'text-blue-500')}>
                            {r.gap_pct > 0 ? '+' : ''}{r.gap_pct.toFixed(2)}%p
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* 목록 뷰 전용 필터 */}
      {viewMode === 'list' && (
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <div className="flex gap-1 flex-wrap">
            <Button
              size="sm"
              variant={statusFilter === 'all' ? 'default' : 'outline'}
              className="h-7 text-xs"
              onClick={() => setStatusFilter('all')}
            >
              전체
            </Button>
            {STATUS_ORDER.map((s) => (
              <Button
                key={s}
                size="sm"
                variant={statusFilter === s ? 'default' : 'outline'}
                className="h-7 text-xs"
                onClick={() => setStatusFilter(s)}
              >
                {s}
              </Button>
            ))}
          </div>
        </div>
      )}

      {/* 본문 */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : viewMode === 'kanban' ? (
        <KanbanBoard
          items={items}
          onStatusChange={(id, status) => updateMut.mutate({ id, status })}
        />
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <ClipboardList className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <div className="text-sm">등록된 투찰이 없습니다.</div>
          <div className="text-xs mt-1">SUCVIEW 파일을 업로드하거나 신규 등록하세요.</div>
        </div>
      ) : (
        <div>
          {items.map((exec) => (
            <ExecutionRow
              key={exec.id}
              exec={exec}
              onStatusChange={(id, status) => updateMut.mutate({ id, status })}
            />
          ))}
        </div>
      )}

      {showNew && <NewExecutionForm onClose={() => setShowNew(false)} />}
    </div>
  )
}
