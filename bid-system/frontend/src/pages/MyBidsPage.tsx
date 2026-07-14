import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, CheckCircle2, XCircle, Clock, Trash2, Edit2, Search, Download, Upload, Loader2, AlertCircle, FileText, TrendingUp, Target, BarChart2, Info } from 'lucide-react'
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, BarChart, Bar, ReferenceLine, Cell, PieChart, Pie, Legend
} from 'recharts'
import { myBidsApi, bidsApi } from '@/api'
import type { MyBidRecord, MyBidAnalysis, DefeatAnalysis, GapAnalysisResponse, BidSearchItem, WinPattern, SekihaiInfo } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

type ResultType = 'pending' | 'won' | 'lost'

function ResultBadge({ result }: { result: ResultType }) {
  if (result === 'won')
    return (
      <Badge className="bg-emerald-50 text-emerald-700 border border-emerald-200 gap-1 font-medium">
        <CheckCircle2 className="h-3 w-3" />낙찰
      </Badge>
    )
  if (result === 'lost')
    return (
      <Badge className="bg-red-50 text-red-600 border border-red-200 gap-1 font-medium">
        <XCircle className="h-3 w-3" />미낙찰
      </Badge>
    )
  return (
    <Badge className="bg-slate-50 text-slate-500 border border-slate-200 gap-1 font-medium">
      <Clock className="h-3 w-3" />결과대기
    </Badge>
  )
}

function StatCard({
  label, value, sub, icon: Icon, accent = 'blue',
}: {
  label: string; value: string | number; sub?: string
  icon?: React.ElementType; accent?: 'blue' | 'emerald' | 'amber' | 'red' | 'slate'
}) {
  const accents = {
    blue:    { bar: 'bg-blue-500',    iconBg: 'bg-blue-50',    iconColor: 'text-blue-600' },
    emerald: { bar: 'bg-emerald-500', iconBg: 'bg-emerald-50', iconColor: 'text-emerald-600' },
    amber:   { bar: 'bg-amber-500',   iconBg: 'bg-amber-50',   iconColor: 'text-amber-600' },
    red:     { bar: 'bg-red-500',     iconBg: 'bg-red-50',     iconColor: 'text-red-600' },
    slate:   { bar: 'bg-slate-400',   iconBg: 'bg-slate-50',   iconColor: 'text-slate-500' },
  }
  const a = accents[accent]
  return (
    <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
      <div className={cn('absolute top-0 left-0 right-0 h-0.5', a.bar)} />
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{value}</p>
            {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
          </div>
          {Icon && (
            <div className={cn('rounded-xl p-2.5', a.iconBg)}>
              <Icon className={cn('h-5 w-5', a.iconColor)} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

const emptyForm = {
  announcement_no: '',
  bid_id: null as number | null,
  title: '',
  agency_name: '',
  bid_date: '',
  base_amount: '',
  submitted_rate: '',
  recommendation_rate: '',
  actual_winner_rate: '',
  result: 'pending',
  note: '',
}

function ExcelDownloadButton() {
  const [loading, setLoading] = useState(false)

  const handleDownload = async () => {
    setLoading(true)
    try {
      const blob = await myBidsApi.exportExcel()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = '투찰이력.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Button variant="outline" onClick={handleDownload} disabled={loading} className="gap-2 border-slate-200 text-slate-600 hover:bg-slate-50">
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
      내보내기
    </Button>
  )
}

interface ImportResult { imported: number; skipped: number; errors: string[]; details: string[] }

function ExcelUploadModal({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => { setFile(null); setResult(null); setError(null) }
  const handleClose = (o: boolean) => { if (!o) { reset() } setOpen(o) }

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.xlsx')) { setError('xlsx 파일만 업로드 가능합니다.'); return }
    setFile(f); setError(null); setResult(null)
  }

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const res = await myBidsApi.importExcel(file)
      setResult(res)
      if (res.imported > 0) onDone()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '업로드 중 오류가 발생했습니다.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const COLS = ['공고번호', '공고제목*', '발주기관', '입찰일', '기초금액', '제출투찰률*', '추천투찰률', '결과', '실제낙찰률', '비고']

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} className="gap-2 border-slate-200 text-slate-600 hover:bg-slate-50">
        <Upload className="h-4 w-4" />업로드
      </Button>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-lg bg-white">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-semibold text-slate-800">
              <Upload className="h-4 w-4 text-blue-600" />투찰 이력 엑셀 업로드
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-1">
            {/* 컬럼 안내 */}
            {!result && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
                <p className="text-xs font-semibold text-blue-700 flex items-center gap-1.5">
                  <Info className="h-3.5 w-3.5" />엑셀 파일 형식 (* 필수)
                </p>
                <div className="flex flex-wrap gap-1">
                  {COLS.map((c) => (
                    <span key={c} className={cn(
                      'text-xs px-2 py-0.5 rounded border font-mono',
                      c.endsWith('*') ? 'bg-blue-100 text-blue-700 border-blue-300 font-semibold' : 'bg-white text-slate-600 border-slate-200'
                    )}>{c.replace('*', '')}</span>
                  ))}
                </div>
                <ul className="text-xs text-blue-600 space-y-0.5 list-disc list-inside">
                  <li>투찰률: 소수(0.87123) 또는 퍼센트(87.123) 모두 허용</li>
                  <li>결과: 낙찰·수주 → 낙찰 / 유찰·패찰·미낙찰 → 미낙찰 / 기타 → 진행중</li>
                  <li>동일 공고번호가 이미 존재하면 중복 건너뜀</li>
                  <li>기존 내보내기 파일을 그대로 업로드 가능</li>
                </ul>
              </div>
            )}

            {/* 파일 선택 */}
            {!result && (
              <div
                onClick={() => inputRef.current?.click()}
                className={cn(
                  'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
                  file ? 'border-blue-400 bg-blue-50' : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
                )}
              >
                <input ref={inputRef} type="file" accept=".xlsx" className="hidden" onChange={handleFile} />
                {file ? (
                  <div className="space-y-1">
                    <FileText className="h-8 w-8 text-blue-500 mx-auto" />
                    <p className="text-sm font-semibold text-blue-700">{file.name}</p>
                    <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <Upload className="h-8 w-8 text-slate-300 mx-auto" />
                    <p className="text-sm text-slate-500">클릭하여 xlsx 파일 선택</p>
                    <p className="text-xs text-slate-400">또는 파일을 여기에 드래그</p>
                  </div>
                )}
              </div>
            )}

            {/* 오류 */}
            {error && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
                <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            {/* 결과 */}
            {result && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: '등록 완료', value: result.imported, color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
                    { label: '건너뜀', value: result.skipped, color: 'text-slate-500', bg: 'bg-slate-50 border-slate-200' },
                  ].map(({ label, value, color, bg }) => (
                    <div key={label} className={cn('border rounded-lg p-3 text-center', bg)}>
                      <p className={cn('text-2xl font-bold tabular-nums', color)}>{value}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>

                {result.errors.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-1 max-h-32 overflow-y-auto">
                    <p className="text-xs font-semibold text-red-600">처리 오류 ({result.errors.length}건)</p>
                    {result.errors.map((e, i) => <p key={i} className="text-xs text-red-600">{e}</p>)}
                  </div>
                )}

                {result.details.length > 0 && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 max-h-40 overflow-y-auto">
                    <p className="text-xs font-semibold text-slate-500 mb-1">처리 내역 (최대 50건)</p>
                    {result.details.map((d, i) => <p key={i} className="text-xs text-slate-600">{d}</p>)}
                  </div>
                )}
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            {result ? (
              <Button onClick={() => handleClose(false)} className="bg-blue-600 hover:bg-blue-700">닫기</Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => handleClose(false)} className="border-slate-200">취소</Button>
                <Button onClick={handleUpload} disabled={!file || loading} className="gap-2 bg-blue-600 hover:bg-blue-700">
                  {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {loading ? '업로드 중...' : '업로드'}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default function MyBidsPage() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState('history')
  const [resultFilter, setResultFilter] = useState('all')
  const [showAdd, setShowAdd] = useState(false)
  const [editRecord, setEditRecord] = useState<MyBidRecord | null>(null)
  const [form, setForm] = useState({ ...emptyForm })
  const [updateForm, setUpdateForm] = useState({ result: 'pending', actual_winner_rate: '', note: '' })
  const [annoInput, setAnnoInput] = useState('')
  const [debouncedAnno, setDebouncedAnno] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const annoRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedAnno(annoInput), 300)
    return () => clearTimeout(t)
  }, [annoInput])

  const { data: bidSuggestions = [] } = useQuery<BidSearchItem[]>({
    queryKey: ['bid-search', debouncedAnno],
    queryFn: () => bidsApi.search(debouncedAnno),
    enabled: debouncedAnno.length >= 2,
  })

  const { data: stats } = useQuery({
    queryKey: ['my-bids-stats'],
    queryFn: myBidsApi.stats,
  })

  const { data: analysis } = useQuery<MyBidAnalysis>({
    queryKey: ['my-bids-analysis'],
    queryFn: myBidsApi.analysis,
    enabled: activeTab === 'analysis',
  })

  const { data: defeat } = useQuery<DefeatAnalysis>({
    queryKey: ['my-bids-defeat'],
    queryFn: myBidsApi.defeatAnalysis,
    enabled: activeTab === 'defeat',
  })

  const { data: gapData } = useQuery<GapAnalysisResponse>({
    queryKey: ['my-bids-gap'],
    queryFn: myBidsApi.gapAnalysis,
    enabled: activeTab === 'gap',
  })

  const { data: winPattern } = useQuery<WinPattern>({
    queryKey: ['my-bids-win-pattern'],
    queryFn: myBidsApi.winPattern,
    enabled: activeTab === 'performance',
  })

  const { data: records = [], isLoading } = useQuery<MyBidRecord[]>({
    queryKey: ['my-bids', resultFilter],
    queryFn: () => myBidsApi.list({ result: resultFilter === 'all' ? undefined : resultFilter }),
  })

  const annoNos = useMemo(
    () => records.filter((r) => r.announcement_no && r.result === 'lost').map((r) => r.announcement_no!).slice(0, 30),
    [records],
  )

  const { data: sekihaiMap = {} } = useQuery<Record<string, SekihaiInfo>>({
    queryKey: ['inpo-rank-batch', annoNos],
    queryFn: () => myBidsApi.inpoRankBatch(annoNos),
    enabled: annoNos.length > 0,
    staleTime: 600_000,
  })

  const createMut = useMutation({
    mutationFn: myBidsApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-bids'] })
      qc.invalidateQueries({ queryKey: ['my-bids-stats'] })
      setShowAdd(false)
      setForm({ ...emptyForm })
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof myBidsApi.update>[1] }) =>
      myBidsApi.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-bids'] })
      qc.invalidateQueries({ queryKey: ['my-bids-stats'] })
      setEditRecord(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: myBidsApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-bids'] })
      qc.invalidateQueries({ queryKey: ['my-bids-stats'] })
    },
  })

  function handleCreate() {
    if (!form.title || !form.submitted_rate) return
    createMut.mutate({
      title: form.title,
      agency_name: form.agency_name || undefined,
      bid_date: form.bid_date || undefined,
      base_amount: form.base_amount ? parseInt(form.base_amount) : undefined,
      submitted_rate: parseFloat(form.submitted_rate) / 100,
      recommendation_rate: form.recommendation_rate ? parseFloat(form.recommendation_rate) / 100 : undefined,
      note: form.note || undefined,
      bid_id: form.bid_id ?? undefined,
      announcement_no: form.announcement_no || undefined,
      actual_winner_rate: form.actual_winner_rate ? parseFloat(form.actual_winner_rate) / 100 : undefined,
      result: form.result || 'pending',
    })
  }

  function handleSelectBid(item: BidSearchItem) {
    setForm((f) => ({
      ...f,
      announcement_no: item.announcement_no,
      bid_id: item.id,
      title: item.title,
      agency_name: item.agency_name ?? '',
      base_amount: String(item.base_amount),
    }))
    setAnnoInput(item.announcement_no)
    setShowSuggestions(false)
  }

  const rateDiffDisplay = (() => {
    if (!form.submitted_rate || !form.actual_winner_rate) return null
    const diff = parseFloat(form.submitted_rate) - parseFloat(form.actual_winner_rate)
    return isNaN(diff) ? null : diff
  })()

  function handleUpdate() {
    if (!editRecord) return
    updateMut.mutate({
      id: editRecord.id,
      body: {
        result: updateForm.result as ResultType,
        actual_winner_rate: updateForm.actual_winner_rate
          ? parseFloat(updateForm.actual_winner_rate) / 100 : undefined,
        note: updateForm.note || undefined,
      },
    })
  }

  function openEdit(rec: MyBidRecord) {
    setEditRecord(rec)
    setUpdateForm({
      result: rec.result,
      actual_winner_rate: rec.actual_winner_rate ? (rec.actual_winner_rate * 100).toFixed(4) : '',
      note: rec.note || '',
    })
  }

  const pct = (v?: number | null) => v != null ? `${(v * 100).toFixed(4)}%` : '-'

  const scatterData = (analysis?.rate_scatter ?? []).map((p) => ({
    x: p.recommendation_rate != null ? +(p.recommendation_rate * 100).toFixed(4) : null,
    y: +(p.submitted_rate * 100).toFixed(4),
    result: p.result,
  })).filter((p) => p.x != null)

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sticky Page Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-600" />투찰 이력
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">자사 투찰 기록 및 낙찰률 추적</p>
          </div>
          <div className="flex items-center gap-2">
            <ExcelDownloadButton />
            <ExcelUploadModal onDone={() => {
              qc.invalidateQueries({ queryKey: ['my-bids'] })
              qc.invalidateQueries({ queryKey: ['my-bids-stats'] })
            }} />
            <Button onClick={() => setShowAdd(true)} className="gap-2 bg-blue-600 hover:bg-blue-700">
              <Plus className="h-4 w-4" />이력 추가
            </Button>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-5">
        {/* KPI 통계 카드 */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="총 참여" value={stats.total} icon={FileText} accent="slate" />
            <StatCard
              label="낙찰"
              value={stats.won}
              sub={`낙찰률 ${(stats.win_rate * 100).toFixed(1)}%`}
              icon={CheckCircle2}
              accent="emerald"
            />
            <StatCard label="미낙찰" value={stats.lost} icon={XCircle} accent="red" />
            <StatCard label="결과대기" value={stats.pending} icon={Clock} accent="amber" />
            <StatCard
              label="평균 투찰률"
              value={stats.avg_submitted_rate != null ? `${(stats.avg_submitted_rate * 100).toFixed(4)}%` : '-'}
              icon={TrendingUp}
              accent="blue"
            />
            <StatCard
              label="AI 추천 대비 오차"
              value={stats.avg_rate_diff_from_rec != null
                ? `±${(stats.avg_rate_diff_from_rec * 100).toFixed(4)}%` : '-'}
              sub="AI 추천과의 평균 차이"
              icon={Target}
              accent="blue"
            />
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-100 border border-slate-200 p-1">
            <TabsTrigger value="history" className="data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">이력 목록</TabsTrigger>
            <TabsTrigger value="analysis" className="data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">정확도 분석</TabsTrigger>
            <TabsTrigger value="gap" className="data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">역산 분석</TabsTrigger>
            <TabsTrigger value="performance" className="data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">성과 분석</TabsTrigger>
          </TabsList>

          {/* 이력 목록 탭 */}
          <TabsContent value="history" className="space-y-3 mt-4">
            <div className="flex gap-2 items-center">
              <Select value={resultFilter} onValueChange={setResultFilter}>
                <SelectTrigger className="w-36 border-slate-200 bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">전체</SelectItem>
                  <SelectItem value="won">낙찰</SelectItem>
                  <SelectItem value="lost">미낙찰</SelectItem>
                  <SelectItem value="pending">결과대기</SelectItem>
                </SelectContent>
              </Select>
              <span className="text-sm text-slate-500 font-medium">{records.length}건</span>
            </div>
            <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 border-b border-slate-200">
                    <TableHead className="text-slate-600 font-semibold">공고명</TableHead>
                    <TableHead className="text-slate-600 font-semibold">발주기관</TableHead>
                    <TableHead className="text-slate-600 font-semibold">투찰일</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold">기초금액</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold">투찰률</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold">AI 추천률</TableHead>
                    <TableHead className="text-right text-slate-600 font-semibold">낙찰률</TableHead>
                    <TableHead className="text-center text-slate-600 font-semibold">결과</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-12 text-slate-500">
                        <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2" />
                        불러오는 중...
                      </TableCell>
                    </TableRow>
                  ) : records.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-16">
                        <FileText className="h-10 w-10 text-slate-200 mx-auto mb-3" />
                        <p className="text-slate-500 text-sm">투찰 이력이 없습니다.</p>
                        <p className="text-slate-300 text-xs mt-1">이력 추가 버튼으로 등록하세요.</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    records.map((rec) => (
                      <TableRow key={rec.id} className="hover:bg-slate-50/50 transition-colors border-b border-slate-100">
                        <TableCell className="max-w-xs truncate font-medium text-slate-800">{rec.title}</TableCell>
                        <TableCell className="whitespace-nowrap text-slate-500 text-sm">{rec.agency_name || '-'}</TableCell>
                        <TableCell className="whitespace-nowrap text-slate-500 text-sm">
                          {rec.bid_date ? new Date(rec.bid_date).toLocaleDateString('ko-KR') : '-'}
                        </TableCell>
                        <TableCell className="text-right whitespace-nowrap text-slate-700 font-medium">
                          {rec.base_amount ? `${(rec.base_amount / 1e8).toFixed(1)}억` : '-'}
                        </TableCell>
                        <TableCell className="text-right font-mono font-semibold text-slate-800">{pct(rec.submitted_rate)}</TableCell>
                        <TableCell className={cn(
                          "text-right font-mono text-sm",
                          rec.recommendation_rate != null ? "text-blue-600 font-medium" : "text-slate-500"
                        )}>
                          {pct(rec.recommendation_rate)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-sm text-slate-500">
                          {pct(rec.actual_winner_rate)}
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex flex-col items-center gap-0.5">
                            <ResultBadge result={rec.result as ResultType} />
                            {rec.result === 'lost' && rec.announcement_no && sekihaiMap[rec.announcement_no]?.found && (() => {
                              const info = sekihaiMap[rec.announcement_no!]!
                              const myRate = rec.submitted_rate
                              const winnerRate = info.winner_rate
                              if (!winnerRate) return null
                              const diff = Math.abs(myRate - winnerRate) * 100
                              const isSekihai = diff < 1.0
                              return isSekihai ? (
                                <Badge className="text-[9px] px-1 py-0 bg-amber-50 text-amber-600 border border-amber-200 gap-0.5">
                                  <AlertCircle className="h-2.5 w-2.5" />아깝게 패찰 {diff.toFixed(2)}%p
                                </Badge>
                              ) : null
                            })()}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1 justify-end">
                            <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-blue-600 hover:bg-blue-50" onClick={() => openEdit(rec)}>
                              <Edit2 className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-red-600 hover:bg-red-50"
                              onClick={() => { if (confirm('삭제하시겠습니까?')) deleteMut.mutate(rec.id) }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Card>
          </TabsContent>

          {/* 정확도 분석 탭 */}
          <TabsContent value="analysis" className="space-y-4 mt-4">
            {analysis && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard label="±1% 적중률" value={analysis.accuracy_stats.accuracy_1pct != null ? `${(analysis.accuracy_stats.accuracy_1pct * 100).toFixed(1)}%` : '-'} icon={Target} accent="emerald" />
                  <StatCard label="±3% 적중률" value={analysis.accuracy_stats.accuracy_3pct != null ? `${(analysis.accuracy_stats.accuracy_3pct * 100).toFixed(1)}%` : '-'} icon={Target} accent="blue" />
                  <StatCard label="평균 오차" value={analysis.accuracy_stats.avg_error != null ? `±${(analysis.accuracy_stats.avg_error * 100).toFixed(4)}%` : '-'} icon={BarChart2} accent="amber" />
                  <StatCard label="분석 대상" value={`${analysis.accuracy_stats.total_records}건`} icon={FileText} accent="slate" />
                </div>

                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardHeader className="border-b border-slate-100 pb-4">
                    <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                      <BarChart2 className="h-4 w-4 text-blue-600" />AI 추천률 vs 실제 투찰률
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-5">
                    {scatterData.length === 0 ? (
                      <p className="text-sm text-slate-500 text-center py-10">AI 추천률이 있는 이력 데이터가 없습니다.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={280}>
                        <ScatterChart margin={{ left: -10, right: 10 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                          <XAxis dataKey="x" name="AI 추천률" unit="%" type="number" domain={['auto', 'auto']} tick={{ fontSize: 12, fill: '#475569' }} />
                          <YAxis dataKey="y" name="투찰률" unit="%" type="number" domain={['auto', 'auto']} tick={{ fontSize: 12, fill: '#475569' }} />
                          <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(v: number) => v + '%'} />
                          <Scatter data={scatterData.filter((p) => p.result === 'won')} fill="#10b981" name="낙찰" opacity={0.8} />
                          <Scatter data={scatterData.filter((p) => p.result === 'lost')} fill="#94a3b8" name="미낙찰" opacity={0.5} />
                        </ScatterChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>

                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardHeader className="border-b border-slate-100 pb-4">
                    <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-blue-600" />월별 AI 추천 오차 (MAE)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-5">
                    {analysis.monthly_accuracy.length === 0 ? (
                      <p className="text-sm text-slate-500 text-center py-10">월별 데이터가 없습니다.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={analysis.monthly_accuracy} margin={{ left: -10, right: 10 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                          <XAxis dataKey="year_month" tick={{ fontSize: 12, fill: '#475569' }} />
                          <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" />
                          <Tooltip formatter={(v: number) => [v + '%', 'MAE']} />
                          <Line type="monotone" dataKey="mae" stroke="#3b82f6" dot={{ r: 3, fill: '#3b82f6' }} strokeWidth={2} connectNulls />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>

                {analysis.monthly_accuracy.length >= 2 && (() => {
                  const sorted = [...analysis.monthly_accuracy].sort((a, b) => a.year_month.localeCompare(b.year_month))
                  const latest = sorted[sorted.length - 1]
                  const prev   = sorted[sorted.length - 2]
                  const trend  = latest?.mae != null && prev?.mae != null ? latest.mae - prev.mae : null
                  const hitRate1 = analysis.accuracy_stats.accuracy_1pct
                  const hitRate3 = analysis.accuracy_stats.accuracy_3pct
                  const avgErr   = analysis.accuracy_stats.avg_error
                  const msgs: { type: 'good' | 'warn' | 'info'; text: string }[] = []
                  if (trend !== null) msgs.push({ type: trend < 0 ? 'good' : 'warn', text: `전월 대비 오차 ${trend < 0 ? '개선 ▼' : '증가 ▲'} ${Math.abs(trend * 100).toFixed(4)}%` })
                  if (hitRate1 != null) msgs.push({ type: hitRate1 >= 0.3 ? 'good' : 'warn', text: `±1% 적중률 ${(hitRate1*100).toFixed(1)}% — ${hitRate1 >= 0.3 ? '양호' : '개선 필요'}` })
                  if (hitRate3 != null) msgs.push({ type: hitRate3 >= 0.6 ? 'good' : 'warn', text: `±3% 적중률 ${(hitRate3*100).toFixed(1)}% — ${hitRate3 >= 0.6 ? '목표 달성' : '목표 60% 미달'}` })
                  if (avgErr != null) msgs.push({ type: 'info', text: `전체 평균 오차 ±${(avgErr*100).toFixed(4)}% (소수점 4자리 기준)` })
                  return (
                    <Card className="bg-white border-blue-100 shadow-sm">
                      <CardHeader className="border-b border-blue-50 pb-4">
                        <CardTitle className="text-base font-semibold text-blue-700 flex items-center gap-2">
                          <Target className="h-4 w-4 text-blue-600" />종합 진단 리포트
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="p-5 space-y-2">
                        {msgs.map((m, i) => (
                          <div key={i} className={cn('flex items-start gap-2 text-sm p-3 rounded-lg border',
                            m.type === 'good'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                              : m.type === 'warn'
                              ? 'bg-amber-50 text-amber-700 border-amber-100'
                              : 'bg-slate-50 text-slate-600 border-slate-100')}>
                            <span className="shrink-0 font-bold">{m.type === 'good' ? '✓' : m.type === 'warn' ? '!' : 'ℹ'}</span>
                            {m.text}
                          </div>
                        ))}
                        <p className="text-xs text-slate-500 pt-1">기준: 최근 {sorted.length}개월 투찰 이력</p>
                      </CardContent>
                    </Card>
                  )
                })()}
              </>
            )}
            {!analysis && (
              <div className="text-center py-16">
                <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2 text-slate-300" />
                <p className="text-sm text-slate-500">분석 데이터를 불러오는 중...</p>
              </div>
            )}
          </TabsContent>

          {/* 역산 분석 탭 */}
          <TabsContent value="gap" className="space-y-4 mt-4">
            {gapData ? (
              gapData.total_analyzed === 0 ? (
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardContent className="py-16 text-center">
                    <BarChart2 className="h-10 w-10 text-slate-200 mx-auto mb-3" />
                    <p className="text-slate-500 text-sm">투찰 이력이 쌓이면 역산 분석이 가능합니다.</p>
                    <p className="text-slate-300 text-xs mt-1">낙찰 결과(실제 낙찰률)가 입력된 이력이 필요합니다.</p>
                  </CardContent>
                </Card>
              ) : (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                      <div className={cn('absolute top-0 left-0 right-0 h-0.5', gapData.mean_diff != null && gapData.mean_diff > 0 ? 'bg-amber-500' : 'bg-blue-500')} />
                      <CardContent className="p-5">
                        <p className="text-sm font-medium text-slate-500">평균 격차</p>
                        <p className={cn("text-2xl font-bold mt-1 tabular-nums", gapData.mean_diff != null && gapData.mean_diff > 0 ? "text-amber-600" : "text-blue-600")}>
                          {gapData.mean_diff != null ? `${gapData.mean_diff > 0 ? '+' : ''}${(gapData.mean_diff * 100).toFixed(4)}%` : '-'}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">
                          {gapData.consistent_direction === 'too_high' ? '▲ 낙찰자보다 높게 투찰' : gapData.consistent_direction === 'too_low' ? '▼ 낙찰자보다 낮게 투찰' : '— 혼합 패턴'}
                        </p>
                      </CardContent>
                    </Card>
                    {gapData.win_if_lower_by != null ? (
                      <Card className="relative overflow-hidden bg-white border-amber-100 shadow-sm">
                        <div className="absolute top-0 left-0 right-0 h-0.5 bg-amber-500" />
                        <CardContent className="p-5">
                          <p className="text-sm font-medium text-slate-500">낙찰 가능 구간</p>
                          <p className="text-2xl font-bold mt-1 tabular-nums text-amber-600">
                            -{(gapData.win_if_lower_by * 100).toFixed(4)}%
                          </p>
                          <p className="text-xs text-slate-500 mt-1">낮게 투찰하면 낙찰 구간 진입</p>
                        </CardContent>
                      </Card>
                    ) : (
                      <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                        <div className="absolute top-0 left-0 right-0 h-0.5 bg-slate-300" />
                        <CardContent className="p-5">
                          <p className="text-sm font-medium text-slate-500">낙찰 가능 구간</p>
                          <p className="text-2xl font-bold mt-1 tabular-nums text-slate-500">-</p>
                          <p className="text-xs text-slate-500 mt-1">{gapData.consistent_direction === 'too_low' ? '낙찰자보다 낮게 투찰 중' : '패턴 미확정'}</p>
                        </CardContent>
                      </Card>
                    )}
                    <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                      <div className="absolute top-0 left-0 right-0 h-0.5 bg-slate-400" />
                      <CardContent className="p-5">
                        <p className="text-sm font-medium text-slate-500">분석 건수</p>
                        <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{gapData.total_analyzed}건</p>
                        <p className="text-xs text-slate-500 mt-1">중앙값 {gapData.median_diff != null ? `${gapData.median_diff > 0 ? '+' : ''}${(gapData.median_diff * 100).toFixed(4)}%` : '-'}</p>
                      </CardContent>
                    </Card>
                  </div>

                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                        <BarChart2 className="h-4 w-4 text-blue-600" />낙찰자 대비 투찰 격차 분포
                        <span className="text-xs font-normal text-slate-500 ml-1">(양수: 내가 높게 / 음수: 내가 낮게)</span>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-5">
                      {gapData.buckets.length === 0 ? (
                        <p className="text-sm text-slate-500 text-center py-10">분포 데이터 없음</p>
                      ) : (
                        <ResponsiveContainer width="100%" height={240}>
                          <BarChart data={gapData.buckets.map((b) => ({ mid: +((b.range_lo + b.range_hi) / 2 * 100).toFixed(4), count: b.count, positive: b.range_lo >= 0 }))} margin={{ left: -10, right: 10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey="mid" unit="%" tick={{ fontSize: 12, fill: '#475569' }} />
                            <YAxis tick={{ fontSize: 12, fill: '#475569' }} allowDecimals={false} />
                            <Tooltip formatter={(v: number) => [v + '건', '빈도']} labelFormatter={(l) => `격차 ${l}%`} />
                            <ReferenceLine x={0} stroke="#475569" strokeDasharray="4 4" strokeWidth={1.5} />
                            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                              {gapData.buckets.map((b, i) => (
                                <Cell key={i} fill={b.range_lo >= 0 ? '#f59e0b' : '#3b82f6'} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      )}
                    </CardContent>
                  </Card>

                  {gapData.personal_bias.sample_count > 0 && (
                    <Card className="bg-white border-blue-100 shadow-sm">
                      <CardHeader className="border-b border-blue-50 pb-4">
                        <CardTitle className="text-base font-semibold text-blue-700 flex items-center gap-2">
                          <Target className="h-4 w-4 text-blue-600" />개인화 편향 분석
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="p-5 space-y-3">
                        <p className="text-sm text-slate-700">{gapData.personal_bias.narrative}</p>
                        <div className="flex gap-4 text-xs text-slate-500 bg-slate-50 rounded-lg p-3">
                          <span>신뢰도: <span className="font-medium text-slate-700">{(gapData.personal_bias.confidence * 100).toFixed(0)}%</span></span>
                          <span>샘플: <span className="font-medium text-slate-700">{gapData.personal_bias.sample_count}건</span></span>
                          <span>편향: <span className="font-medium text-slate-700">{gapData.personal_bias.avg_bias_pct > 0 ? '+' : ''}{gapData.personal_bias.avg_bias_pct.toFixed(4)}%</span></span>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </>
              )
            ) : (
              <div className="text-center py-16">
                <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2 text-slate-300" />
                <p className="text-sm text-slate-500">분석 데이터를 불러오는 중...</p>
              </div>
            )}
          </TabsContent>

          {/* 성과 분석 탭 */}
          <TabsContent value="performance" className="space-y-4 mt-4">
            {!winPattern ? (
              <div className="text-center py-16">
                <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2 text-slate-300" />
                <p className="text-sm text-slate-500">분석 데이터를 불러오는 중...</p>
              </div>
            ) : (
              <>
                <Card className={cn(
                  'border shadow-sm overflow-hidden',
                  winPattern.bias.direction === 'above' ? 'border-amber-200' : winPattern.bias.direction === 'below' ? 'border-blue-200' : 'border-slate-200'
                )}>
                  <div className={cn('h-1', winPattern.bias.direction === 'above' ? 'bg-amber-500' : winPattern.bias.direction === 'below' ? 'bg-blue-500' : 'bg-slate-300')} />
                  <CardContent className="p-6">
                    <div className="flex items-start gap-5">
                      <div className={cn(
                        'flex-none w-14 h-14 rounded-2xl flex items-center justify-center text-2xl',
                        winPattern.bias.direction === 'above' ? 'bg-amber-50' : winPattern.bias.direction === 'below' ? 'bg-blue-50' : 'bg-slate-50'
                      )}>
                        {winPattern.bias.direction === 'above' ? '▲' : winPattern.bias.direction === 'below' ? '▼' : '—'}
                      </div>
                      <div className="flex-1">
                        <p className="text-xs text-slate-500 mb-1 font-medium">투찰 편향 진단</p>
                        <p className="text-xl font-bold text-slate-900 mb-2">{winPattern.bias.signal}</p>
                        <div className="flex flex-wrap gap-4 text-sm text-slate-500">
                          <span>평균 rate_diff: <span className="font-mono font-semibold text-slate-700">
                            {winPattern.bias.rate_diff_mean != null ? `${winPattern.bias.rate_diff_mean > 0 ? '+' : ''}${(winPattern.bias.rate_diff_mean * 100).toFixed(4)}%p` : '-'}
                          </span></span>
                          <span>총 <span className="font-semibold text-slate-700">{winPattern.total}건</span> 중 낙찰 <span className="font-semibold text-emerald-600">{winPattern.won}건</span> ({winPattern.overall_win_rate.toFixed(2)}%)</span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {winPattern.lost > 0 && (() => {
                  const total = winPattern.loss_reasons.above_winner + winPattern.loss_reasons.below_floor + winPattern.loss_reasons.below_winner
                  const pieData = [
                    { name: '높게 투찰', value: winPattern.loss_reasons.above_winner, fill: '#f59e0b' },
                    { name: '낮게 투찰', value: winPattern.loss_reasons.below_winner, fill: '#3b82f6' },
                    { name: '하한 미달', value: winPattern.loss_reasons.below_floor, fill: '#ef4444' },
                  ].filter((d) => d.value > 0)
                  return (
                    <Card className="bg-white border-slate-200 shadow-sm">
                      <CardHeader className="border-b border-slate-100 pb-4">
                        <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                          <XCircle className="h-4 w-4 text-blue-600" />패배 원인 분석 ({total}건)
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="p-5">
                        <div className="flex flex-col md:flex-row items-center gap-8">
                          <ResponsiveContainer width={220} height={200}>
                            <PieChart>
                              <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value" paddingAngle={3}>
                                {pieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                              </Pie>
                              <Tooltip formatter={(v: number) => [`${v}건 (${total > 0 ? (v / total * 100).toFixed(1) : 0}%)`, '']} />
                            </PieChart>
                          </ResponsiveContainer>
                          <div className="space-y-3 flex-1">
                            {pieData.map((d) => (
                              <div key={d.name} className="flex items-center gap-3 text-sm">
                                <span className="w-3 h-3 rounded-full shrink-0" style={{ background: d.fill }} />
                                <span className="text-slate-600 w-20">{d.name}</span>
                                <span className="font-mono font-semibold text-slate-800">{d.value}건</span>
                                <span className="text-slate-500 text-xs">({total > 0 ? (d.value / total * 100).toFixed(1) : 0}%)</span>
                              </div>
                            ))}
                            <p className="text-xs text-slate-500 pt-2 leading-relaxed">
                              높게 투찰: submitted &gt; winner<br />
                              낮게 투찰: submitted &lt; winner (하한 이상)<br />
                              하한 미달: 최저 투찰률 미만 투찰
                            </p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })()}

                {winPattern.by_agency.filter((a) => a.total >= 10).length > 0 && (
                  <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-blue-600" />발주기관별 승률 (10건 이상 참여)
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-slate-50 border-b border-slate-200">
                            <TableHead className="text-slate-600 font-semibold">발주기관</TableHead>
                            <TableHead className="text-right text-slate-600 font-semibold">참여</TableHead>
                            <TableHead className="text-right text-slate-600 font-semibold">낙찰</TableHead>
                            <TableHead className="text-right text-slate-600 font-semibold">승률</TableHead>
                            <TableHead className="text-right text-slate-600 font-semibold">평균 격차</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {winPattern.by_agency.filter((a) => a.total >= 10).map((a) => (
                            <TableRow key={a.agency_name} className="hover:bg-slate-50/50 border-b border-slate-100">
                              <TableCell className="max-w-xs truncate font-medium text-slate-800">{a.agency_name}</TableCell>
                              <TableCell className="text-right text-slate-600">{a.total}</TableCell>
                              <TableCell className="text-right text-slate-600">{a.won}</TableCell>
                              <TableCell className={cn('text-right font-mono font-semibold', a.win_rate >= 10 ? 'text-emerald-600' : a.win_rate > 0 ? 'text-blue-600' : 'text-slate-500')}>
                                {a.win_rate.toFixed(1)}%
                              </TableCell>
                              <TableCell className={cn('text-right font-mono text-sm', a.avg_rate_diff == null ? 'text-slate-400' : a.avg_rate_diff > 0 ? 'text-amber-600' : 'text-blue-600')}>
                                {a.avg_rate_diff != null ? `${a.avg_rate_diff > 0 ? '+' : ''}${(a.avg_rate_diff * 100).toFixed(4)}%p` : '-'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                )}

                {winPattern.by_year.length > 0 && (
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-blue-600" />연도별 승률 추이
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-5">
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={winPattern.by_year} margin={{ left: -10, right: 10 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                          <XAxis dataKey="year" tick={{ fontSize: 12, fill: '#475569' }} />
                          <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit="%" domain={[0, 'auto']} />
                          <Tooltip formatter={(v: number, name: string) => [name === 'win_rate' ? `${v.toFixed(1)}%` : v + '건', name === 'win_rate' ? '승률' : name === 'won' ? '낙찰' : '참여']} />
                          <Legend formatter={(v) => v === 'win_rate' ? '승률 (%)' : v === 'won' ? '낙찰 건수' : '참여 건수'} />
                          <Line type="monotone" dataKey="win_rate" stroke="#10b981" dot={{ r: 4, fill: '#10b981' }} strokeWidth={2.5} name="win_rate" />
                          <Line type="monotone" dataKey="total" stroke="#94a3b8" dot={{ r: 3 }} strokeWidth={1.5} strokeDasharray="4 2" name="total" />
                        </LineChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}

                {winPattern.won === 0 && winPattern.lost === 0 && (
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardContent className="py-16 text-center">
                      <BarChart2 className="h-10 w-10 text-slate-200 mx-auto mb-3" />
                      <p className="text-slate-500 text-sm">결과가 확정된 투찰 이력이 없습니다.</p>
                      <p className="text-slate-300 text-xs mt-1">낙찰 결과(won/lost)가 입력된 이력이 필요합니다.</p>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* 투찰 등록 다이얼로그 */}
      <Dialog open={showAdd} onOpenChange={(o) => { setShowAdd(o); if (!o) { setForm({ ...emptyForm }); setAnnoInput(''); setShowSuggestions(false) } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-slate-900 font-semibold">투찰 등록</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div ref={annoRef} className="relative">
              <Label className="text-sm font-medium text-slate-600 mb-1.5 block">공고번호 (자동완성)</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500 pointer-events-none" />
                <Input
                  className="pl-9 border-slate-200"
                  value={annoInput}
                  onChange={(e) => { setAnnoInput(e.target.value); setForm((f) => ({ ...f, announcement_no: e.target.value, bid_id: null })); setShowSuggestions(true) }}
                  onFocus={() => setShowSuggestions(true)}
                  onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                  placeholder="공고번호 입력 (2자 이상)"
                />
              </div>
              {showSuggestions && bidSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg py-1 max-h-48 overflow-y-auto">
                  {bidSuggestions.map((item) => (
                    <button
                      key={item.id}
                      className="w-full text-left px-3 py-2.5 hover:bg-slate-50 transition-colors border-b border-slate-50 last:border-0"
                      onMouseDown={() => handleSelectBid(item)}
                    >
                      <div className="text-xs font-mono text-slate-500">{item.announcement_no}</div>
                      <div className="text-sm font-medium text-slate-800 truncate">{item.title}</div>
                      <div className="text-xs text-slate-500">{item.agency_name} · {item.base_amount ? `${(item.base_amount / 1e8).toFixed(1)}억` : '-'}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <Label className="text-sm font-medium text-slate-600 mb-1.5 block">공고명 *</Label>
              <Input className="border-slate-200" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="공고명 입력 (자동완성 또는 직접 입력)" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">발주기관</Label>
                <Input className="border-slate-200" value={form.agency_name} onChange={(e) => setForm((f) => ({ ...f, agency_name: e.target.value }))} placeholder="발주기관명" />
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">투찰일</Label>
                <Input type="date" className="border-slate-200" value={form.bid_date} onChange={(e) => setForm((f) => ({ ...f, bid_date: e.target.value }))} />
              </div>
            </div>

            <div>
              <Label className="text-sm font-medium text-slate-600 mb-1.5 block">기초금액 (원)</Label>
              <Input type="number" className="border-slate-200" value={form.base_amount} onChange={(e) => setForm((f) => ({ ...f, base_amount: e.target.value }))} placeholder="예: 500000000" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">투찰률 (%) *</Label>
                <Input type="number" step="0.0001" className="border-slate-200" value={form.submitted_rate} onChange={(e) => setForm((f) => ({ ...f, submitted_rate: e.target.value }))} placeholder="예: 87.9300" />
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">AI 추천률 (%)</Label>
                <Input type="number" step="0.0001" className="border-slate-200" value={form.recommendation_rate} onChange={(e) => setForm((f) => ({ ...f, recommendation_rate: e.target.value }))} placeholder="예: 87.9500" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">결과</Label>
                <Select value={form.result} onValueChange={(v) => setForm((f) => ({ ...f, result: v }))}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">결과대기</SelectItem>
                    <SelectItem value="won">낙찰</SelectItem>
                    <SelectItem value="lost">미낙찰</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">낙찰자 사정율 (%)</Label>
                <Input type="number" step="0.0001" className="border-slate-200" value={form.actual_winner_rate} onChange={(e) => setForm((f) => ({ ...f, actual_winner_rate: e.target.value }))} placeholder="예: 87.9100" disabled={form.result === 'pending'} />
              </div>
            </div>

            {rateDiffDisplay !== null && (
              <div className={cn(
                'text-xs px-3 py-2 rounded-lg border font-mono',
                rateDiffDisplay > 0 ? 'text-amber-700 bg-amber-50 border-amber-200' : rateDiffDisplay < 0 ? 'text-blue-700 bg-blue-50 border-blue-200' : 'text-emerald-700 bg-emerald-50 border-emerald-200'
              )}>
                rate_diff: {rateDiffDisplay > 0 ? '+' : ''}{rateDiffDisplay.toFixed(4)}%
                {rateDiffDisplay > 0 ? ' (낙찰자보다 높게 투찰)' : rateDiffDisplay < 0 ? ' (낙찰자보다 낮게 투찰)' : ' (동일)'}
              </div>
            )}

            <div>
              <Label className="text-sm font-medium text-slate-600 mb-1.5 block">메모</Label>
              <Input className="border-slate-200" value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} placeholder="메모 (선택)" />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" className="border-slate-200" onClick={() => { setShowAdd(false); setForm({ ...emptyForm }); setAnnoInput('') }}>취소</Button>
            <Button onClick={handleCreate} disabled={!form.title || !form.submitted_rate || createMut.isPending} className="bg-blue-600 hover:bg-blue-700">
              {createMut.isPending ? <><Loader2 className="h-4 w-4 animate-spin mr-1" />저장 중...</> : '저장'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 결과 수정 다이얼로그 */}
      <Dialog open={!!editRecord} onOpenChange={(o) => !o && setEditRecord(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-slate-900 font-semibold">결과 입력</DialogTitle>
          </DialogHeader>
          {editRecord && (
            <div className="space-y-4 py-2">
              <p className="text-sm font-medium text-slate-700 truncate bg-slate-50 rounded-lg p-3">{editRecord.title}</p>
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">결과</Label>
                <Select value={updateForm.result} onValueChange={(v) => setUpdateForm((f) => ({ ...f, result: v }))}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">결과대기</SelectItem>
                    <SelectItem value="won">낙찰</SelectItem>
                    <SelectItem value="lost">미낙찰</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">실제 낙찰률 (%)</Label>
                <Input type="number" step="0.0001" className="border-slate-200" value={updateForm.actual_winner_rate} onChange={(e) => setUpdateForm((f) => ({ ...f, actual_winner_rate: e.target.value }))} placeholder="예: 87.93" />
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-600 mb-1.5 block">메모</Label>
                <Input className="border-slate-200" value={updateForm.note} onChange={(e) => setUpdateForm((f) => ({ ...f, note: e.target.value }))} placeholder="메모 (선택)" />
              </div>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" className="border-slate-200" onClick={() => setEditRecord(null)}>취소</Button>
            <Button onClick={handleUpdate} disabled={updateMut.isPending} className="bg-blue-600 hover:bg-blue-700">
              {updateMut.isPending ? <><Loader2 className="h-4 w-4 animate-spin mr-1" />저장 중...</> : '저장'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
