import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, CheckCircle2, XCircle, Clock, Trash2, Edit2 } from 'lucide-react'
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line
} from 'recharts'
import { myBidsApi } from '@/api'
import type { MyBidRecord, MyBidAnalysis, DefeatAnalysis } from '@/types'
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
  title: '', agency_name: '', bid_date: '', base_amount: '',
  submitted_rate: '', recommendation_rate: '', note: '',
}

export default function MyBidsPage() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState('history')
  const [resultFilter, setResultFilter] = useState('all')
  const [showAdd, setShowAdd] = useState(false)
  const [editRecord, setEditRecord] = useState<MyBidRecord | null>(null)
  const [form, setForm] = useState({ ...emptyForm })
  const [updateForm, setUpdateForm] = useState({ result: 'pending', actual_winner_rate: '', note: '' })

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

  const { data: records = [], isLoading } = useQuery<MyBidRecord[]>({
    queryKey: ['my-bids', resultFilter],
    queryFn: () => myBidsApi.list({ result: resultFilter === 'all' ? undefined : resultFilter }),
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
    })
  }

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
        <Button onClick={() => setShowAdd(true)} className="gap-2">
          <Plus className="h-4 w-4" />
          이력 추가
        </Button>
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
                        <ResultBadge result={rec.result as ResultType} />
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
      </Tabs>

      {/* 이력 추가 다이얼로그 */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>투찰 이력 추가</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-xs mb-1">공고명 *</Label>
              <Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="공고명 입력" />
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
                  placeholder="예: 87.93" />
              </div>
              <div>
                <Label className="text-xs mb-1">AI 추천률 (%)</Label>
                <Input type="number" step="0.0001" value={form.recommendation_rate}
                  onChange={(e) => setForm((f) => ({ ...f, recommendation_rate: e.target.value }))}
                  placeholder="예: 87.95" />
              </div>
            </div>
            <div>
              <Label className="text-xs mb-1">메모</Label>
              <Input value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} placeholder="메모 (선택)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>취소</Button>
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


