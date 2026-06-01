import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, ShieldCheck, Activity, Plus, Pencil, Trash2, RefreshCw, Database, Layers, Search, CheckSquare, Square, Save } from 'lucide-react'
import { adminApi, statsApi } from '@/api'
import type { AdminUser, SystemStatus, ModelInfo, IndustryFilterItem } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter
} from '@/components/ui/dialog'

const ROLE_LABELS: Record<string, { label: string; variant: 'destructive' | 'info' | 'secondary' }> = {
  admin:   { label: '관리자', variant: 'destructive' },
  analyst: { label: '분석가', variant: 'info' },
  viewer:  { label: '뷰어',   variant: 'secondary' },
}

interface UserFormState { email: string; password: string; name: string; role: string; department: string }
const EMPTY_FORM: UserFormState = { email: '', password: '', name: '', role: 'viewer', department: '' }

export default function AdminPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState('system')
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<UserFormState>(EMPTY_FORM)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
  const [indSearch, setIndSearch] = useState('')
  const [checkedIds, setCheckedIds] = useState<Set<number> | null>(null)
  const [indSaved, setIndSaved] = useState(false)

  const { data: users = [], isLoading: usersLoading } = useQuery<AdminUser[]>({
    queryKey: ['admin-users'], queryFn: adminApi.users, enabled: tab === 'users',
  })
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery<SystemStatus>({
    queryKey: ['admin-status'], queryFn: adminApi.systemStatus, enabled: tab === 'system', refetchInterval: 30000,
  })
  const { data: modelInfo } = useQuery<ModelInfo>({
    queryKey: ['model-info'], queryFn: () => statsApi.modelInfo(), enabled: tab === 'system',
  })
  const { data: industryFilters = [], isLoading: indLoading } = useQuery<IndustryFilterItem[]>({
    queryKey: ['admin-industry-filters'], queryFn: adminApi.industryFilters, enabled: tab === 'industries',
  })


  const { data: collectionLogs = [] } = useQuery({
    queryKey: ['admin-collection-logs'],
    queryFn: () => adminApi.collectionLogs(7),
    enabled: tab === 'system',
    refetchInterval: 60000,
  })
  if (checkedIds === null && industryFilters.length > 0) {
    setCheckedIds(new Set(industryFilters.filter((i) => i.is_active).map((i) => i.industry_id)))
  }

  const createMutation = useMutation({
    mutationFn: adminApi.createUser,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); resetForm() },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => adminApi.updateUser(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); resetForm() },
  })
  const deleteMutation = useMutation({
    mutationFn: adminApi.deleteUser,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); setDeleteConfirm(null) },
  })
  const retrainMutation = useMutation({
    mutationFn: async () => { const { recommendApi } = await import('@/api'); return recommendApi.retrain() },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['model-info'] }) },
  })
  const saveIndMutation = useMutation({
    mutationFn: (ids: number[]) => adminApi.updateIndustryFilters(ids),
    onSuccess: () => {
      setIndSaved(true)
      qc.invalidateQueries({ queryKey: ['admin-industry-filters'] })
      qc.invalidateQueries({ queryKey: ['stats-overview'] })
      qc.invalidateQueries({ queryKey: ['stats-cluster'] })
      qc.invalidateQueries({ queryKey: ['stats-heatmap'] })
      setTimeout(() => setIndSaved(false), 3000)
    },
  })

  function resetForm() { setShowForm(false); setEditId(null); setForm(EMPTY_FORM) }
  function handleEdit(u: AdminUser) {
    setEditId(u.id); setForm({ email: u.email, password: '', name: u.name ?? '', role: u.role, department: u.department ?? '' }); setShowForm(true)
  }
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (editId !== null) {
      const body: Record<string, unknown> = { name: form.name, role: form.role, department: form.department || undefined }
      if (form.password) body.password = form.password
      updateMutation.mutate({ id: editId, body })
    } else {
      createMutation.mutate({ email: form.email, password: form.password, name: form.name, role: form.role, department: form.department || undefined })
    }
  }
  const currentChecked = useMemo(() => {
    if (checkedIds !== null) return checkedIds
    return new Set(industryFilters.filter((i) => i.is_active).map((i) => i.industry_id))
  }, [checkedIds, industryFilters])
  const filteredIndustries = useMemo(() =>
    industryFilters.filter((i) => i.name.toLowerCase().includes(indSearch.toLowerCase())),
    [industryFilters, indSearch]
  )
  function toggleIndustry(id: number) {
    const next = new Set(currentChecked)
    if (next.has(id)) next.delete(id); else next.add(id)
    setCheckedIds(next); setIndSaved(false)
  }

  const stats = status?.db_stats
  const collector = status?.collector
  const activeCount = currentChecked.size
  const totalCount = industryFilters.length

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-destructive" />
        <h1 className="text-2xl font-bold tracking-tight">관리자</h1>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="system" className="gap-1.5"><Activity className="h-3.5 w-3.5" />시스템 현황</TabsTrigger>
          <TabsTrigger value="users" className="gap-1.5"><Users className="h-3.5 w-3.5" />사용자 관리</TabsTrigger>
          <TabsTrigger value="industries" className="gap-1.5"><Layers className="h-3.5 w-3.5" />공종 관리</TabsTrigger>
        </TabsList>

        <TabsContent value="system" className="space-y-5 mt-4">
          {statusLoading ? <Skeleton className="h-64 w-full" /> : stats ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: '전체 공고', value: stats.total_bids.toLocaleString(), sub: `나라장터 ${stats.g2b_bids.toLocaleString()}건`, icon: Database, color: 'text-blue-600' },
                  { label: '7일 신규', value: stats.new_bids_7d.toLocaleString(), icon: Activity, color: 'text-green-600' },
                  { label: '개찰결과', value: stats.total_results.toLocaleString(), icon: Activity, color: 'text-purple-600' },
                  { label: '경쟁사', value: stats.total_competitors.toLocaleString(), icon: Users, color: 'text-orange-600' },
                ].map(({ label, value, sub, icon: Icon, color }) => (
                  <Card key={label}>
                    <CardContent className="pt-4 pb-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-muted-foreground">{label}</span>
                        <Icon className={cn('h-4 w-4', color)} />
                      </div>
                      <div className="text-2xl font-bold">{value}</div>
                      {sub && <div className="text-xs text-muted-foreground mt-0.5">{sub}</div>}
                    </CardContent>
                  </Card>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm">수집기 상태</CardTitle>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => refetchStatus()}>
                        <RefreshCw className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-muted-foreground">상태</span>
                      <Badge variant={collector?.enabled ? 'success' : 'secondary'}>{collector?.enabled ? '활성' : '비활성'}</Badge>
                    </div>
                    <div className="flex justify-between"><span className="text-muted-foreground">마지막 수집</span>
                      <span className="text-xs">{collector?.last_g2b_collect ? new Date(collector.last_g2b_collect).toLocaleString('ko-KR') : '없음'}</span>
                    </div>
                    <div className="flex justify-between"><span className="text-muted-foreground">활성 키워드</span><span>{stats.active_keywords}개</span></div>
                    {status?.daily_collection && status.daily_collection.length > 0 && (
                      <div className="border-t pt-2 mt-1">
                        <div className="text-xs text-muted-foreground mb-1">최근 수집 현황</div>
                        {status.daily_collection.slice(0, 5).map((d) => (
                          <div key={d.date} className="flex justify-between text-xs">
                            <span className="text-muted-foreground">{d.date}</span>
                            <span>{d.count.toLocaleString()}건</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm">ML 모델 상태</CardTitle>
                      <Button size="sm" variant="outline" className="h-7 text-xs"
                        onClick={() => retrainMutation.mutate()} disabled={retrainMutation.isPending}>
                        {retrainMutation.isPending ? '학습 중...' : '재학습'}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {modelInfo ? (
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-muted-foreground">모델 버전</span><span className="font-mono text-xs">{modelInfo.model.version}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">학습 데이터</span><span>{(modelInfo.model.train_size || 0).toLocaleString()}건</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">낙찰 데이터</span><span>{(modelInfo.model.winner_size || 0).toLocaleString()}건</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">ML 준비</span>
                          <Badge variant={modelInfo.data_availability.ready_for_ml ? 'success' : 'warning'}>
                            {modelInfo.data_availability.ready_for_ml ? '가능' : `미충족 (${modelInfo.data_availability.winner_results}/20건)`}
                          </Badge>
                        </div>
                        <div className="flex justify-between"><span className="text-muted-foreground">30일 추천 요청</span><span>{modelInfo.usage.predictions_30d}회</span></div>
                      </div>
                    ) : <div className="text-sm text-muted-foreground">정보 없음</div>}
                    {retrainMutation.isSuccess && <div className="mt-2 text-xs text-green-600">재학습 완료!</div>}
                    {retrainMutation.isError && <div className="mt-2 text-xs text-destructive">재학습 실패 (관리자 권한 필요)</div>}
                  </CardContent>
                </Card>
              </div>
            </>
          ) : null}

              {collectionLogs.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">수집 이력 (최근 7일)</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>수집 유형</TableHead>
                          <TableHead>수집 시각</TableHead>
                          <TableHead className="text-center">성공</TableHead>
                          <TableHead className="text-center">실패</TableHead>
                          <TableHead className="text-right">소요(초)</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {collectionLogs.map((log: { id: number; collect_type: string; collected_at: string; success_count: number; fail_count: number; duration_sec: number | null }) => (
                          <TableRow key={log.id}>
                            <TableCell>
                              <Badge variant={log.collect_type === 'notice_cnstwk' ? 'info' : log.collect_type === 'notice_servc' ? 'secondary' : 'outline'} className="text-[10px] px-1.5">
                                {log.collect_type}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                              {new Date(log.collected_at).toLocaleString('ko-KR')}
                            </TableCell>
                            <TableCell className="text-center text-green-600 font-bold">{log.success_count}</TableCell>
                            <TableCell className="text-center text-destructive">{log.fail_count}</TableCell>
                            <TableCell className="text-right text-xs">{log.duration_sec?.toFixed(1) ?? '-'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
        </TabsContent>

        <TabsContent value="users" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Button onClick={() => { resetForm(); setShowForm(true) }} size="sm">
              <Plus className="h-4 w-4" /> 사용자 추가
            </Button>
          </div>

          {showForm && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">{editId !== null ? '사용자 수정' : '새 사용자 추가'}</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {editId === null && (
                    <div className="space-y-2"><Label>이메일 *</Label>
                      <Input type="email" value={form.email} required onChange={(e) => setForm({ ...form, email: e.target.value })} />
                    </div>
                  )}
                  <div className="space-y-2"><Label>이름 *</Label>
                    <Input type="text" value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </div>
                  <div className="space-y-2"><Label>{editId ? '비밀번호 (변경 시만)' : '비밀번호 *'}</Label>
                    <Input type="password" value={form.password} required={editId === null} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                  </div>
                  <div className="space-y-2"><Label>역할</Label>
                    <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="viewer">뷰어</SelectItem>
                        <SelectItem value="analyst">분석가</SelectItem>
                        <SelectItem value="admin">관리자</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2"><Label>부서</Label>
                    <Input type="text" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
                  </div>
                  <div className="md:col-span-3 flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={resetForm}>취소</Button>
                    <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                      {editId !== null ? '수정' : '추가'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          <Card>
            {usersLoading ? (
              <div className="p-8 space-y-2">{Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
            ) : (
              <Table>
                <TableHeader><TableRow>
                  <TableHead>이름</TableHead><TableHead>이메일</TableHead><TableHead>역할</TableHead>
                  <TableHead>부서</TableHead><TableHead>마지막 로그인</TableHead><TableHead>상태</TableHead><TableHead>관리</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {users.map((u) => (
                    <TableRow key={u.id} className={cn(!u.is_active && 'opacity-50')}>
                      <TableCell className="font-medium">{u.name || '-'}</TableCell>
                      <TableCell className="text-muted-foreground">{u.email}</TableCell>
                      <TableCell>
                        <Badge variant={(ROLE_LABELS[u.role]?.variant ?? 'secondary') as 'destructive' | 'info' | 'secondary'}>
                          {ROLE_LABELS[u.role]?.label ?? u.role}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{u.department || '-'}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{u.last_login ? new Date(u.last_login).toLocaleString('ko-KR') : '없음'}</TableCell>
                      <TableCell>
                        <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                          onClick={() => updateMutation.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                          {u.is_active ? '활성' : '비활성'}
                        </Button>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleEdit(u)}><Pencil className="h-3.5 w-3.5" /></Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => setDeleteConfirm(u.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="industries" className="space-y-4 mt-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-700">
            <strong>공종 필터 설정</strong> — 체크된 공종의 입찰만 시스템 전체에서 활용됩니다.
          </div>
          {indLoading ? <Skeleton className="h-64 w-full" /> : (
            <>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input value={indSearch} onChange={(e) => setIndSearch(e.target.value)} placeholder="공종 검색..." className="pl-8 w-64" />
                  </div>
                  <Button variant="outline" size="sm" onClick={() => { setCheckedIds(new Set(industryFilters.map((i) => i.industry_id))); setIndSaved(false) }}>
                    <CheckSquare className="h-3.5 w-3.5" /> 전체 선택
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => { setCheckedIds(new Set()); setIndSaved(false) }}>
                    <Square className="h-3.5 w-3.5" /> 전체 해제
                  </Button>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">
                    <strong className="text-primary">{activeCount}</strong> / {totalCount}개 선택됨
                    {activeCount === totalCount && <span className="ml-1 text-xs text-green-600">(전체 = 필터 없음)</span>}
                  </span>
                  <Button size="sm" onClick={() => saveIndMutation.mutate(Array.from(currentChecked))} disabled={saveIndMutation.isPending}>
                    <Save className="h-4 w-4" /> {saveIndMutation.isPending ? '저장 중...' : '저장'}
                  </Button>
                  {indSaved && <span className="text-xs text-green-600 font-medium">저장 완료!</span>}
                  {saveIndMutation.isError && <span className="text-xs text-destructive">저장 실패</span>}
                </div>
              </div>
              <Card>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                  {filteredIndustries.length === 0 ? (
                    <div className="col-span-3 p-8 text-center text-muted-foreground">검색 결과 없음</div>
                  ) : filteredIndustries.map((ind) => {
                    const checked = currentChecked.has(ind.industry_id)
                    return (
                      <label key={ind.industry_id}
                        className={cn('flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors hover:bg-accent border-b last:border-b-0 md:border-b', checked && 'bg-accent/50')}>
                        <input type="checkbox" checked={checked} onChange={() => toggleIndustry(ind.industry_id)}
                          className="w-4 h-4 rounded accent-primary cursor-pointer shrink-0" />
                        <div className="min-w-0">
                          <div className={cn('text-sm font-medium truncate', checked ? 'text-primary' : 'text-foreground')}>{ind.name}</div>
                          <div className="text-xs text-muted-foreground font-mono">{ind.code}</div>
                        </div>
                        {checked && <Badge variant="info" className="ml-auto shrink-0 text-[10px] px-1.5 py-0">활성</Badge>}
                      </label>
                    )
                  })}
                </div>
              </Card>
            </>
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={deleteConfirm !== null} onOpenChange={(o) => { if (!o) setDeleteConfirm(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>사용자 삭제</DialogTitle>
            <DialogDescription>이 사용자를 삭제하시겠습니까?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>취소</Button>
            <Button variant="destructive" onClick={() => deleteConfirm !== null && deleteMutation.mutate(deleteConfirm)} disabled={deleteMutation.isPending}>삭제</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}