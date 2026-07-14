import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  ArrowLeft, Plus, Trash2, Users, CheckCircle2, XCircle, AlertCircle, Building2,
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
    <div className="flex flex-col min-h-full bg-slate-50">
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  )

  return (
    <div className="flex flex-col min-h-full bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            className="gap-1.5 text-slate-500 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            공고 상세로
          </Button>
          <div className="h-4 w-px bg-slate-200" />
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Users className="h-5 w-5 text-blue-600" />
              공동도급 적격심사 시뮬레이터
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">파트너 구성에 따른 적격심사 통과 여부를 실시간으로 확인</p>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-5xl mx-auto w-full space-y-5">
        {/* 공고 요약 카드 */}
        {bid && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <div className="bg-blue-50 rounded-lg p-2 shrink-0">
                  <Building2 className="h-5 w-5 text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{bid.title}</p>
                  <div className="flex flex-wrap gap-4 mt-1.5">
                    <span className="text-xs text-slate-500">
                      기초금액 <span className="font-semibold text-slate-700">{fmtAmt(bid.base_amount)}</span>
                    </span>
                    <span className="text-xs text-slate-500">
                      낙찰하한율 <span className="font-semibold text-slate-700">
                        {bid.min_bid_rate ? `${(bid.min_bid_rate * 100).toFixed(4)}%` : '-'}
                      </span>
                    </span>
                    <span className="text-xs text-slate-500">
                      발주기관 <span className="font-semibold text-slate-700">{bid.agency_name}</span>
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 파트너 구성 패널 */}
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="border-b border-slate-100 pb-3">
              <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-1.5">
                <Users className="h-4 w-4 text-blue-600" />
                파트너 구성
              </CardTitle>
            </CardHeader>
            <CardContent className="p-5 space-y-3">
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
                'flex items-center justify-between rounded-lg px-3 py-2.5 text-sm border',
                rateValid
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                  : 'bg-red-50 border-red-200 text-red-600',
              )}>
                <span className="font-medium">지분율 합계</span>
                <span className="font-mono font-bold">{totalRate.toFixed(1)}%</span>
              </div>
              {!rateValid && (
                <p className="text-xs text-red-600 flex items-center gap-1 px-1">
                  <AlertCircle className="h-3 w-3" />
                  지분율 합계가 100%여야 합니다
                </p>
              )}

              <Button
                variant="outline"
                size="sm"
                className="w-full gap-1.5 border-slate-200 text-slate-600 hover:border-blue-200 hover:text-blue-600"
                onClick={() => setSearchOpen(true)}
              >
                <Plus className="h-4 w-4" />
                파트너 추가
              </Button>

              <Button
                size="sm"
                className="w-full bg-blue-600 hover:bg-blue-700"
                disabled={!rateValid || mutation.isPending}
                onClick={runSimulate}
              >
                {mutation.isPending ? '계산 중...' : '심사 시뮬레이션 실행'}
              </Button>
            </CardContent>
          </Card>

          {/* 결과 패널 */}
          <SimResultPanel result={simResult} loading={mutation.isPending} />
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
                className="border-slate-200 focus:border-blue-400"
              />
              {searching && (
                <p className="text-xs text-slate-500 px-1">검색 중...</p>
              )}
              {searchResults && (
                <div className="border border-slate-200 rounded-lg max-h-72 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-50/70">
                        <TableHead className="text-slate-500">업체명</TableHead>
                        <TableHead className="text-slate-500">사업자번호</TableHead>
                        <TableHead className="text-right text-slate-500">낙찰률</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(searchResults.items ?? []).map((c) => (
                        <TableRow
                          key={c.id}
                          className="cursor-pointer hover:bg-blue-50/30 transition-colors"
                          onClick={() => addCompetitor(c)}
                        >
                          <TableCell className="text-sm font-medium text-slate-700">{c.name}</TableCell>
                          <TableCell className="text-sm text-slate-500">{c.aggression_score?.toFixed(2) ?? '-'}</TableCell>
                          <TableCell className="text-right text-sm text-slate-600">{(c.win_rate * 100).toFixed(1)}%</TableCell>
                          <TableCell>
                            <div className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-50 hover:bg-blue-100 transition-colors">
                              <Plus className="h-3.5 w-3.5 text-blue-600" />
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                      {(searchResults.items ?? []).length === 0 && (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center text-sm text-slate-500 py-8">
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
  const isUser = partner.type === 'user'
  return (
    <div className={cn(
      'rounded-xl p-4 space-y-3 border transition-all',
      isUser
        ? 'bg-blue-50/30 border-blue-200'
        : 'bg-slate-50/50 border-slate-200',
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={cn(
            'rounded-full w-2 h-2 shrink-0',
            isUser ? 'bg-blue-500' : 'bg-slate-400',
          )} />
          <span className="text-sm font-semibold text-slate-800">{partner.name}</span>
          {isUser && (
            <Badge className="bg-blue-100 text-blue-700 border-blue-200 text-xs">귀사</Badge>
          )}
        </div>
        {onRemove && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-slate-500 hover:text-red-500 hover:bg-red-50"
            onClick={onRemove}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {partner.type === 'user' && (
        <div className="space-y-1.5">
          <Label className="text-sm font-medium text-slate-500">보유 실적 (억원)</Label>
          <Input
            type="number"
            min={0}
            step={0.1}
            placeholder="0"
            value={partner.user_track === 0 ? '' : partner.user_track}
            onChange={(e) => onTrackChange(parseFloat(e.target.value) || 0)}
            className="h-8 text-sm border-slate-200 focus:border-blue-400 bg-white"
          />
        </div>
      )}

      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <Label className="text-sm font-medium text-slate-500">지분율</Label>
          <span className={cn(
            'text-sm font-bold font-mono',
            isUser ? 'text-blue-600' : 'text-slate-700',
          )}>
            {partner.participation_rate.toFixed(1)}%
          </span>
        </div>
        {/* 커스텀 슬라이더 */}
        <div className="relative">
          <input
            type="range"
            min={10}
            max={90}
            step={1}
            value={partner.participation_rate}
            onChange={(e) => onRateChange(Number(e.target.value))}
            className={cn(
              'w-full h-2 rounded-full appearance-none cursor-pointer',
              isUser ? 'accent-blue-600' : 'accent-slate-500',
            )}
            style={{
              background: `linear-gradient(to right, ${isUser ? '#2563eb' : '#64748b'} 0%, ${isUser ? '#2563eb' : '#64748b'} ${((partner.participation_rate - 10) / 80) * 100}%, #e2e8f0 ${((partner.participation_rate - 10) / 80) * 100}%, #e2e8f0 100%)`,
            }}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-300">
          <span>10%</span>
          <span>90%</span>
        </div>
      </div>
    </div>
  )
}

// ── 결과 패널 컴포넌트 ───────────────────────────────────────────

function SimResultPanel({ result, loading }: { result: JointSimResponse | null; loading: boolean }) {
  if (loading) return (
    <Card className="bg-white border-slate-200 shadow-sm">
      <CardContent className="p-5 space-y-3">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </CardContent>
    </Card>
  )

  if (!result) return (
    <Card className="bg-white border-slate-200 shadow-sm">
      <CardContent className="flex flex-col items-center justify-center h-full min-h-[300px] gap-3">
        <div className="bg-slate-100 rounded-full p-4">
          <AlertCircle className="h-8 w-8 text-slate-300" />
        </div>
        <p className="text-sm text-slate-500 text-center">
          파트너를 구성하면<br />심사 결과가 표시됩니다
        </p>
      </CardContent>
    </Card>
  )

  const { joint_result, partners, bid_amount_required } = result

  return (
    <Card className="bg-white border-slate-200 shadow-sm">
      <CardHeader className="border-b border-slate-100 pb-3">
        <CardTitle className="text-base font-semibold text-slate-800">심사 결과</CardTitle>
      </CardHeader>
      <CardContent className="p-5 space-y-4">
        {/* 통과/미통과 배너 */}
        <div className={cn(
          'flex items-center gap-3 rounded-xl p-4 border',
          joint_result.passes
            ? 'bg-emerald-50 border-emerald-200'
            : 'bg-red-50 border-red-200',
        )}>
          <div className={cn(
            'rounded-full p-2 shrink-0',
            joint_result.passes ? 'bg-emerald-100' : 'bg-red-100',
          )}>
            {joint_result.passes
              ? <CheckCircle2 className="h-6 w-6 text-emerald-600" />
              : <XCircle className="h-6 w-6 text-red-500" />
            }
          </div>
          <div>
            <p className={cn('font-bold text-lg', joint_result.passes ? 'text-emerald-700' : 'text-red-600')}>
              적격심사 {joint_result.passes ? '통과' : '미통과'}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              합산점수 <span className="font-semibold text-slate-600">{joint_result.total_qual_score}점</span> / 기준 {joint_result.threshold}점
            </p>
          </div>
        </div>

        {/* 점수 진행바 */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-slate-500">
            <span>합산 적격점수</span>
            <span className="font-semibold text-slate-600">{joint_result.total_qual_score} / {joint_result.threshold}</span>
          </div>
          <div className="relative h-3 rounded-full bg-slate-100 overflow-hidden">
            {/* 기준선 */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-slate-300 z-10"
              style={{ left: `${Math.min((joint_result.threshold / Math.max(joint_result.threshold + 10, 1)) * 100, 100)}%` }}
            />
            <div
              className={cn('h-full rounded-full transition-all duration-700', joint_result.passes ? 'bg-emerald-500' : 'bg-red-400')}
              style={{ width: `${Math.min((joint_result.total_qual_score / Math.max(joint_result.threshold, 1)) * 100, 100)}%` }}
            />
          </div>
        </div>

        {/* 투찰금액 정보 */}
        <div className="grid grid-cols-2 gap-3">
          <AmtCard label="최저 투찰금액" value={fmtAmt(joint_result.min_bid_amount)} sub={`${(joint_result.min_bid_rate * 100).toFixed(4)}%`} highlight />
          <AmtCard label="심사 기준금액" value={fmtAmt(bid_amount_required)} sub="기초금액 × 낙찰하한율" />
        </div>

        {/* 개별 파트너 점수 */}
        <div>
          <p className="text-xs font-semibold text-slate-500 mb-2">파트너별 기여점수</p>
          <div className="space-y-1.5">
            {partners.map((p: JointSimPartnerResult, i: number) => (
              <PartnerScoreRow key={i} partner={p} />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AmtCard({ label, value, sub, highlight }: { label: string; value: string; sub: string; highlight?: boolean }) {
  return (
    <div className={cn(
      'rounded-xl p-3.5 space-y-1',
      highlight
        ? 'bg-blue-50 border border-blue-200'
        : 'bg-slate-50 border border-slate-100',
    )}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={cn('text-base font-bold font-mono', highlight ? 'text-blue-700' : 'text-slate-900')}>
        {value}
      </p>
      <p className="text-xs text-slate-500">{sub}</p>
    </div>
  )
}

function PartnerScoreRow({ partner }: { partner: JointSimPartnerResult }) {
  return (
    <div className={cn(
      'flex items-center justify-between text-xs px-3 py-2.5 rounded-lg border transition-colors',
      partner.passes
        ? 'bg-emerald-50/50 border-emerald-100'
        : 'bg-red-50/50 border-red-100',
    )}>
      <div className="flex items-center gap-2">
        {partner.passes
          ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
          : <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
        }
        <span className="font-medium text-slate-700 truncate max-w-[110px]">{partner.name}</span>
        <Badge className="bg-slate-100 text-slate-500 border-slate-200 text-xs px-1.5 py-0 h-4 font-mono">
          {(partner.participation_rate * 100).toFixed(0)}%
        </Badge>
      </div>
      <div className="text-right shrink-0 ml-2">
        <span className="font-mono font-bold text-slate-800">{partner.qual_score}점</span>
        <span className="text-slate-500 ml-1">/ {fmtAmt(partner.track_amount)} 실적</span>
      </div>
    </div>
  )
}
