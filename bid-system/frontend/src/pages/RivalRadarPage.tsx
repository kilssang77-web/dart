import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Trophy, Users, TrendingUp, Radar as RadarIcon, Building2, BarChart3 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { bidsApi } from '@/api'
import type { RivalRadarResponse } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

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
    <div className="min-h-screen bg-slate-50 p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-8 w-20 rounded-lg" />
        <Skeleton className="h-8 w-64 rounded-lg" />
      </div>
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  )

  if (!data) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500">데이터 없음</div>
  )

  const chartData = data.rivals.slice(0, 10).map((r, i) => ({
    name: r.company_name.slice(0, 8),
    count: r.co_bid_count,
    avg_rate: r.avg_bid_rate ? +(r.avg_bid_rate * 100).toFixed(3) : 0,
    idx: i,
  }))

  const rankColors = ['#7c3aed', '#8b5cf6', '#a78bfa', '#c4b5fd']

  return (
    <div className="min-h-screen bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="gap-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100"
            >
              <ArrowLeft className="h-4 w-4" /> 돌아가기
            </Button>
            <div className="w-px h-5 bg-slate-200" />
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
                <RadarIcon className="h-5 w-5 text-purple-600" />
                경쟁 레이더
              </h1>
              <p className="text-sm text-slate-500 mt-0.5">
                공고번호 <span className="font-mono text-slate-700">{data.announcement_no}</span> — 동반입찰 경쟁사 분석
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-5">
        {/* KPI 스탯 카드 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="전체 참여사"
            value={String(data.total_participants)}
            sub="개사"
            icon={Users}
            color="blue"
          />
          <StatCard
            label="낙찰사"
            value={data.winner_company ?? '-'}
            sub="낙찰 업체"
            icon={Trophy}
            color="amber"
          />
          <StatCard
            label="낙찰률"
            value={data.winner_rate ? (data.winner_rate * 100).toFixed(3) + '%' : '-'}
            sub="낙찰 투찰률"
            icon={TrendingUp}
            color="emerald"
          />
          <StatCard
            label="분석된 경쟁사"
            value={String(data.rivals.length)}
            sub="동반입찰 업체"
            icon={BarChart3}
            color="purple"
          />
        </div>

        {/* 이번 공고 참여자 */}
        {data.current_participants.length > 0 && (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                <div className="rounded-lg p-1.5 bg-blue-50">
                  <Users className="h-4 w-4 text-blue-600" />
                </div>
                이번 공고 참여자
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead className="w-14 text-sm text-slate-500 px-5">순위</TableHead>
                    <TableHead className="text-sm text-slate-500">업체명</TableHead>
                    <TableHead className="text-right text-sm text-slate-500">투찰율</TableHead>
                    <TableHead className="text-center text-sm text-slate-500 pr-5">결과</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.current_participants.map((p) => (
                    <TableRow
                      key={p.rank}
                      className={cn(
                        'transition-colors',
                        p.is_winner
                          ? 'bg-amber-50/60 hover:bg-amber-50'
                          : 'hover:bg-slate-50'
                      )}
                    >
                      <TableCell className="px-5">
                        <span className={cn(
                          'inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold',
                          p.rank === 1 ? 'bg-amber-100 text-amber-700' :
                          p.rank === 2 ? 'bg-slate-100 text-slate-700' :
                          p.rank === 3 ? 'bg-orange-100 text-orange-700' :
                          'text-slate-500 bg-transparent'
                        )}>
                          {p.rank}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {p.is_winner && <Trophy className="h-3.5 w-3.5 text-amber-500 shrink-0" />}
                          <span className={cn('text-sm', p.is_winner ? 'font-bold text-slate-900' : 'font-medium text-slate-700')}>
                            {p.company_name}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className={cn(
                          'font-mono text-sm font-semibold tabular-nums',
                          p.is_winner ? 'text-amber-700' : 'text-slate-600'
                        )}>
                          {p.bid_rate != null ? (p.bid_rate * 100).toFixed(3) + '%' : '-'}
                        </span>
                      </TableCell>
                      <TableCell className="text-center pr-5">
                        {p.is_winner && (
                          <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200 font-semibold gap-1">
                            <Trophy className="h-2.5 w-2.5" />낙찰
                          </span>
                        )}
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
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardHeader className="pb-2 pt-4 px-5">
              <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                <div className="rounded-lg p-1.5 bg-purple-50">
                  <TrendingUp className="h-4 w-4 text-purple-600" />
                </div>
                동반입찰 빈도 상위 10사
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-5">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#475569' }} angle={-30} textAnchor="end" />
                  <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                  <Tooltip
                    contentStyle={{ border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                    formatter={(v: number) => [v + '건', '동반 횟수']}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={rankColors[Math.min(i, rankColors.length - 1)]}
                        fillOpacity={1 - i * 0.06}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* 경쟁사 상세 테이블 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-2 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <div className="rounded-lg p-1.5 bg-slate-100">
                <Building2 className="h-4 w-4 text-slate-600" />
              </div>
              경쟁사 레이더 목록
              <span className="ml-1 text-xs font-normal text-slate-500">— {data.rivals.length}개사</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="w-12 text-sm text-slate-500 px-5">순위</TableHead>
                  <TableHead className="text-sm text-slate-500">업체명</TableHead>
                  <TableHead className="text-right text-sm text-slate-500">동반입찰</TableHead>
                  <TableHead className="text-right text-sm text-slate-500">평균 투찰율</TableHead>
                  <TableHead className="text-right text-sm text-slate-500 pr-5">낙찰 횟수</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rivals.map((r, i) => (
                  <TableRow key={i} className="hover:bg-slate-50 transition-colors group">
                    <TableCell className="px-5">
                      <span className={cn(
                        'inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold',
                        i === 0 ? 'bg-purple-100 text-purple-700' :
                        i === 1 ? 'bg-purple-50 text-purple-600' :
                        i === 2 ? 'bg-slate-100 text-slate-600' :
                        'text-slate-500'
                      )}>
                        {i + 1}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="font-semibold text-sm text-slate-800 group-hover:text-purple-700 transition-colors">
                        {r.company_name}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="text-sm font-semibold text-slate-700 tabular-nums">{r.co_bid_count}</span>
                      <span className="text-xs text-slate-500 ml-0.5">건</span>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm text-slate-600 tabular-nums">
                      {r.avg_bid_rate != null ? (r.avg_bid_rate * 100).toFixed(3) + '%' : '-'}
                    </TableCell>
                    <TableCell className="text-right pr-5">
                      {r.win_count > 0 ? (
                        <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-semibold gap-1">
                          <Trophy className="h-2.5 w-2.5" />{r.win_count}회
                        </span>
                      ) : (
                        <span className="text-slate-300 text-xs">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

const colorMap = {
  blue:    { bar: 'bg-blue-500',    icon: 'bg-blue-50',    iconText: 'text-blue-600' },
  amber:   { bar: 'bg-amber-400',   icon: 'bg-amber-50',   iconText: 'text-amber-600' },
  emerald: { bar: 'bg-emerald-500', icon: 'bg-emerald-50', iconText: 'text-emerald-600' },
  purple:  { bar: 'bg-purple-500',  icon: 'bg-purple-50',  iconText: 'text-purple-600' },
}

function StatCard({
  label, value, sub, icon: Icon, color,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ComponentType<{ className?: string }>
  color: keyof typeof colorMap
}) {
  const c = colorMap[color]
  return (
    <Card className="relative overflow-hidden bg-white border-slate-200 shadow-sm hover:shadow-md transition-shadow">
      <div className={cn('absolute top-0 left-0 right-0 h-0.5', c.bar)} />
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className="text-xl font-bold mt-1 text-slate-900 truncate tabular-nums">{value}</p>
            {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
          </div>
          <div className={cn('rounded-xl p-2.5 shrink-0 ml-3', c.icon)}>
            <Icon className={cn('h-5 w-5', c.iconText)} />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
