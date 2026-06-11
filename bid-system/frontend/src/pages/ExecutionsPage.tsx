import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardList, Plus, Upload, CheckCircle2, XCircle, Clock, Trophy,
  AlertTriangle, SkipForward, Loader2, ChevronDown, ChevronUp, RefreshCw,
  Search, Filter, X, FileText, LayoutList, LayoutGrid,
} from 'lucide-react'
import { executionsApi } from '../api'
import type { BidExecution, ExecutionStatus } from '../types'
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
          <div className="text-green-600 font-medium">낙찰율 {fmtRate(exec.winner_rate)}</div>
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
                  <div className="text-sm text-muted-foreground">낙찰율</div>
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
                    다음 조정: {analysis.next_rate_adj > 0 ? '+' : ''}{(analysis.next_rate_adj * 100).toFixed(2)}%p
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
