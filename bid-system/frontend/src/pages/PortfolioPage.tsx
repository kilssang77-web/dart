import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  PackageCheck, Zap, TrendingUp, AlertTriangle, CheckCircle2, XCircle,
  Minus, Loader2, RefreshCw, ChevronDown, ChevronUp, CalendarDays,
} from 'lucide-react'
import { portfolioApi, bidsApi } from '../api'
import type { PortfolioBidItem, PortfolioPlanResponse, ActivePortfolioItem } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// ── 상수 ────────────────────────────────────────────────────

const VERDICT_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  GO:     { label: 'GO',     color: 'bg-green-100 text-green-700 border-green-300',  icon: <CheckCircle2 className="h-3 w-3" /> },
  WATCH:  { label: 'WATCH',  color: 'bg-yellow-100 text-yellow-700 border-yellow-300', icon: <Minus className="h-3 w-3" /> },
  NO_GO:  { label: 'NO-GO',  color: 'bg-red-100 text-red-700 border-red-300',        icon: <XCircle className="h-3 w-3" /> },
}

// ── 유틸 ────────────────────────────────────────────────────

const fmt억 = (n: number) => n >= 1e8 ? `${(n / 1e8).toFixed(1)}억` : `${Math.round(n / 10000).toLocaleString()}만`
const fmtPct = (r: number) => `${(r * 100).toFixed(1)}%`

// ── 서브 컴포넌트 ────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string }) {
  const m = VERDICT_META[verdict] ?? VERDICT_META['WATCH']
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border', m.color)}>
      {m.icon} {m.label}
    </span>
  )
}

function KpiCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <Card className="relative overflow-hidden">
      <div className={cn('absolute top-0 left-0 right-0 h-0.5', accent ?? 'bg-blue-500')} />
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold mt-0.5">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  )
}

function BidRow({
  item,
  tag,
  checked,
  onToggle,
}: {
  item: { id: number; title: string; base_amount: number; bid_open_date?: string }
  tag?: 'selected' | 'not_selected' | 'no_go'
  checked?: boolean
  onToggle?: () => void
}) {
  const tagStyle = tag === 'selected'
    ? 'border-l-2 border-green-400'
    : tag === 'not_selected'
    ? 'border-l-2 border-yellow-400'
    : tag === 'no_go'
    ? 'border-l-2 border-red-300 opacity-60'
    : ''

  return (
    <div className={cn('flex items-center gap-3 px-3 py-2 bg-white rounded-md border mb-1.5 text-sm', tagStyle)}>
      {onToggle && (
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="h-4 w-4 rounded accent-blue-600 cursor-pointer"
        />
      )}
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{item.title}</p>
        <p className="text-xs text-muted-foreground">
          {fmt억(item.base_amount)}
          {item.bid_open_date && ` · 개찰 ${item.bid_open_date.slice(0, 10)}`}
        </p>
      </div>
    </div>
  )
}

function ResultBidRow({ item, category }: { item: PortfolioBidItem; category: 'selected' | 'not_selected' | 'no_go' }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={cn(
      'border rounded-md mb-1.5 bg-white',
      category === 'selected' ? 'border-l-4 border-l-green-400' :
      category === 'not_selected' ? 'border-l-4 border-l-yellow-400' :
      'border-l-4 border-l-red-300 opacity-70'
    )}>
      <div
        className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50"
        onClick={() => setOpen(o => !o)}
      >
        <VerdictBadge verdict={item.verdict} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.title}</p>
          <p className="text-xs text-muted-foreground">
            {fmt억(item.base_amount)} · 개찰 {item.bid_date}
          </p>
        </div>
        <div className="text-xs text-right shrink-0 text-muted-foreground">
          <div>낙찰 {fmtPct(item.win_prob)}</div>
          <div>점수 {item.selection_score.toFixed(1)}</div>
        </div>
        {open ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
      </div>
      {open && (
        <div className="px-4 pb-3 border-t bg-gray-50">
          <div className="grid grid-cols-3 gap-3 mt-2 text-xs">
            <div>
              <p className="text-muted-foreground">적격 통과율</p>
              <p className="font-medium">{fmtPct(item.qualify_prob)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">낙찰 확률</p>
              <p className="font-medium">{fmtPct(item.win_prob)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">추천 투찰율</p>
              <p className="font-medium text-blue-600">{fmtPct(item.recommended_rate)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">선별 점수</p>
              <p className="font-medium">{item.selection_score.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">기대가치(EV)</p>
              <p className="font-medium">{fmt억(item.ev_score)}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 현재 활성 포트폴리오 패널 ────────────────────────────────

function ActivePortfolioPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['portfolio-active'],
    queryFn: portfolioApi.active,
    refetchInterval: 60_000,
  })
  const active: ActivePortfolioItem[] = data?.active ?? []

  if (isLoading) return null
  if (active.length === 0) return (
    <Card className="p-4 text-sm text-muted-foreground text-center">활성 포트폴리오 없음</Card>
  )

  return (
    <Card>
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-blue-500" />
          현재 활성 포트폴리오 ({active.length}건)
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-1">
        {active.map((a) => (
          <div key={a.bid_id} className="flex items-center gap-2 text-xs py-1.5 border-b last:border-0">
            <Badge variant="outline" className="text-blue-600 border-blue-300">{a.status}</Badge>
            <span className="flex-1 truncate font-medium">{a.title}</span>
            <span className="text-muted-foreground shrink-0">{fmt억(a.base_amount)}</span>
            {a.bid_date && <span className="text-muted-foreground shrink-0">{a.bid_date.slice(0, 10)}</span>}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// ── 메인 페이지 ──────────────────────────────────────────────

export default function PortfolioPage() {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [result, setResult] = useState<PortfolioPlanResponse | null>(null)

  // 개찰 예정 공고 (14일 이내)
  const { data: bidsData, isLoading: bidsLoading } = useQuery({
    queryKey: ['portfolio-bids'],
    queryFn: () => bidsApi.list({ limit: 50 }),
  })

  const optimizeMut = useMutation({
    mutationFn: () => portfolioApi.optimize(Array.from(selectedIds)),
    onSuccess: (data: PortfolioPlanResponse) => setResult(data),
  })

  const bids = bidsData?.items ?? []

  const toggle = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === bids.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(bids.map((b) => b.id)))
  }

  const resultSelectedIds = new Set(result?.selected.map((i) => i.bid_id) ?? [])
  const resultNotSelectedIds = new Set(result?.not_selected.map((i) => i.bid_id) ?? [])
  const resultNoGoIds = new Set(result?.no_go_list.map((i) => i.bid_id) ?? [])

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto space-y-6">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <PackageCheck className="h-6 w-6 text-blue-600" />
          <div>
            <h1 className="text-xl font-bold">포트폴리오 최적화</h1>
            <p className="text-xs text-muted-foreground">
              보증한도·동시 진행 제약 하에서 기대 수주건수를 최대화하는 투찰 조합을 추천합니다
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* 좌측: 공고 선택 */}
        <div className="lg:col-span-1 space-y-3">
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">최적화 대상 공고</CardTitle>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{selectedIds.size}/{bids.length} 선택</span>
                  <button
                    onClick={toggleAll}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    {selectedIds.size === bids.length ? '전체 해제' : '전체 선택'}
                  </button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              {bidsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : bids.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-6">조회된 공고가 없습니다.</p>
              ) : (
                <div className="max-h-[480px] overflow-y-auto space-y-0.5 pr-1">
                  {bids.map((bid) => {
                    const tag = result
                      ? resultSelectedIds.has(bid.id) ? 'selected'
                        : resultNotSelectedIds.has(bid.id) ? 'not_selected'
                        : resultNoGoIds.has(bid.id) ? 'no_go'
                        : undefined
                      : undefined
                    return (
                      <BidRow
                        key={bid.id}
                        item={{ id: bid.id, title: bid.title, base_amount: bid.base_amount, bid_open_date: bid.bid_open_date }}
                        checked={selectedIds.has(bid.id)}
                        onToggle={() => toggle(bid.id)}
                        tag={tag}
                      />
                    )
                  })}
                </div>
              )}

              <Button
                className="w-full mt-4"
                disabled={selectedIds.size === 0 || optimizeMut.isPending}
                onClick={() => optimizeMut.mutate()}
              >
                {optimizeMut.isPending
                  ? <><Loader2 className="h-4 w-4 animate-spin mr-2" />최적화 중…</>
                  : <><Zap className="h-4 w-4 mr-2" />포트폴리오 최적화 실행</>
                }
              </Button>
            </CardContent>
          </Card>

          <ActivePortfolioPanel />
        </div>

        {/* 우측: 결과 */}
        <div className="lg:col-span-2 space-y-4">
          {!result ? (
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground rounded-xl border-2 border-dashed">
              <PackageCheck className="h-12 w-12 mb-3 opacity-30" />
              <p className="text-sm">왼쪽에서 공고를 선택하고<br />최적화를 실행하세요.</p>
            </div>
          ) : (
            <>
              {/* 알림 배너 */}
              {result.alerts.length > 0 && (
                <div className="flex items-start gap-2 p-3 rounded-md bg-amber-50 border border-amber-200 text-sm text-amber-700">
                  <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                  <ul className="space-y-0.5">
                    {result.alerts.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}

              {/* KPI 카드 */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <KpiCard
                  label="기대 수주 건수"
                  value={result.expected_wins.toFixed(1) + '건'}
                  accent="bg-green-500"
                />
                <KpiCard
                  label="기대 수주 금액"
                  value={fmt억(result.expected_win_amount)}
                  accent="bg-blue-500"
                />
                <KpiCard
                  label="보증 사용액"
                  value={fmt억(result.bond_usage)}
                  sub={`잔여 ${fmt억(result.remaining_bond_after)}`}
                  accent="bg-orange-400"
                />
                <KpiCard
                  label="총 기대가치(EV)"
                  value={fmt억(result.total_ev)}
                  accent="bg-purple-500"
                />
              </div>

              {/* 투찰 권장 */}
              {result.selected.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                    <span className="text-sm font-semibold text-green-700">
                      투찰 권장 ({result.selected.length}건)
                    </span>
                  </div>
                  {result.selected.map((item) => (
                    <ResultBidRow key={item.bid_id} item={item} category="selected" />
                  ))}
                </div>
              )}

              {/* 제약으로 미선택 */}
              {result.not_selected.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Minus className="h-4 w-4 text-yellow-600" />
                    <span className="text-sm font-semibold text-yellow-700">
                      제약으로 미선택 ({result.not_selected.length}건)
                    </span>
                    <span className="text-xs text-muted-foreground">보증한도 또는 동시 건수 초과</span>
                  </div>
                  {result.not_selected.map((item) => (
                    <ResultBidRow key={item.bid_id} item={item} category="not_selected" />
                  ))}
                </div>
              )}

              {/* NO-GO */}
              {result.no_go_list.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-sm font-semibold text-red-600">
                      GO 판정 제외 ({result.no_go_list.length}건)
                    </span>
                  </div>
                  {result.no_go_list.map((item) => (
                    <ResultBidRow key={item.bid_id} item={item} category="no_go" />
                  ))}
                </div>
              )}

              {/* 투찰 일정 */}
              {result.schedule.length > 0 && (
                <Card>
                  <CardHeader className="pb-2 pt-4 px-4">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <CalendarDays className="h-4 w-4 text-blue-500" />
                      날짜별 투찰 일정
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <div className="space-y-2">
                      {result.schedule.map((s, i) => (
                        <div key={i} className="flex items-center gap-3 text-sm">
                          <span className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded shrink-0">{s.date}</span>
                          <span className="text-muted-foreground">{s.bids.length}건 예정</span>
                          {s.note && <span className="text-xs text-blue-600">{s.note}</span>}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
