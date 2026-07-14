import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Handshake, Search, Shield, TrendingUp, Activity, Award, ChevronDown, ChevronUp, CheckCircle2, XCircle, Zap, Users } from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from 'recharts'
import { competitorsApi, bidsApi } from '@/api'
import type { Competitor, MetaData, JointPartnersResponse } from '@/types'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

/*
 * 공동도급 협정사 궁합 분석
 * 기존 경쟁사 데이터를 기반으로 잠재 협력사를 탐색하고 궁합 점수를 산출
 */

interface CompatScore {
  total: number        // 0~100
  stability: number   // 위험도 기반 (40점)
  performance: number // 낙찰 실적 (25점)
  consistency: number // 일관성 (20점)
  activity: number    // 활동성 (15점)
}

function calcCompat(c: Competitor, myTargetRate: number): CompatScore {
  // 안정성 (40점)
  const stabilityMap: Record<string, number> = { LOW: 40, MEDIUM: 24, HIGH: 8, UNKNOWN: 16 }
  const stability = stabilityMap[c.risk_level] ?? 16

  // 실적 (25점) — win_rate 최대 30%를 기준으로 정규화
  const performance = Math.min(c.win_rate / 0.3, 1) * 25

  // 일관성 (20점)
  const consistency = (c.consistency_score ?? 0) * 20

  // 활동성 (15점) — total_bids 50건 이상이면 만점
  const activity = Math.min(c.total_bids / 50, 1) * 15

  // 투찰률 범위 패널티: 상대방 평균과 내 목표율이 ±3% 초과 시 감점
  const rateDiff = Math.abs((c.avg_bid_rate ?? 0) - myTargetRate)
  const ratePenalty = rateDiff > 0.03 ? Math.min(rateDiff * 200, 15) : 0

  const total = Math.max(0, Math.min(100, stability + performance + consistency + activity - ratePenalty))
  return { total: +total.toFixed(1), stability: +stability.toFixed(1), performance: +performance.toFixed(1), consistency: +consistency.toFixed(1), activity: +activity.toFixed(1) }
}

function CompatBar({ score }: { score: number }) {
  const color = score >= 75 ? 'bg-emerald-500' : score >= 55 ? 'bg-amber-400' : 'bg-red-400'
  const textColor = score >= 75 ? 'text-emerald-700' : score >= 55 ? 'text-amber-700' : 'text-red-600'
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 rounded-full bg-slate-100 overflow-hidden">
        <div className={cn('h-1.5 rounded-full transition-all', color)} style={{ width: `${score}%` }} />
      </div>
      <span className={cn('text-xs font-bold tabular-nums', textColor)}>
        {score}
      </span>
    </div>
  )
}

function RiskBadge({ level }: { level: string }) {
  const map: Record<string, { label: string; className: string }> = {
    LOW:     { label: '안정', className: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    MEDIUM:  { label: '보통', className: 'bg-amber-50 text-amber-700 border-amber-200' },
    HIGH:    { label: '위험', className: 'bg-red-50 text-red-700 border-red-200' },
    UNKNOWN: { label: '미상', className: 'bg-slate-100 text-slate-500 border-slate-200' },
  }
  const m = map[level] ?? map.UNKNOWN
  return <span className={cn('text-xs px-1.5 py-0.5 rounded border font-semibold', m.className)}>{m.label}</span>
}

export default function JointBidPage() {
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [myTargetRate, setMyTargetRate] = useState('90.5')
  const [minScore, setMinScore] = useState('50')
  const [riskFilter, setRiskFilter] = useState('all')
  const [sortBy, setSortBy] = useState<'compat' | 'win_rate' | 'total_bids'>('compat')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 20

  // 공고 연계 AI 매칭
  const [aiBidId, setAiBidId] = useState('')
  const [aiUserTrack, setAiUserTrack] = useState('500000000')
  const [aiPartRate, setAiPartRate] = useState('60')
  const [aiQueryKey, setAiQueryKey] = useState<{ bidId: number; track: number; rate: number } | null>(null)

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['meta'],
    queryFn: bidsApi.meta,
    staleTime: 300_000,
  })

  const { data: aiResult, isLoading: aiLoading, error: aiError } = useQuery<JointPartnersResponse>({
    queryKey: ['joint-partners', aiQueryKey],
    queryFn: () => bidsApi.jointPartners(aiQueryKey!.bidId, aiQueryKey!.track, aiQueryKey!.rate / 100),
    enabled: !!aiQueryKey,
    staleTime: 60_000,
  })

  // 전체 경쟁사 목록 (최대 200건)
  const { data: listData, isLoading } = useQuery<{ items: Competitor[]; total: number }>({
    queryKey: ['joint-bid-competitors', search, riskFilter],
    queryFn: () => competitorsApi.list({
      keyword: search || undefined,
      page: 1,
      size: 100,
      risk_level: riskFilter === 'all' ? undefined : riskFilter,
    }),
  })

  const targetRate = Number(myTargetRate) / 100

  const scoredList = useMemo(() => {
    const items = listData?.items ?? []
    return items
      .map((c) => ({ ...c, _compat: calcCompat(c, targetRate) }))
      .filter((c) => c._compat.total >= Number(minScore))
      .sort((a, b) => {
        if (sortBy === 'compat') return b._compat.total - a._compat.total
        if (sortBy === 'win_rate') return b.win_rate - a.win_rate
        return b.total_bids - a.total_bids
      })
  }, [listData, targetRate, minScore, sortBy])

  const paginated = scoredList.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(scoredList.length / PAGE_SIZE)

  const handleSearch = () => { setSearch(keyword); setPage(1) }

  // 상위 3사 평균 궁합
  const top3avg = scoredList.length > 0
    ? +(scoredList.slice(0, 3).reduce((s, c) => s + c._compat.total, 0) / Math.min(3, scoredList.length)).toFixed(1)
    : null

  return (
    <div className="min-h-screen bg-slate-50">
      {/* 스티키 헤더 */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Handshake className="h-5 w-5 text-blue-600" />
              공동도급 협정사 탐색
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">경쟁사 데이터 기반 잠재 협력사 궁합 분석 — 안정성·실적·일관성·활동성 종합 평가</p>
          </div>
          {scoredList.length > 0 && (
            <div className="flex items-center gap-4 text-sm">
              <div className="text-right">
                <p className="text-xs text-slate-500">탐색 결과</p>
                <p className="font-bold text-slate-900">{scoredList.length}<span className="text-xs font-normal text-slate-500 ml-0.5">개사</span></p>
              </div>
              {top3avg != null && (
                <div className="text-right">
                  <p className="text-xs text-slate-500">상위 3사 평균</p>
                  <p className="font-bold text-blue-600">{top3avg}<span className="text-xs font-normal text-slate-500 ml-0.5">점</span></p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="p-6 space-y-5 max-w-5xl">
        {/* 공고 연계 적격심사 AI 매칭 */}
        <Card className="relative overflow-hidden bg-white border-blue-200 shadow-sm">
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
          <CardHeader className="pb-3 pt-5 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <div className="rounded-lg p-1.5 bg-blue-50">
                <Zap className="h-4 w-4 text-blue-600" />
              </div>
              공고 연계 적격심사 AI 매칭
            </CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">공고 ID</Label>
                <Input
                  placeholder="예: 12345"
                  value={aiBidId}
                  onChange={(e) => setAiBidId(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const id = parseInt(aiBidId)
                      if (!isNaN(id) && id > 0) setAiQueryKey({ bidId: id, track: Number(aiUserTrack), rate: Number(aiPartRate) })
                    }
                  }}
                  className="border-slate-200 focus:border-blue-300"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">귀사 실적금액 (원)</Label>
                <Input
                  type="number"
                  placeholder="예: 500000000"
                  value={aiUserTrack}
                  onChange={(e) => setAiUserTrack(e.target.value)}
                  className="border-slate-200 focus:border-blue-300"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">귀사 참여지분율 (%)</Label>
                <Select value={aiPartRate} onValueChange={setAiPartRate}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="50">50%</SelectItem>
                    <SelectItem value="60">60%</SelectItem>
                    <SelectItem value="70">70%</SelectItem>
                    <SelectItem value="80">80%</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <Button
                  size="sm"
                  className="w-full bg-blue-600 hover:bg-blue-700 gap-1.5"
                  disabled={!aiBidId || isNaN(parseInt(aiBidId)) || aiLoading}
                  onClick={() => {
                    const id = parseInt(aiBidId)
                    if (!isNaN(id) && id > 0) setAiQueryKey({ bidId: id, track: Number(aiUserTrack), rate: Number(aiPartRate) })
                  }}
                >
                  <Zap className="h-3.5 w-3.5" />
                  {aiLoading ? '분석 중...' : '적격심사 AI 매칭'}
                </Button>
              </div>
            </div>

            {aiError && (
              <p className="text-xs text-red-500 bg-red-50 px-3 py-2 rounded-lg border border-red-100">
                공고를 찾을 수 없습니다. 공고 ID를 확인하세요.
              </p>
            )}

            {aiResult && (
              <div className="space-y-3 mt-3">
                <div className="text-xs text-slate-600 bg-blue-50 rounded-lg px-4 py-2.5 border border-blue-100">
                  <strong className="text-slate-900">{aiResult.bid_title}</strong>
                  <span className="mx-2 text-slate-300">|</span>
                  <span className="text-slate-500">{aiResult.threshold_note}</span>
                </div>
                {aiResult.partners.length === 0 ? (
                  <p className="text-xs text-slate-500 text-center py-6">매칭 가능한 업체가 없습니다.</p>
                ) : (
                  <div className="rounded-xl overflow-hidden border border-slate-200">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-slate-50">
                          <TableHead className="text-sm text-slate-500">업체명</TableHead>
                          <TableHead className="text-sm text-slate-500">사업자번호</TableHead>
                          <TableHead className="text-center text-sm text-slate-500">적격 예상</TableHead>
                          <TableHead className="text-right text-sm text-slate-500">파트너 지분</TableHead>
                          <TableHead className="text-right text-sm text-slate-500">낙찰률</TableHead>
                          <TableHead className="text-right text-sm text-slate-500">궁합점수</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {aiResult.partners.slice(0, 20).map((p) => (
                          <TableRow key={p.competitor_id} className="hover:bg-slate-50 transition-colors">
                            <TableCell className="font-semibold text-sm text-slate-800">{p.name}</TableCell>
                            <TableCell className="text-xs font-mono text-slate-500">{p.biz_reg_no ?? '-'}</TableCell>
                            <TableCell className="text-center">
                              {p.qualification_ok
                                ? <CheckCircle2 className="h-4 w-4 text-emerald-500 mx-auto" />
                                : <XCircle className="h-4 w-4 text-red-400 mx-auto" />}
                            </TableCell>
                            <TableCell className="text-right text-xs font-mono text-slate-600">
                              {(p.joint_min_rate * 100).toFixed(0)}% 이상
                            </TableCell>
                            <TableCell className="text-right text-xs font-mono text-slate-600">
                              {(p.win_rate * 100).toFixed(1)}%
                            </TableCell>
                            <TableCell className="text-right">
                              <span className={cn(
                                'text-xs font-bold tabular-nums',
                                p.compat_score >= 60 ? 'text-emerald-700' : p.compat_score >= 40 ? 'text-amber-700' : 'text-slate-500'
                              )}>
                                {p.compat_score}
                              </span>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
                {aiResult.partners.length > 20 && (
                  <p className="text-xs text-slate-500 text-center">상위 20개사 표시 (전체 {aiResult.partners.length}개사)</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 궁합 점수 기준 안내 카드 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { icon: Shield, label: '안정성', desc: '위험등급 기반', max: 40, color: 'text-blue-600', bg: 'bg-blue-50' },
            { icon: Award, label: '낙찰 실적', desc: '낙찰률 정규화', max: 25, color: 'text-emerald-600', bg: 'bg-emerald-50' },
            { icon: Activity, label: '일관성', desc: '투찰률 변동성', max: 20, color: 'text-purple-600', bg: 'bg-purple-50' },
            { icon: TrendingUp, label: '활동성', desc: '총 입찰건수', max: 15, color: 'text-amber-600', bg: 'bg-amber-50' },
          ].map(({ icon: Icon, label, desc, max, color, bg }) => (
            <Card key={label} className="bg-white border-slate-200 shadow-sm">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <div className={cn('rounded-lg p-1.5', bg)}>
                    <Icon className={cn('h-3.5 w-3.5', color)} />
                  </div>
                  <span className="text-xs font-semibold text-slate-800">{label}</span>
                  <span className="ml-auto text-xs font-bold text-slate-500">{max}점</span>
                </div>
                <p className="text-[11px] text-slate-500">{desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* 필터 카드 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-3 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Search className="h-4 w-4 text-slate-500" />
              탐색 조건
            </CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-1.5 md:col-span-2">
                <Label className="text-sm text-slate-600 font-medium">업체명 검색</Label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                    <Input
                      placeholder="업체명 입력..."
                      value={keyword}
                      onChange={(e) => setKeyword(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      className="pl-8 border-slate-200"
                    />
                  </div>
                  <Button size="sm" onClick={handleSearch} className="shrink-0 bg-slate-800 hover:bg-slate-900">
                    검색
                  </Button>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">내 목표 투찰률 (%)</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="85"
                  max="100"
                  value={myTargetRate}
                  onChange={(e) => setMyTargetRate(e.target.value)}
                  placeholder="예: 90.5"
                  className="border-slate-200"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">최소 궁합점수</Label>
                <Select value={minScore} onValueChange={(v) => { setMinScore(v); setPage(1) }}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">전체</SelectItem>
                    <SelectItem value="40">40점 이상</SelectItem>
                    <SelectItem value="55">55점 이상</SelectItem>
                    <SelectItem value="70">70점 이상</SelectItem>
                    <SelectItem value="80">80점 이상</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">위험등급 필터</Label>
                <Select value={riskFilter} onValueChange={(v) => { setRiskFilter(v); setPage(1) }}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">전체</SelectItem>
                    <SelectItem value="LOW">안정(LOW)</SelectItem>
                    <SelectItem value="MEDIUM">보통(MEDIUM)</SelectItem>
                    <SelectItem value="HIGH">위험(HIGH)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm text-slate-600 font-medium">정렬 기준</Label>
                <Select value={sortBy} onValueChange={(v) => setSortBy(v as typeof sortBy)}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="compat">궁합점수 순</SelectItem>
                    <SelectItem value="win_rate">낙찰률 순</SelectItem>
                    <SelectItem value="total_bids">입찰건수 순</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 결과 테이블 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="pb-3 pt-4 px-5">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Users className="h-4 w-4 text-slate-500" />
              후보 협정사 목록
              {scoredList.length > 0 && (
                <span className="ml-1 text-xs font-normal text-slate-500">— {scoredList.length}개사</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 border-b border-slate-200">
                    <TableHead className="w-8 text-sm text-slate-500">#</TableHead>
                    <TableHead className="text-sm text-slate-500">업체명</TableHead>
                    <TableHead className="text-sm text-slate-500">위험</TableHead>
                    <TableHead className="text-right text-sm text-slate-500">궁합점수</TableHead>
                    <TableHead className="text-right text-sm text-slate-500">낙찰률</TableHead>
                    <TableHead className="text-right text-sm text-slate-500">평균 투찰률</TableHead>
                    <TableHead className="text-right text-sm text-slate-500">입찰건</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading
                    ? Array.from({ length: 8 }).map((_, i) => (
                        <TableRow key={i}>
                          {Array.from({ length: 8 }).map((_, j) => (
                            <TableCell key={j}><Skeleton className="h-4 w-full rounded" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    : paginated.map((c, idx) => {
                        const rank = (page - 1) * PAGE_SIZE + idx + 1
                        const expanded = expandedId === c.id
                        const radarData = [
                          { subject: '안정성', value: +(c._compat.stability / 40 * 100).toFixed(0) },
                          { subject: '실적', value: +(c._compat.performance / 25 * 100).toFixed(0) },
                          { subject: '일관성', value: +(c._compat.consistency / 20 * 100).toFixed(0) },
                          { subject: '활동성', value: +(c._compat.activity / 15 * 100).toFixed(0) },
                        ]
                        const isTop3 = rank <= 3
                        return (
                          <>
                            <TableRow
                              key={c.id}
                              className={cn(
                                'cursor-pointer transition-colors',
                                isTop3 ? 'bg-blue-50/40 hover:bg-blue-50' : 'hover:bg-slate-50',
                                expanded && 'bg-slate-50'
                              )}
                              onClick={() => setExpandedId(expanded ? null : c.id)}
                            >
                              <TableCell className="text-sm text-slate-500 font-mono">{rank}</TableCell>
                              <TableCell>
                                <div className="flex items-center gap-2">
                                  {isTop3 && (
                                    <span className="inline-flex items-center text-[9px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 font-bold border border-blue-200">
                                      TOP
                                    </span>
                                  )}
                                  <span className="font-semibold text-sm text-slate-800">{c.name}</span>
                                </div>
                              </TableCell>
                              <TableCell><RiskBadge level={c.risk_level} /></TableCell>
                              <TableCell className="text-right">
                                <CompatBar score={c._compat.total} />
                              </TableCell>
                              <TableCell className="text-right font-mono text-sm text-slate-600 tabular-nums">
                                {(c.win_rate * 100).toFixed(1)}%
                              </TableCell>
                              <TableCell className="text-right font-mono text-sm text-slate-600 tabular-nums">
                                {c.avg_bid_rate != null ? (c.avg_bid_rate * 100).toFixed(4) + '%' : '-'}
                              </TableCell>
                              <TableCell className="text-right text-sm text-slate-600">{c.total_bids}건</TableCell>
                              <TableCell>
                                {expanded
                                  ? <ChevronUp className="h-3.5 w-3.5 text-slate-500" />
                                  : <ChevronDown className="h-3.5 w-3.5 text-slate-300" />}
                              </TableCell>
                            </TableRow>

                            {expanded && (
                              <TableRow key={`${c.id}-detail`} className="bg-slate-50/80">
                                <TableCell colSpan={8} className="py-5 px-6">
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    {/* 레이더 차트 */}
                                    <div>
                                      <p className="text-xs font-semibold mb-2 text-slate-500">궁합 구성 (각 항목 / 만점 비율)</p>
                                      <ResponsiveContainer width="100%" height={180}>
                                        <RadarChart data={radarData} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
                                          <PolarGrid stroke="#e2e8f0" />
                                          <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: '#64748b' }} />
                                          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                                          <Radar dataKey="value" stroke="#2563eb" fill="#2563eb" fillOpacity={0.15} strokeWidth={2} />
                                        </RadarChart>
                                      </ResponsiveContainer>
                                    </div>

                                    {/* 항목별 점수 */}
                                    <div className="space-y-3">
                                      <p className="text-xs font-semibold text-slate-500">항목별 점수 (만점 기준)</p>
                                      {[
                                        { label: '안정성', score: c._compat.stability, max: 40, color: 'bg-blue-500' },
                                        { label: '낙찰 실적', score: c._compat.performance, max: 25, color: 'bg-emerald-500' },
                                        { label: '일관성', score: c._compat.consistency, max: 20, color: 'bg-purple-500' },
                                        { label: '활동성', score: c._compat.activity, max: 15, color: 'bg-amber-500' },
                                      ].map(({ label, score, max, color }) => (
                                        <div key={label}>
                                          <div className="flex justify-between text-xs mb-1">
                                            <span className="text-slate-600">{label}</span>
                                            <span className="font-mono font-semibold text-slate-700 tabular-nums">{score.toFixed(1)} / {max}</span>
                                          </div>
                                          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                                            <div
                                              className={cn('h-1.5 rounded-full transition-all', color)}
                                              style={{ width: `${(score / max) * 100}%` }}
                                            />
                                          </div>
                                        </div>
                                      ))}
                                      <div className="pt-3 border-t border-slate-200">
                                        <div className="flex items-center justify-between">
                                          <span className="text-xs font-semibold text-slate-700">총 궁합점수</span>
                                          <span className={cn(
                                            'text-2xl font-bold tabular-nums',
                                            c._compat.total >= 75 ? 'text-emerald-600' : c._compat.total >= 55 ? 'text-amber-600' : 'text-red-500'
                                          )}>
                                            {c._compat.total}
                                            <span className="text-sm font-normal text-slate-500 ml-0.5">점</span>
                                          </span>
                                        </div>
                                        <p className="text-xs text-slate-500 mt-0.5">
                                          P25~P75 투찰구간: {c.p25_rate != null ? (c.p25_rate * 100).toFixed(4) : '-'}% ~ {c.p75_rate != null ? (c.p75_rate * 100).toFixed(4) : '-'}%
                                        </p>
                                      </div>
                                    </div>
                                  </div>
                                </TableCell>
                              </TableRow>
                            )}
                          </>
                        )
                      })}

                  {!isLoading && paginated.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center py-12 text-slate-500 text-sm">
                        조건에 맞는 업체가 없습니다. 필터를 조정해보세요.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/50">
                <Button variant="outline" size="sm" className="border-slate-200"
                  onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>이전</Button>
                <span className="text-xs text-slate-500 tabular-nums">{page} / {totalPages} ({scoredList.length}개사)</span>
                <Button variant="outline" size="sm" className="border-slate-200"
                  onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages}>다음</Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 안내 */}
        <p className="text-xs text-slate-500 px-1">
          * 궁합점수는 수집된 입찰 데이터 기반 참고 지표입니다. 실제 협정 체결 전 재무상태·면허 등을 반드시 확인하세요.
        </p>
      </div>
    </div>
  )
}
