import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Trophy, Users, TrendingUp } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { bidsApi } from '@/api'
import type { RivalRadarResponse } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export default function RivalRadarPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [topK] = useState(15)

  const { data, isLoading } = useQuery<RivalRadarResponse>({
    queryKey: ['rival-radar', id],
    queryFn: () => bidsApi.rivalRadar(Number(id), topK),
    enabled: !!id,
    staleTime: 300_000,
  })

  if (isLoading) return (
    <div className="p-6 space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-64 w-full" />
    </div>
  )

  if (!data) return <div className="p-6 text-muted-foreground">데이터 없음</div>

  const chartData = data.rivals.slice(0, 10).map((r) => ({
    name: r.company_name.slice(0, 8),
    count: r.co_bid_count,
    avg_rate: r.avg_bid_rate ? +(r.avg_bid_rate * 100).toFixed(3) : 0,
  }))

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> 돌아가기
        </Button>
        <div>
          <h1 className="text-lg font-bold">경쟁 레이더</h1>
          <p className="text-xs text-muted-foreground">공고번호 {data.announcement_no} — 동반입찰 경쟁사 분석</p>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="전체 참여사" value={data.total_participants} />
        <StatCard label="낙찰사" value={data.winner_company ?? '-'} />
        <StatCard label="낙찰율" value={data.winner_rate ? (data.winner_rate * 100).toFixed(3) + '%' : '-'} />
        <StatCard label="분석된 경쟁사" value={data.rivals.length} />
      </div>

      {/* 이번 공고 참여자 */}
      {data.current_participants.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Users className="h-4 w-4" /> 이번 공고 참여자
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>순위</TableHead>
                  <TableHead>업체명</TableHead>
                  <TableHead className="text-right">투찰율</TableHead>
                  <TableHead className="text-center">결과</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.current_participants.map((p) => (
                  <TableRow key={p.rank} className={p.is_winner ? 'bg-red-50/50 font-semibold' : ''}>
                    <TableCell>{p.rank}</TableCell>
                    <TableCell className="flex items-center gap-1.5">
                      {p.is_winner && <Trophy className="h-3.5 w-3.5 text-yellow-500" />}
                      {p.company_name}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {p.bid_rate != null ? (p.bid_rate * 100).toFixed(3) + '%' : '-'}
                    </TableCell>
                    <TableCell className="text-center">
                      {p.is_winner && <Badge variant="success" className="text-[10px]">낙찰</Badge>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* 동반입찰 빈도 차트 */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <TrendingUp className="h-4 w-4" /> 동반입찰 빈도 상위 10사
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} margin={{ bottom: 30 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v: number) => [v + '건', '동반 횟수']} />
                <Bar dataKey="count" fill="hsl(var(--primary)/0.7)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* 경쟁사 상세 테이블 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">경쟁사 레이더 목록</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>업체명</TableHead>
                <TableHead className="text-right">동반입찰</TableHead>
                <TableHead className="text-right">평균 투찰율</TableHead>
                <TableHead className="text-right">낙찰 횟수</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rivals.map((r, i) => (
                <TableRow key={i}>
                  <TableCell className="text-muted-foreground text-xs">{i + 1}</TableCell>
                  <TableCell className="font-medium">{r.company_name}</TableCell>
                  <TableCell className="text-right">{r.co_bid_count}건</TableCell>
                  <TableCell className="text-right font-mono">
                    {r.avg_bid_rate != null ? (r.avg_bid_rate * 100).toFixed(3) + '%' : '-'}
                  </TableCell>
                  <TableCell className="text-right">
                    {r.win_count > 0
                      ? <Badge variant="outline" className="text-[10px]">{r.win_count}회</Badge>
                      : <span className="text-muted-foreground text-xs">-</span>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-muted/50 rounded-md p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold mt-0.5 truncate">{value}</div>
    </div>
  )
}
