import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, CheckCircle2, XCircle, Clock, Trash2, Edit2, Search, Download, Loader2, AlertCircle } from 'lucide-react'
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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
    return <Badge variant="default" className="bg-emerald-500 text-white gap-1"><CheckCircle2 className="h-3 w-3" />낙찰</Badge>
  if (result === 'lost')
    return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" />미낙찰</Badge>
  return <Badge variant="outline" className="gap-1 text-muted-foreground"><Clock className="h-3 w-3" />결과대기</Badge>
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <p className="text-xs text-muted-foreground mb-1">{label}</p>
        <p className="text-2xl font-bold font-mono">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
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
    <Button variant="outline" onClick={handleDownload} disabled={loading} className="gap-2">
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
      Excel
    </Button>
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
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">투찰 이력</h1>
          <p className="text-muted-foreground text-sm mt-1">자사 투찰 기록 및 낙찰률 추적</p>
        </div>
        <div className="flex gap-2">
          <ExcelDownloadButton />
          <Button onClick={() => setShowAdd(true)} className="gap-2">
            <Plus className="h-4 w-4" />
            이력 추가
          </Button>
        </div>
      </div>

      {/* 통계 카드 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="총 참여" value={stats.total} />
          <StatCard label="낙찰" value={stats.won} sub={`${(stats.win_rate * 100).toFixed(1)}%`} />
          <StatCard label="미낙찰" value={stats.lost} />
          <StatCard label="결과대기" value={stats.pending} />
          <StatCard
            label="평균 투찰률"
            value={stats.avg_submitted_rate != null ? `${(stats.avg_submitted_rate * 100).toFixed(4)}%` : '-'}
          />
          <StatCard
            label="AI 추천 대비 오차"
            value={stats.avg_rate_diff_from_rec != null
              ? `±${(stats.avg_rate_diff_from_rec * 100).toFixed(4)}%` : '-'}
            sub="AI 추천과의 평균 차이"
          />
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="history">이력 목록</TabsTrigger>
          <TabsTrigger value="analysis">정확도 분석</TabsTrigger>
          <TabsTrigger value="gap">역산 분석</TabsTrigger>
          <TabsTrigger value="performance">성과 분석</TabsTrigger>
        </TabsList>

        {/* 이력 목록 탭 */}
        <TabsContent value="history" className="space-y-3 mt-3">
          <div className="flex gap-2 items-center">
            <Select value={resultFilter} onValueChange={setResultFilter}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">전체</SelectItem>
                <SelectItem value="won">낙찰</SelectItem>
                <SelectItem value="lost">미낙찰</SelectItem>
                <SelectItem value="pending">결과대기</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">{records.length}건</span>
          </div>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>공고명</TableHead>
                  <TableHead>발주기관</TableHead>
                  <TableHead>투찰일</TableHead>
                  <TableHead className="text-right">기초금액</TableHead>
                  <TableHead className="text-right">투찰률</TableHead>
                  <TableHead className="text-right">AI 추천률</TableHead>
                  <TableHead className="text-right">낙찰률</TableHead>
                  <TableHead className="text-center">결과</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-10 text-muted-foreground">불러오는 중...</TableCell>
                  </TableRow>
                ) : records.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-10 text-muted-foreground">
                      투찰 이력이 없습니다. 이력 추가 버튼으로 등록하세요.
                    </TableCell>
                  </TableRow>
                ) : (
                  records.map((rec) => (
                    <TableRow key={rec.id}>
                      <TableCell className="max-w-xs truncate font-medium">{rec.title}</TableCell>
                      <TableCell className="whitespace-nowrap text-muted-foreground">{rec.agency_name || '-'}</TableCell>
                      <TableCell className="whitespace-nowrap text-muted-foreground">
                        {rec.bid_date ? new Date(rec.bid_date).toLocaleDateString('ko-KR') : '-'}
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        {rec.base_amount ? `${(rec.base_amount / 1e8).toFixed(1)}억` : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono font-semibold">{pct(rec.submitted_rate)}</TableCell>
                      <TableCell className={cn(
                        "text-right font-mono text-sm",
                        rec.recommendation_rate != null ? "text-primary" : "text-muted-foreground"
                      )}>
                        {pct(rec.recommendation_rate)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm text-muted-foreground">
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
                            const rank2 = info.participants?.find(p => p.rank === 2)
                            const isSekihai = diff < 1.0
                            return isSekihai ? (
                              <Badge variant="outline" className="text-[9px] px-1 py-0 text-orange-600 border-orange-400 gap-0.5">
                                <AlertCircle className="h-2.5 w-2.5" />惜敗 {diff.toFixed(2)}%p
                              </Badge>
                            ) : null
                          })()}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1 justify-end">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(rec)}>
                            <Edit2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive"
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
        <TabsContent value="analysis" className="space-y-4 mt-3">
          {analysis && (
            <>
              {/* 정확도 요약 카드 */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-xs text-muted-foreground mb-1">±1% 적중률</p>
                    <p className="text-2xl font-bold font-mono">
                      {analysis.accuracy_stats.accuracy_1pct != null
                        ? `${(analysis.accuracy_stats.accuracy_1pct * 100).toFixed(1)}%` : '-'}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-xs text-muted-foreground mb-1">±3% 적중률</p>
                    <p className="text-2xl font-bold font-mono">
                      {analysis.accuracy_stats.accuracy_3pct != null
                        ? `${(analysis.accuracy_stats.accuracy_3pct * 100).toFixed(1)}%` : '-'}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-xs text-muted-foreground mb-1">평균 오차</p>
                    <p className="text-2xl font-bold font-mono">
                      {analysis.accuracy_stats.avg_error != null
                        ? `±${(analysis.accuracy_stats.avg_error * 100).toFixed(4)}%` : '-'}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-xs text-muted-foreground mb-1">분석 대상</p>
                    <p className="text-2xl font-bold font-mono">{analysis.accuracy_stats.total_records}건</p>
                  </CardContent>
                </Card>
              </div>

              {/* 산점도 */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-semibold">AI 추천률 vs 실제 투찰률</CardTitle>
                </CardHeader>
                <CardContent>
                  {scatterData.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-10">
                      AI 추천률이 있는 이력 데이터가 없습니다.
                    </p>
                  ) : (
                    <ResponsiveContainer width="100%" height={280}>
                      <ScatterChart margin={{ left: -10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="x" name="AI 추천률" unit="%" type="number" domain={['auto', 'auto']} tick={{ fontSize: 11 }} />
                        <YAxis dataKey="y" name="투찰률" unit="%" type="number" domain={['auto', 'auto']} tick={{ fontSize: 11 }} />
                        <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(v: number) => v + '%'} />
                        <Scatter
                          data={scatterData.filter((p) => p.result === 'won')}
                          fill="hsl(142.1 76.2% 36.3%)"
                          name="낙찰"
                          opacity={0.8}
                        />
                        <Scatter
                          data={scatterData.filter((p) => p.result === 'lost')}
                          fill="hsl(var(--muted-foreground))"
                          name="미낙찰"
                          opacity={0.5}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              {/* 월별 MAE */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-semibold">월별 AI 추천 오차 (MAE)</CardTitle>
                </CardHeader>
                <CardContent>
                  {analysis.monthly_accuracy.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-10">월별 데이터가 없습니다.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={analysis.monthly_accuracy} margin={{ left: -10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="year_month" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 11 }} unit="%" />
                        <Tooltip formatter={(v: number) => [v + '%', 'MAE']} />
                        <Line type="monotone" dataKey="mae" stroke="hsl(var(--primary))" dot={{ r: 3 }} strokeWidth={2} connectNulls />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              {/* 월별 진단 리포트 */}
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
                  <Card className="border-blue-200 bg-blue-50/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold text-blue-700">종합 진단 리포트</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {msgs.map((m, i) => (
                        <div key={i} className={cn('flex items-start gap-2 text-sm p-2.5 rounded-md',
                          m.type === 'good' ? 'bg-green-50 text-green-700' : m.type === 'warn' ? 'bg-orange-50 text-orange-700' : 'bg-white text-muted-foreground')}>
                          <span className="shrink-0 font-bold">{m.type === 'good' ? '✓' : m.type === 'warn' ? '!' : 'ℹ'}</span>
                          {m.text}
                        </div>
                      ))}
                      <p className="text-[10px] text-muted-foreground pt-1">기준: 최근 {sorted.length}개월 투찰 이력</p>
                    </CardContent>
                  </Card>
                )
              })()}
            </>
          )}
          {!analysis && (
            <p className="text-sm text-muted-foreground text-center py-10">분석 데이터를 불러오는 중...</p>
          )}
        </TabsContent>
        {/* 역산 분석 탭 */}
        <TabsContent value="gap" className="space-y-4 mt-3">
          {gapData ? (
            gapData.total_analyzed === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-sm text-muted-foreground">
                  투찰 이력이 쌓이면 역산 분석이 가능합니다.
                  <br />
                  낙찰 결과(실제 낙찰률)가 입력된 이력이 필요합니다.
                </CardContent>
              </Card>
            ) : (
              <>
                {/* 핵심 지표 카드 */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <Card>
                    <CardContent className="pt-4">
                      <p className="text-xs text-muted-foreground mb-1">평균 격차</p>
                      <p className={cn(
                        "text-2xl font-bold font-mono",
                        gapData.mean_diff != null && gapData.mean_diff > 0
                          ? "text-orange-600"
                          : "text-blue-600"
                      )}>
                        {gapData.mean_diff != null
                          ? `${gapData.mean_diff > 0 ? '+' : ''}${(gapData.mean_diff * 100).toFixed(3)}%`
                          : '-'}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {gapData.consistent_direction === 'too_high'
                          ? '▲ 낙찰자보다 높게 투찰'
                          : gapData.consistent_direction === 'too_low'
                          ? '▼ 낙찰자보다 낮게 투찰'
                          : '— 혼합 패턴'}
                      </p>
                    </CardContent>
                  </Card>
                  {gapData.win_if_lower_by != null ? (
                    <Card className="border-orange-200 bg-orange-50/30">
                      <CardContent className="pt-4">
                        <p className="text-xs text-muted-foreground mb-1">낙찰 가능 구간</p>
                        <p className="text-2xl font-bold font-mono text-orange-600">
                          -{(gapData.win_if_lower_by * 100).toFixed(3)}%
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">낮게 투찰하면 낙찰 구간 진입</p>
                      </CardContent>
                    </Card>
                  ) : (
                    <Card>
                      <CardContent className="pt-4">
                        <p className="text-xs text-muted-foreground mb-1">낙찰 가능 구간</p>
                        <p className="text-2xl font-bold font-mono text-muted-foreground">-</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {gapData.consistent_direction === 'too_low' ? '낙찰자보다 낮게 투찰 중' : '패턴 미확정'}
                        </p>
                      </CardContent>
                    </Card>
                  )}
                  <Card>
                    <CardContent className="pt-4">
                      <p className="text-xs text-muted-foreground mb-1">분석 건수</p>
                      <p className="text-2xl font-bold font-mono">{gapData.total_analyzed}건</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        중앙값 {gapData.median_diff != null
                          ? `${gapData.median_diff > 0 ? '+' : ''}${(gapData.median_diff * 100).toFixed(3)}%`
                          : '-'}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                {/* rate_diff 분포 히스토그램 */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">
                      낙찰자 대비 투찰 격차 분포
                      <span className="text-xs font-normal text-muted-foreground ml-2">
                        (양수: 내가 높게 투찰 / 음수: 내가 낮게 투찰)
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {gapData.buckets.length === 0 ? (
                      <p className="text-sm text-muted-foreground text-center py-10">분포 데이터 없음</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart
                          data={gapData.buckets.map((b) => ({
                            mid: +((b.range_lo + b.range_hi) / 2 * 100).toFixed(3),
                            count: b.count,
                            positive: b.range_lo >= 0,
                          }))}
                          margin={{ left: -10, right: 10 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="mid" unit="%" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                          <Tooltip
                            formatter={(v: number) => [v + '건', '빈도']}
                            labelFormatter={(l) => `격차 ${l}%`}
                          />
                          <ReferenceLine x={0} stroke="hsl(var(--foreground))" strokeDasharray="4 4" strokeWidth={1.5} />
                          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                            {gapData.buckets.map((b, i) => (
                              <Cell
                                key={i}
                                fill={b.range_lo >= 0 ? 'hsl(24 95% 53%)' : 'hsl(221 83% 53%)'}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>

                {/* 개인화 편향 보정 카드 */}
                {gapData.personal_bias.sample_count > 0 && (
                  <Card className="border-blue-200 bg-blue-50/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold text-blue-700">개인화 편향 분석</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <p className="text-sm text-blue-800">{gapData.personal_bias.narrative}</p>
                      <div className="flex gap-4 text-xs text-muted-foreground">
                        <span>신뢰도: {(gapData.personal_bias.confidence * 100).toFixed(0)}%</span>
                        <span>샘플: {gapData.personal_bias.sample_count}건</span>
                        <span>편향: {gapData.personal_bias.avg_bias_pct > 0 ? '+' : ''}{gapData.personal_bias.avg_bias_pct.toFixed(3)}%</span>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )
          ) : (
            <p className="text-sm text-muted-foreground text-center py-10">분석 데이터를 불러오는 중...</p>
          )}
        </TabsContent>

        {/* 성과 분석 탭 */}
        <TabsContent value="performance" className="space-y-4 mt-3">
          {!winPattern ? (
            <p className="text-sm text-muted-foreground text-center py-10">분석 데이터를 불러오는 중...</p>
          ) : (
            <>
              {/* 편향 진단 카드 */}
              <Card className={cn(
                'border-2',
                winPattern.bias.direction === 'above'
                  ? 'border-orange-300 bg-orange-50/40'
                  : winPattern.bias.direction === 'below'
                  ? 'border-blue-300 bg-blue-50/40'
                  : 'border-border bg-muted/20'
              )}>
                <CardContent className="pt-5 pb-5">
                  <div className="flex items-start gap-4">
                    <div className={cn(
                      'text-4xl leading-none select-none',
                      winPattern.bias.direction === 'above' ? 'text-orange-500' : winPattern.bias.direction === 'below' ? 'text-blue-500' : 'text-muted-foreground'
                    )}>
                      {winPattern.bias.direction === 'above' ? '▲' : winPattern.bias.direction === 'below' ? '▼' : '—'}
                    </div>
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground mb-1">투찰 편향 진단</p>
                      <p className="text-xl font-bold mb-1">{winPattern.bias.signal}</p>
                      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground mt-2">
                        <span>평균 rate_diff: <span className="font-mono font-semibold">
                          {winPattern.bias.rate_diff_mean != null
                            ? `${winPattern.bias.rate_diff_mean > 0 ? '+' : ''}${(winPattern.bias.rate_diff_mean * 100).toFixed(3)}%p`
                            : '-'}
                        </span></span>
                        <span>총 {winPattern.total}건 중 낙찰 {winPattern.won}건 ({winPattern.overall_win_rate.toFixed(2)}%)</span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* 패배 원인 도넛차트 */}
              {winPattern.lost > 0 && (() => {
                const total = winPattern.loss_reasons.above_winner + winPattern.loss_reasons.below_floor + winPattern.loss_reasons.below_winner
                const pieData = [
                  { name: '높게 투찰', value: winPattern.loss_reasons.above_winner, fill: 'hsl(24 95% 53%)' },
                  { name: '낮게 투찰', value: winPattern.loss_reasons.below_winner, fill: 'hsl(221 83% 53%)' },
                  { name: '하한 미달', value: winPattern.loss_reasons.below_floor, fill: 'hsl(0 84% 60%)' },
                ].filter((d) => d.value > 0)
                return (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold">패배 원인 분석 ({total}건)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-col md:flex-row items-center gap-6">
                        <ResponsiveContainer width={220} height={200}>
                          <PieChart>
                            <Pie
                              data={pieData}
                              cx="50%"
                              cy="50%"
                              innerRadius={55}
                              outerRadius={85}
                              dataKey="value"
                              paddingAngle={2}
                            >
                              {pieData.map((entry, i) => (
                                <Cell key={i} fill={entry.fill} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(v: number) => [`${v}건 (${total > 0 ? (v / total * 100).toFixed(1) : 0}%)`, '']} />
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="space-y-2 flex-1">
                          {pieData.map((d) => (
                            <div key={d.name} className="flex items-center gap-2 text-sm">
                              <span className="w-3 h-3 rounded-full shrink-0" style={{ background: d.fill }} />
                              <span className="text-muted-foreground w-20">{d.name}</span>
                              <span className="font-mono font-semibold">{d.value}건</span>
                              <span className="text-muted-foreground text-xs">({total > 0 ? (d.value / total * 100).toFixed(1) : 0}%)</span>
                            </div>
                          ))}
                          <p className="text-xs text-muted-foreground pt-2">
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

              {/* 발주처별 승률 테이블 (10건 이상만) */}
              {winPattern.by_agency.filter((a) => a.total >= 10).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">발주처별 승률 (10건 이상 참여)</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>발주처</TableHead>
                          <TableHead className="text-right">참여</TableHead>
                          <TableHead className="text-right">낙찰</TableHead>
                          <TableHead className="text-right">승률</TableHead>
                          <TableHead className="text-right">평균 격차</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {winPattern.by_agency
                          .filter((a) => a.total >= 10)
                          .map((a) => (
                            <TableRow key={a.agency_name}>
                              <TableCell className="max-w-xs truncate font-medium">{a.agency_name}</TableCell>
                              <TableCell className="text-right">{a.total}</TableCell>
                              <TableCell className="text-right">{a.won}</TableCell>
                              <TableCell className={cn(
                                'text-right font-mono font-semibold',
                                a.win_rate >= 10 ? 'text-emerald-600' : a.win_rate > 0 ? 'text-primary' : 'text-muted-foreground'
                              )}>
                                {a.win_rate.toFixed(1)}%
                              </TableCell>
                              <TableCell className={cn(
                                'text-right font-mono text-sm',
                                a.avg_rate_diff == null ? 'text-muted-foreground'
                                  : a.avg_rate_diff > 0 ? 'text-orange-600'
                                  : 'text-blue-600'
                              )}>
                                {a.avg_rate_diff != null
                                  ? `${a.avg_rate_diff > 0 ? '+' : ''}${(a.avg_rate_diff * 100).toFixed(3)}%p`
                                  : '-'}
                              </TableCell>
                            </TableRow>
                          ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}

              {/* 연도별 승률 추이 LineChart */}
              {winPattern.by_year.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">연도별 승률 추이</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={winPattern.by_year} margin={{ left: -10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, 'auto']} />
                        <Tooltip
                          formatter={(v: number, name: string) => [
                            name === 'win_rate' ? `${v.toFixed(1)}%` : v + '건',
                            name === 'win_rate' ? '승률' : name === 'won' ? '낙찰' : '참여',
                          ]}
                        />
                        <Legend formatter={(v) => v === 'win_rate' ? '승률 (%)' : v === 'won' ? '낙찰 건수' : '참여 건수'} />
                        <Line type="monotone" dataKey="win_rate" stroke="hsl(142.1 76.2% 36.3%)" dot={{ r: 4 }} strokeWidth={2} name="win_rate" />
                        <Line type="monotone" dataKey="total" stroke="hsl(var(--muted-foreground))" dot={{ r: 3 }} strokeWidth={1.5} strokeDasharray="4 2" name="total" />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {winPattern.won === 0 && winPattern.lost === 0 && (
                <Card>
                  <CardContent className="py-12 text-center text-sm text-muted-foreground">
                    결과가 확정된 투찰 이력이 없습니다.<br />
                    낙찰 결과(won/lost)가 입력된 이력이 필요합니다.
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* 투찰 등록 다이얼로그 */}
      <Dialog open={showAdd} onOpenChange={(o) => { setShowAdd(o); if (!o) { setForm({ ...emptyForm }); setAnnoInput(''); setShowSuggestions(false) } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>투찰 등록</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {/* 공고번호 자동완성 */}
            <div ref={annoRef} className="relative">
              <Label className="text-xs mb-1">공고번호 (자동완성)</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                <Input
                  className="pl-8"
                  value={annoInput}
                  onChange={(e) => { setAnnoInput(e.target.value); setForm((f) => ({ ...f, announcement_no: e.target.value, bid_id: null })); setShowSuggestions(true) }}
                  onFocus={() => setShowSuggestions(true)}
                  onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                  placeholder="공고번호 입력 (2자 이상)"
                />
              </div>
              {showSuggestions && bidSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-background border rounded-md shadow-lg py-1 max-h-48 overflow-y-auto">
                  {bidSuggestions.map((item) => (
                    <button
                      key={item.id}
                      className="w-full text-left px-3 py-2 hover:bg-accent transition-colors"
                      onMouseDown={() => handleSelectBid(item)}
                    >
                      <div className="text-xs font-mono text-muted-foreground">{item.announcement_no}</div>
                      <div className="text-sm font-medium truncate">{item.title}</div>
                      <div className="text-xs text-muted-foreground">{item.agency_name} · {item.base_amount ? `${(item.base_amount / 1e8).toFixed(1)}억` : '-'}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 공고명 */}
            <div>
              <Label className="text-xs mb-1">공고명 *</Label>
              <Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="공고명 입력 (자동완성 또는 직접 입력)" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs mb-1">발주기관</Label>
                <Input value={form.agency_name} onChange={(e) => setForm((f) => ({ ...f, agency_name: e.target.value }))} placeholder="발주기관명" />
              </div>
              <div>
                <Label className="text-xs mb-1">투찰일</Label>
                <Input type="date" value={form.bid_date} onChange={(e) => setForm((f) => ({ ...f, bid_date: e.target.value }))} />
              </div>
            </div>

            <div>
              <Label className="text-xs mb-1">기초금액 (원)</Label>
              <Input type="number" value={form.base_amount} onChange={(e) => setForm((f) => ({ ...f, base_amount: e.target.value }))} placeholder="예: 500000000" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs mb-1">투찰률 (%) *</Label>
                <Input type="number" step="0.0001" value={form.submitted_rate}
                  onChange={(e) => setForm((f) => ({ ...f, submitted_rate: e.target.value }))}
                  placeholder="예: 87.9300" />
              </div>
              <div>
                <Label className="text-xs mb-1">AI 추천률 (%)</Label>
                <Input type="number" step="0.0001" value={form.recommendation_rate}
                  onChange={(e) => setForm((f) => ({ ...f, recommendation_rate: e.target.value }))}
                  placeholder="예: 87.9500" />
              </div>
            </div>

            {/* 결과 + 낙찰자 사정율 */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs mb-1">결과</Label>
                <Select value={form.result} onValueChange={(v) => setForm((f) => ({ ...f, result: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">결과대기</SelectItem>
                    <SelectItem value="won">낙찰</SelectItem>
                    <SelectItem value="lost">미낙찰</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs mb-1">낙찰자 사정율 (%)</Label>
                <Input type="number" step="0.0001" value={form.actual_winner_rate}
                  onChange={(e) => setForm((f) => ({ ...f, actual_winner_rate: e.target.value }))}
                  placeholder="예: 87.9100"
                  disabled={form.result === 'pending'} />
              </div>
            </div>

            {/* rate_diff 실시간 표시 */}
            {rateDiffDisplay !== null && (
              <div className={cn(
                'text-xs px-3 py-2 rounded-md border font-mono',
                rateDiffDisplay > 0
                  ? 'text-orange-700 bg-orange-50 border-orange-200'
                  : rateDiffDisplay < 0
                  ? 'text-blue-700 bg-blue-50 border-blue-200'
                  : 'text-green-700 bg-green-50 border-green-200'
              )}>
                rate_diff: {rateDiffDisplay > 0 ? '+' : ''}{rateDiffDisplay.toFixed(4)}%
                {rateDiffDisplay > 0 ? ' (낙찰자보다 높게 투찰)' : rateDiffDisplay < 0 ? ' (낙찰자보다 낮게 투찰)' : ' (동일)'}
              </div>
            )}

            <div>
              <Label className="text-xs mb-1">메모</Label>
              <Input value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} placeholder="메모 (선택)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowAdd(false); setForm({ ...emptyForm }); setAnnoInput('') }}>취소</Button>
            <Button onClick={handleCreate} disabled={!form.title || !form.submitted_rate || createMut.isPending}>
              {createMut.isPending ? '저장 중...' : '저장'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 결과 수정 다이얼로그 */}
      <Dialog open={!!editRecord} onOpenChange={(o) => !o && setEditRecord(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>결과 입력</DialogTitle>
          </DialogHeader>
          {editRecord && (
            <div className="space-y-3 py-2">
              <p className="text-sm font-medium truncate">{editRecord.title}</p>
              <div>
                <Label className="text-xs mb-1">결과</Label>
                <Select value={updateForm.result} onValueChange={(v) => setUpdateForm((f) => ({ ...f, result: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">결과대기</SelectItem>
                    <SelectItem value="won">낙찰</SelectItem>
                    <SelectItem value="lost">미낙찰</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs mb-1">실제 낙찰률 (%)</Label>
                <Input type="number" step="0.0001" value={updateForm.actual_winner_rate}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, actual_winner_rate: e.target.value }))}
                  placeholder="예: 87.93" />
              </div>
              <div>
                <Label className="text-xs mb-1">메모</Label>
                <Input value={updateForm.note}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, note: e.target.value }))}
                  placeholder="메모 (선택)" />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditRecord(null)}>취소</Button>
            <Button onClick={handleUpdate} disabled={updateMut.isPending}>
              {updateMut.isPending ? '저장 중...' : '저장'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}


