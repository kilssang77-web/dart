import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus, Pencil, Trash2, Search, Tag, ToggleLeft, ToggleRight, BookMarked, ExternalLink, AlertCircle } from 'lucide-react'
import { keywordsApi, bidsApi } from '@/api'
import type { WatchKeyword } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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

const KW_TYPE_LABELS: Record<string, { label: string; variant: 'default' | 'secondary' | 'info'; desc: string }> = {
  agency:  { label: '발주기관', variant: 'info',      desc: '발주기관명에서 검색' },
  title:   { label: '공고명',   variant: 'default',   desc: '공고 제목에서 검색' },
  general: { label: '일반',     variant: 'secondary', desc: '공고명에서 검색(기본)' },
}

interface KeywordMatch {
  keyword_id: number; keyword: string; kw_type: string; note: string | null
  match_count: number; new_7d: number
  recent_bids: { id: number; title: string; agency_name: string; base_amount: number; notice_date: string | null; status: string }[]
}

interface FormState { keyword: string; kw_type: string; note: string }
const EMPTY_FORM: FormState = { keyword: '', kw_type: 'general', note: '' }

export default function KeywordsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: keywords = [], isLoading } = useQuery<WatchKeyword[]>({
    queryKey: ['keywords'], queryFn: keywordsApi.list,
  })
  const { data: matches = [] } = useQuery<KeywordMatch[]>({
    queryKey: ['keyword-matches'], queryFn: bidsApi.keywordMatches, staleTime: 60_000,
  })

  const createMutation = useMutation({
    mutationFn: keywordsApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['keywords'] }); qc.invalidateQueries({ queryKey: ['keyword-matches'] }); resetForm() },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Pick<WatchKeyword, 'keyword' | 'kw_type' | 'is_active' | 'note'>> }) =>
      keywordsApi.update(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['keywords'] }); qc.invalidateQueries({ queryKey: ['keyword-matches'] }); resetForm() },
  })
  const deleteMutation = useMutation({
    mutationFn: keywordsApi.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['keywords'] }); qc.invalidateQueries({ queryKey: ['keyword-matches'] }); setDeleteConfirm(null) },
  })
  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => keywordsApi.update(id, { is_active }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['keywords'] }); qc.invalidateQueries({ queryKey: ['keyword-matches'] }) },
  })

  function resetForm() { setShowForm(false); setEditId(null); setForm(EMPTY_FORM) }
  function handleEdit(kw: WatchKeyword) { setEditId(kw.id); setForm({ keyword: kw.keyword, kw_type: kw.kw_type, note: kw.note ?? '' }); setShowForm(true) }
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.keyword.trim()) return
    const body = { keyword: form.keyword.trim(), kw_type: form.kw_type, note: form.note.trim() || undefined }
    if (editId !== null) updateMutation.mutate({ id: editId, body })
    else createMutation.mutate(body)
  }
  function goToBids(keyword: string) { navigate(`/bids?keyword=${encodeURIComponent(keyword)}`) }

  const filtered = keywords.filter(
    (kw) => kw.keyword.toLowerCase().includes(search.toLowerCase()) || (kw.note ?? '').toLowerCase().includes(search.toLowerCase())
  )
  const activeCount = keywords.filter((k) => k.is_active).length
  const matchMap = Object.fromEntries(matches.map((m) => [m.keyword_id, m]))
  const totalNew7d = matches.reduce((s, m) => s + m.new_7d, 0)

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <BookMarked className="h-5 w-5 text-primary" /> 키워드 관리
          </h1>
          <p className="text-muted-foreground text-sm mt-1">전체 {keywords.length}개 / 활성 {activeCount}개</p>
        </div>
        <Button onClick={() => { resetForm(); setShowForm(true) }} size="sm">
          <Plus className="h-4 w-4" /> 키워드 추가
        </Button>
      </div>

      <Card>
        <CardContent className="py-3 px-4 space-y-1.5">
          <p className="text-sm font-semibold flex items-center gap-1.5"><Tag className="h-3.5 w-3.5" /> 키워드 활용 방법</p>
          <ul className="text-xs space-y-1 text-muted-foreground list-disc list-inside">
            <li><strong>공고명 키워드</strong> — 입찰 제목에 해당 단어가 포함된 공고를 즉시 검색</li>
            <li><strong>발주기관 키워드</strong> — 특정 기관에서 발주한 공고를 모니터링</li>
            <li>각 키워드별 매칭 공고 수와 최근 7일 신규 건수를 확인하고 빠르게 이동할 수 있습니다.</li>
          </ul>
        </CardContent>
      </Card>

      {totalNew7d > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 flex items-center gap-2 text-sm text-orange-700">
          <AlertCircle className="h-4 w-4" />
          최근 7일 내 키워드 매칭 신규 공고 <strong>{totalNew7d}건</strong>이 있습니다.
        </div>
      )}

      {showForm && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">{editId !== null ? '키워드 수정' : '새 키워드 추가'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div className="md:col-span-2 space-y-2">
                <Label>키워드 *</Label>
                <Input type="text" value={form.keyword} onChange={(e) => setForm({ ...form, keyword: e.target.value })}
                  placeholder="예: 서울시, 도로공사, 교량..." required />
              </div>
              <div className="space-y-2">
                <Label>유형</Label>
                <Select value={form.kw_type} onValueChange={(v) => setForm({ ...form, kw_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">일반 (공고명 검색)</SelectItem>
                    <SelectItem value="agency">발주기관명 검색</SelectItem>
                    <SelectItem value="title">공고명 검색</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">{KW_TYPE_LABELS[form.kw_type]?.desc}</p>
              </div>
              <div className="space-y-2">
                <Label>메모</Label>
                <Input type="text" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="선택사항" />
              </div>
              <div className="md:col-span-4 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={resetForm}>취소</Button>
                <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                  {editId !== null ? '수정' : '추가'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="키워드 검색..." className="pl-9" />
      </div>

      <Card>
        {isLoading ? (
          <div className="p-8 space-y-2">{Array.from({length: 4}).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">
            {search ? '검색 결과가 없습니다.' : '등록된 키워드가 없습니다. 키워드를 추가해보세요.'}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>키워드</TableHead>
                <TableHead>유형</TableHead>
                <TableHead>매칭 공고</TableHead>
                <TableHead>메모</TableHead>
                <TableHead>활성</TableHead>
                <TableHead>등록일</TableHead>
                <TableHead>관리</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((kw) => {
                const m = matchMap[kw.id]
                const isExpanded = expandedId === kw.id
                const kwType = KW_TYPE_LABELS[kw.kw_type] ?? KW_TYPE_LABELS.general
                return (
                  <>
                    <TableRow key={kw.id} className={cn(!kw.is_active && 'opacity-50')}>
                      <TableCell className="font-medium">
                        <span className="flex items-center gap-1.5">
                          <Tag className="h-3 w-3 text-muted-foreground" /> {kw.keyword}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={kwType.variant as 'default' | 'secondary' | 'info'}>{kwType.label}</Badge>
                      </TableCell>
                      <TableCell>
                        {kw.is_active && m ? (
                          <div className="flex items-center gap-2">
                            <button onClick={() => goToBids(kw.keyword)}
                              className="flex items-center gap-1 text-primary hover:underline font-semibold text-sm">
                              <ExternalLink className="h-3 w-3" /> {m.match_count.toLocaleString()}건
                            </button>
                            {m.new_7d > 0 && (
                              <Badge variant="warning" className="text-[10px] px-1.5 py-0">+{m.new_7d} 신규</Badge>
                            )}
                            {m.recent_bids.length > 0 && (
                              <button onClick={() => setExpandedId(isExpanded ? null : kw.id)}
                                className="text-xs text-muted-foreground hover:text-foreground underline">
                                {isExpanded ? '접기' : '최근 공고'}
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">{kw.is_active ? '집계 중...' : '비활성'}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">{kw.note ?? '-'}</TableCell>
                      <TableCell>
                        <button onClick={() => toggleMutation.mutate({ id: kw.id, is_active: !kw.is_active })}
                          title={kw.is_active ? '비활성화' : '활성화'}>
                          {kw.is_active
                            ? <ToggleRight className="h-6 w-6 text-primary" />
                            : <ToggleLeft className="h-6 w-6 text-muted-foreground" />}
                        </button>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">{new Date(kw.created_at).toLocaleDateString('ko-KR')}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleEdit(kw)} title="수정">
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => setDeleteConfirm(kw.id)} title="삭제">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && m && m.recent_bids.length > 0 && (
                      <TableRow key={`${kw.id}-expand`}>
                        <TableCell colSpan={7} className="bg-muted/20 px-6 pb-3">
                          <div className="text-xs font-semibold text-muted-foreground mb-1.5 mt-1">최근 매칭 공고</div>
                          <div className="space-y-1">
                            {m.recent_bids.map((b) => (
                              <div key={b.id}
                                className="flex items-center justify-between bg-background rounded-lg px-3 py-1.5 border hover:border-primary cursor-pointer"
                                onClick={() => navigate(`/bids/${b.id}`)}>
                                <div className="truncate max-w-md">
                                  <span className="text-primary font-medium text-xs">{b.title}</span>
                                  <span className="text-muted-foreground ml-2 text-xs">{b.agency_name}</span>
                                </div>
                                <div className="flex items-center gap-2 shrink-0 ml-2">
                                  <span className="text-xs text-muted-foreground">{b.notice_date ? new Date(b.notice_date).toLocaleDateString('ko-KR') : '-'}</span>
                                  <Badge variant={b.status === 'open' ? 'success' : 'secondary'} className="text-[10px] px-1.5 py-0">
                                    {b.status === 'open' ? '공고중' : '개찰완료'}
                                  </Badge>
                                </div>
                              </div>
                            ))}
                          </div>
                          <button onClick={() => goToBids(kw.keyword)}
                            className="mt-2 text-xs text-primary hover:underline flex items-center gap-1">
                            <ExternalLink className="h-3 w-3" /> 전체 {m.match_count}건 보기
                          </button>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={deleteConfirm !== null} onOpenChange={(o) => { if (!o) setDeleteConfirm(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>키워드 삭제</DialogTitle>
            <DialogDescription>이 키워드를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>취소</Button>
            <Button variant="destructive" onClick={() => deleteConfirm !== null && deleteMutation.mutate(deleteConfirm)}
              disabled={deleteMutation.isPending}>삭제</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}