import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Trophy, ExternalLink, Sparkles } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { bidsApi } from '@/api'
import type { BidDetail, BidResultItem, MetaData } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'

export default function BidDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const { data: bid, isLoading } = useQuery<BidDetail>({
    queryKey: ['bid', id],
    queryFn: () => bidsApi.detail(Number(id)),
    enabled: !!id,
  })

  const { data: similar } = useQuery<unknown[]>({
    queryKey: ['similar', id],
    queryFn: () => bidsApi.similar(Number(id), 6),
    enabled: !!id,
  })

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })

  if (isLoading) return (
    <div className="p-6 space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
  if (!bid) return (
    <div className="p-6 text-destructive">데이터를 찾을 수 없습니다.</div>
  )

  const chartData = bid.results
    ?.sort((a: BidResultItem, b: BidResultItem) => a.bid_rate - b.bid_rate)
    .map((r: BidResultItem) => ({ name: r.competitor_name.slice(0,6), rate: +(r.bid_rate * 100).toFixed(2), winner: r.is_winner }))

  const similarList = (similar ?? []) as Array<{
    bid_id: number; title: string; agency_name: string
    base_amount: number; winner_rate: number | null
    competitor_count: number; similarity_score: number
  }>

  function handleRecommend() { navigate(`/recommend?bid_id=${id}`) }

  const fmtDate = (v: string | null | undefined) =>
    v ? new Date(v).toLocaleDateString('ko-KR') : '-'
  const fmtAmt = (v: number | null | undefined) =>
    v ? `${(v / 1e8).toFixed(1)}억원` : '-'

  return (
    <div className="p-6 space-y-5">
      {/* 상단 버튼 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> 목록으로
        </Button>
        <div className="flex items-center gap-2">
          <Button onClick={handleRecommend} size="sm" className="gap-1.5">
            <Sparkles className="h-4 w-4" /> AI 투찰률 추천
          </Button>
          {bid.ntce_url && (
            <Button variant="outline" size="sm" asChild>
              <a href={bid.ntce_url} target="_blank" rel="noopener noreferrer" className="gap-1.5">
                <ExternalLink className="h-4 w-4" /> 조달청 원문 보기
              </a>
            </Button>
          )}
        </div>
      </div>

      {/* 기본 정보 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{bid.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <button
              className="block text-left w-full"
              onClick={() => {
                const ag = meta?.agencies.find((a) => a.name === bid.agency_name)
                if (ag) navigate(`/agencies/${ag.id}`)
              }}
            >
              <InfoBox label="발주기관"    value={bid.agency_name} />
            </button>
            <InfoBox label="지역"        value={bid.region_name ?? '-'} />
            <InfoBox label="공종"        value={bid.industry_name ?? '-'} />
            <InfoBox label="기초금액"    value={`${(bid.base_amount / 1e8).toFixed(1)}억원`} />
            <InfoBox label="예정가격"    value={fmtAmt(bid.estimated_price)} />
            <InfoBox label="낙찰하한율"  value={bid.min_bid_rate ? `${(bid.min_bid_rate * 100).toFixed(2)}%` : '-'} />
            <InfoBox label="A값"         value={bid.a_value ? `${(bid.a_value / 1e8).toFixed(1)}억원` : '-'} />
            <InfoBox label="공사기간"    value={bid.construction_period ? `${bid.construction_period}일` : '-'} />
            <InfoBox label="공고일"      value={fmtDate(bid.notice_date)} />
            <InfoBox label="입찰마감일"  value={fmtDate(bid.bid_close_date)} />
            <InfoBox label="개찰일"      value={fmtDate(bid.bid_open_date)} />
            <InfoBox label="낙찰률"      value={bid.winner_rate ? `${(bid.winner_rate * 100).toFixed(2)}%` : '-'} highlight />
            <InfoBox label="경쟁사 수"   value={`${bid.competitor_count}개사`} />
            <InfoBox label="상태"        value={bid.status === 'open' ? '공고중' : '개찰완료'} />
          </div>

          {(bid.construction_site || bid.contract_method || bid.bid_method ||
            bid.eligible_regions || bid.industry_limit || bid.contact_name) && (
            <div className="border-t pt-4">
              <p className="text-xs font-semibold text-muted-foreground uppercase mb-3">상세 정보</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {bid.contract_method && <InfoBox label="계약방법" value={bid.contract_method} />}
                {bid.bid_method && <InfoBox label="입찰방법" value={bid.bid_method} />}
                {bid.construction_site && <InfoBox label="공사현장" value={bid.construction_site} />}
                {bid.eligible_regions && <InfoBox label="참가가능지역" value={bid.eligible_regions} />}
                {bid.industry_limit && <InfoBox label="업종제한" value={bid.industry_limit} />}
                {bid.contact_name && (
                  <InfoBox label="담당자"
                    value={bid.contact_name + (bid.contact_tel ? ` (${bid.contact_tel})` : '')} />
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 투찰률 분포 */}
      {chartData && chartData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">투찰률 분포</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} margin={{ bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" />
                <YAxis domain={['auto','auto']} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip formatter={(v: number) => [v + '%', '투찰률']} />
                <Bar dataKey="rate" radius={[3,3,0,0]}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={d.winner ? '#ef4444' : 'hsl(var(--primary)/0.4)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-muted-foreground mt-1">
              <span className="inline-block w-3 h-3 bg-red-400 mr-1 rounded-sm align-middle"></span>낙찰
            </p>
          </CardContent>
        </Card>
      )}

      {/* 참여업체 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">
            참여업체 현황 ({bid.competitor_count}개사)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>순위</TableHead>
                <TableHead>업체명</TableHead>
                <TableHead className="text-right">투찰금액</TableHead>
                <TableHead className="text-right">투찰률</TableHead>
                <TableHead className="text-center">낙찰</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bid.results?.map((r: BidResultItem) => (
                <TableRow key={r.id} className={cn(r.is_winner && 'bg-red-50/50 font-semibold')}>
                  <TableCell>{r.rank}</TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1.5">
                      {r.is_winner && <Trophy className="h-3.5 w-3.5 text-yellow-500" />}
                      {r.competitor_name}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">{(r.bid_amount / 1e8).toFixed(2)}억</TableCell>
                  <TableCell className="text-right font-mono">{(r.bid_rate * 100).toFixed(2)}%</TableCell>
                  <TableCell className="text-center">
                    {r.is_winner && <Badge variant="success" className="text-[10px] px-1.5 py-0">낙찰</Badge>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 유사 사례 */}
      {similarList.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">유사 입찰 사례</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {similarList.map((s) => (
              <div
                key={s.bid_id}
                className="flex items-center justify-between p-3 rounded-lg bg-muted/40 hover:bg-accent cursor-pointer transition-colors"
                onClick={() => navigate(`/bids/${s.bid_id}`)}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate max-w-xs">{s.title}</p>
                  <p className="text-xs text-muted-foreground">{s.agency_name} · {s.competitor_count}개사</p>
                </div>
                <div className="text-right shrink-0 ml-4">
                  <p className="text-sm font-mono font-semibold text-primary">
                    {s.winner_rate ? (s.winner_rate * 100).toFixed(2) + '%' : '-'}
                  </p>
                  <p className="text-xs text-muted-foreground">유사도 {(s.similarity_score * 100).toFixed(0)}%</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function InfoBox({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-muted/50 rounded-md p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('text-sm font-semibold mt-0.5', highlight ? 'text-primary text-base' : 'text-foreground')}>{value}</div>
    </div>
  )
}