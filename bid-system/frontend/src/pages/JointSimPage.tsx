import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  ArrowLeft, Plus, Trash2, Users, CheckCircle2, XCircle, AlertCircle,
} from 'lucide-react'
import { bidsApi, competitorsApi } from '@/api'
import type { BidDetail, JointSimResponse, JointSimPartnerResult, Competitor } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

interface PartnerInput {
  key:               number
  type:              'user' | 'competitor'
  competitor_id?:    number
  name:              string
  user_track:        number
  participation_rate: number
}

let _keySeq = 0
function nextKey() { return ++_keySeq }

function fmtAmt(v: number) {
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}억원`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}만원`
  return `${v.toLocaleString()}원`
}

export default function JointSimPage() {
  const { id: bidId } = useParams()
  const navigate = useNavigate()

  const { data: bid, isLoading: bidLoading } = useQuery<BidDetail>({
    queryKey: ['bid', bidId],
    queryFn:  () => bidsApi.detail(Number(bidId)),
    enabled:  !!bidId,
  })

  const [partners, setPartners] = useState<PartnerInput[]>([
    { key: nextKey(), type: 'user', name: '귀사', user_track: 0, participation_rate: 60 },
  ])
  const [searchOpen,   setSearchOpen]   = useState(false)
  const [searchKw,     setSearchKw]     = useState('')
  const [simResult,    setSimResult]    = useState<JointSimResponse | null>(null)

  const { data: searchResults, isLoading: searching } = useQuery<{ items: Competitor[] }>({
    queryKey: ['competitor-search', searchKw],
    queryFn:  () => competitorsApi.list({ keyword: searchKw, size: 30 }),
    enabled:  searchOpen && searchKw.length >= 1,
    staleTime: 10_000,
  })

  const mutation = useMutation({
    mutationFn: (req: { partners: Array<{ competitor_id?: number; user_track?: number; participation_rate: number }> }) =>
      bidsApi.jointSimulate(Number(bidId), { partners: req.partners }),
    onSuccess: (data) => setSimResult(data),
  })

  const totalRate = partners.reduce((s, p) => s + p.participation_rate, 0)
  const rateValid = Math.abs(totalRate - 100) < 0.5

  const runSimulate = useCallback(() => {
    if (!bidId || !rateValid) return
    mutation.mutate({
      partners: partners.map((p) => ({
        competitor_id:      p.type === 'competitor' ? p.competitor_id : undefined,
        user_track:         p.type === 'user' ? p.user_track * 1e8 : undefined,
        participation_rate: p.participation_rate / 100,
      })),
    })
  }, [partners, bidId, rateValid, mutation])

  // 파트너 변경 시 자동 계산 (debounce 500ms)
  useEffect(() => {
    if (!rateValid) { setSimResult(null); return }
    const t = setTimeout(runSimulate, 500)
    return () => clearTimeout(t)
  }, [partners, rateValid]) // eslint-disable-line react-hooks/exhaustive-deps

  function addCompetitor(c: Competitor) {
    // 이미 추가된 경쟁사 중복 방지
    if (partners.some((p) => p.competitor_id === c.id)) return
    setPartners((prev) => {
      const remaining = Math.max(0, 100 - prev.reduce((s, p) => s + p.participation_rate, 0))
      return [
        ...prev,
        {
          key:               nextKey(),
          type:              'competitor',
          competitor_id:     c.id,
          name:              c.name,
          user_track:        0,
          participation_rate: Math.min(remaining, 40),
        },
      ]
    })
    setSearchOpen(false)
    setSearchKw('')
  }

  function removePartner(key: number) {
    setPartners((prev) => prev.filter((p) => p.key !== key))
  }

  function updateRate(key: number, val: number) {
    setPartners((prev) =>
      prev.map((p) => (p.key === key ? { ...p, participation_rate: val } : p)),
    )
  }

  function updateTrack(key: number, val: number) {
    setPartners((prev) =>
      prev.map((p) => (p.key === key ? { ...p, user_track: val } : p)),
    )
  }

  if (bidLoading) return (
    <div className="p-6 space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-40 w-full" />
    </div>
  )

  return (
    <div className="p-6 space-y-5 max-w-5xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> 공고 상세로
        </Button>
        <span className="text-sm text-muted-foreground">공동도급 적격심사 시뮬레이터</span>
      </div>

      {/* 공고 요약 */}
      {bid && (
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="font-semibold text-sm truncate">{bid.title}</p>
            <div className="flex flex-wrap gap-4 mt-2 text-xs text-muted-foreground">
              <span>기초금액 <b className="text-foreground">{fmtAmt(bid.base_amount)}</b></span>
              <span>낙찰하한율 <b className="text-foreground">{bid.min_bid_rate ? `${(bid.min_bid_rate * 100).toFixed(2)}%` : '-'}</b></span>
              <span>발주처 <b className="text-foreground">{bid.agency_name}</b></span>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* 파트너 구성 패널 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <Users className="h-4 w-4" /> 파트너 구성
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {partners.map((p) => (
              <PartnerRow
                key={p.key}
                partner={p}
                onRateChange={(v) => updateRate(p.key, v)}
                onTrackChange={(v) => updateTrack(p.key, v)}
                onRemove={p.type === 'user' ? undefined : () => removePartner(p.key)}
              />
            ))}

            {/* 지분율 합계 표시 */}
            <div className={cn(
              'flex items-center justify-between text-xs px-1',
              rateValid ? 'text-green-600' : 'text-destructive',
            )}>
              <span>지분율 합계</span>
              <span className="font-mono font-semibold">{totalRate.toFixed(1)}%</span>
            </div>
            {!rateValid && (
              <p className="text-xs text-destructive flex items-center gap-1">
                <AlertCircle className="h-3 w-3" /> 지분율 합계가 100%여야 합니다
              </p>
            )}

            <Button
              variant="outline"
              size="sm"
              className="w-full gap-1.5"
              onClick={() => setSearchOpen(true)}
            >
              <Plus className="h-4 w-4" /> 파트너 추가
            </Button>

            <Button
              size="sm"
              className="w-full"
              disabled={!rateValid || mutation.isPending}
              onClick={runSimulate}
            >
              {mutation.isPending ? '계산 중…' : '심사 시뮬레이션'}
            </Button>
          </CardContent>
        </Card>

        {/* 결과 패널 */}
        <ResultPanel result={simResult} loading={mutation.isPending} />
      </div>

      {/* 파트너 검색 다이얼로그 */}
      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>경쟁사 검색</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="업체명 또는 사업자번호"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              autoFocus
            />
            {searching && <p className="text-xs text-muted-foreground">검색 중…</p>}
            {searchResults && (
              <div className="border rounded-md max-h-72 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>업체명</TableHead>
                      <TableHead>사업자번호</TableHead>
                      <TableHead className="text-right">낙찰률</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(searchResults.items ?? []).map((c) => (
                      <TableRow key={c.id} className="cursor-pointer hover:bg-muted/50" onClick={() => addCompetitor(c)}>
                        <TableCell className="text-sm">{c.name}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{c.aggression_score?.toFixed(2) ?? '-'}</TableCell>
                        <TableCell className="text-right text-xs">{(c.win_rate * 100).toFixed(1)}%</TableCell>
                        <TableCell>
                          <Plus className="h-3.5 w-3.5 text-muted-foreground" />
                        </TableCell>
                      </TableRow>
                    ))}
                    {(searchResults.items ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={4} className="text-center text-xs text-muted-foreground py-6">
                          검색 결과 없음
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── 파트너 행 컴포넌트 ────────────────────────────────────────────

interface PartnerRowProps {
  partner:        PartnerInput
  onRateChange:   (v: number) => void
  onTrackChange:  (v: number) => void
  onRemove?:      () => void
}

function PartnerRow({ partner, onRateChange, onTrackChange, onRemove }: PartnerRowProps) {
  return (
    <div className="border rounded-lg p-3 space-y-2 bg-muted/20">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{partner.name}</span>
        {onRemove && (
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onRemove}>
            <Trash2 className="h-3.5 w-3.5 text-destructive" />
          </Button>
        )}
      </div>
      {partner.type === 'user' && (
        <div className="space-y-1">
          <Label className="text-xs">보유 실적 (억원)</Label>
          <Input
            type="number"
            min={0}
            step={0.1}
            placeholder="0"
            value={partner.user_track === 0 ? '' : partner.user_track}
            onChange={(e) => onTrackChange(parseFloat(e.target.value) || 0)}
            className="h-7 text-sm"
          />
        </div>
      )}
      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <Label className="text-xs">지분율</Label>
          <span className="font-mono">{partner.participation_rate.toFixed(1)}%</span>
        </div>
        <input
          type="range"
          min={10}
          max={90}
          step={1}
          value={partner.participation_rate}
          onChange={(e) => onRateChange(Number(e.target.value))}
          className="w-full accent-primary"
        />
      </div>
    </div>
  )
}

// ── 결과 패널 컴포넌트 ───────────────────────────────────────────

function ResultPanel({ result, loading }: { result: JointSimResponse | null; loading: boolean }) {
  if (loading) return (
    <Card>
      <CardContent className="pt-4 space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </CardContent>
    </Card>
  )

  if (!result) return (
    <Card>
      <CardContent className="pt-6 flex flex-col items-center justify-center h-full min-h-[240px] text-muted-foreground text-sm gap-2">
        <AlertCircle className="h-8 w-8 opacity-40" />
        <p>파트너를 구성하면 심사 결과가 표시됩니다</p>
      </CardContent>
    </Card>
  )

  const { joint_result, partners, bid_amount_required } = result

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">심사 결과</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 통과/미통과 배지 */}
        <div className={cn(
          'flex items-center gap-2 rounded-lg p-3',
          joint_result.passes ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200',
        )}>
          {joint_result.passes
            ? <CheckCircle2 className="h-6 w-6 text-green-600 shrink-0" />
            : <XCircle     className="h-6 w-6 text-red-500 shrink-0" />
          }
          <div>
            <p className={cn('font-semibold', joint_result.passes ? 'text-green-700' : 'text-red-600')}>
              {joint_result.passes ? '적격심사 통과' : '적격심사 미통과'}
            </p>
            <p className="text-xs text-muted-foreground">
              합산점수 {joint_result.total_qual_score}점 / 기준 {joint_result.threshold}점
            </p>
          </div>
        </div>

        {/* 점수 진행바 */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>합산 적격점수</span>
            <span>{joint_result.total_qual_score} / {joint_result.threshold}</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all', joint_result.passes ? 'bg-green-500' : 'bg-red-400')}
              style={{ width: `${Math.min((joint_result.total_qual_score / Math.max(joint_result.threshold, 1)) * 100, 100)}%` }}
            />
          </div>
        </div>

        {/* 투찰금액 정보 */}
        <div className="grid grid-cols-2 gap-3">
          <AmtCard label="최저 투찰금액"  value={fmtAmt(joint_result.min_bid_amount)} sub={`${(joint_result.min_bid_rate * 100).toFixed(2)}%`} />
          <AmtCard label="심사 기준금액"  value={fmtAmt(bid_amount_required)}          sub="기초금액 × 낙찰하한율" />
        </div>

        {/* 개별 파트너 점수 */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground mb-2">파트너별 기여점수</p>
          <div className="space-y-1">
            {partners.map((p: JointSimPartnerResult, i: number) => (
              <PartnerScoreRow key={i} partner={p} />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AmtCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="border rounded-lg p-2.5 space-y-0.5">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold">{value}</p>
      <p className="text-[10px] text-muted-foreground">{sub}</p>
    </div>
  )
}

function PartnerScoreRow({ partner }: { partner: JointSimPartnerResult }) {
  return (
    <div className="flex items-center justify-between text-xs py-1 border-b last:border-0">
      <div className="flex items-center gap-1.5">
        {partner.passes
          ? <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
          : <XCircle      className="h-3 w-3 text-red-400 shrink-0" />
        }
        <span className="truncate max-w-[110px]">{partner.name}</span>
        <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
          {(partner.participation_rate * 100).toFixed(0)}%
        </Badge>
      </div>
      <div className="text-right shrink-0 ml-2">
        <span className="font-mono font-semibold">{partner.qual_score}점</span>
        <span className="text-muted-foreground ml-1">/ {fmtAmt(partner.track_amount)} 실적</span>
      </div>
    </div>
  )
}
