import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Users, TrendingUp, AlertTriangle, Star, Loader2, Search } from 'lucide-react'
import { executionsApi } from '../api'
import type { OurCompetitor } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const fmtRate = (r: number | null | undefined) =>
  r != null ? (r * 100).toFixed(4) + '%' : '-'

function AggressionBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-muted-foreground">-</span>
  const pct = Math.min(Math.round(value * 100), 100)
  const color = value > 0.7 ? 'bg-red-500' : value > 0.4 ? 'bg-orange-400' : 'bg-green-400'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">{pct}%</span>
    </div>
  )
}

function CompetitorCard({ comp }: { comp: OurCompetitor }) {
  const winRate = comp.co_participation_cnt > 0
    ? Math.round((comp.co_win_cnt / comp.co_participation_cnt) * 100)
    : null

  return (
    <div className="border rounded-xl bg-white p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            {comp.is_primary_rival && (
              <Star className="h-3.5 w-3.5 text-amber-400 fill-amber-400 shrink-0" />
            )}
            <span className="font-semibold text-sm truncate">{comp.company_name}</span>
          </div>
          {comp.biz_reg_no && (
            <div className="text-xs text-muted-foreground font-mono mt-0.5">{comp.biz_reg_no}</div>
          )}
        </div>
        <Badge
          variant="outline"
          className={cn(
            'text-xs shrink-0',
            winRate != null && winRate >= 30 ? 'border-red-300 text-red-600' : 'border-gray-200 text-gray-500'
          )}
        >
          {winRate != null ? `상대 낙찰 ${winRate}%` : '낙찰이력없음'}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-3 text-xs">
        <div>
          <div className="text-muted-foreground">동반 참여</div>
          <div className="font-bold text-gray-800">{comp.co_participation_cnt}건</div>
        </div>
        <div>
          <div className="text-muted-foreground">상대 낙찰</div>
          <div className="font-bold text-gray-800">{comp.co_win_cnt}건</div>
        </div>
        <div>
          <div className="text-muted-foreground">평균 투찰율</div>
          <div className="font-medium">{fmtRate(comp.avg_bid_rate)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">공격성</div>
          <AggressionBar value={comp.aggression} />
        </div>
      </div>

      {(comp.last_seen_at || comp.last_seen_agency) && (
        <div className="mt-2 pt-2 border-t text-xs text-muted-foreground">
          최근: {comp.last_seen_at ?? ''} {comp.last_seen_agency ? `· ${comp.last_seen_agency}` : ''}
        </div>
      )}
    </div>
  )
}

export default function OurCompetitorsPage() {
  const [search, setSearch] = useState('')
  const [limitN, setLimitN] = useState(50)

  const { data = [], isLoading } = useQuery({
    queryKey: ['our-competitors', limitN],
    queryFn: () => executionsApi.ourCompetitors(limitN),
  })

  const filtered = data.filter((c) =>
    c.company_name.toLowerCase().includes(search.toLowerCase()) ||
    (c.biz_reg_no ?? '').includes(search)
  )

  const primaryRivals = filtered.filter((c) => c.is_primary_rival)
  const others = filtered.filter((c) => !c.is_primary_rival)

  const totalParticipations = data.reduce((s, c) => s + c.co_participation_cnt, 0)
  const avgWinRate =
    data.length > 0
      ? Math.round(
          (data.reduce((s, c) => s + c.co_win_cnt, 0) / Math.max(totalParticipations, 1)) * 100
        )
      : null

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-5xl mx-auto">
      {/* 헤더 */}
      <div className="flex items-center gap-2">
        <Users className="h-6 w-6 text-indigo-600" />
        <div>
          <h1 className="text-xl font-bold">자사 경쟁사 레이더</h1>
          <p className="text-xs text-muted-foreground">SUCVIEW 데이터 기반 · 동반 출현 빈도순</p>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="p-3 text-center">
          <div className="text-2xl font-bold text-indigo-600">{data.length}</div>
          <div className="text-xs text-muted-foreground mt-0.5">추적 경쟁사</div>
        </Card>
        <Card className="p-3 text-center">
          <div className="text-2xl font-bold text-gray-800">{totalParticipations.toLocaleString()}</div>
          <div className="text-xs text-muted-foreground mt-0.5">총 동반 참여</div>
        </Card>
        <Card className="p-3 text-center">
          <div className={cn('text-2xl font-bold', avgWinRate != null && avgWinRate >= 20 ? 'text-red-500' : 'text-green-600')}>
            {avgWinRate != null ? `${avgWinRate}%` : '-'}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">평균 낙찰율 (상대)</div>
        </Card>
      </div>

      {/* 검색 */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="회사명 또는 사업자번호 검색"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Users className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <div className="text-sm">SUCVIEW 파일을 업로드하면 경쟁사가 자동 등록됩니다.</div>
        </div>
      ) : (
        <>
          {primaryRivals.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-3">
                <Star className="h-4 w-4 text-amber-400 fill-amber-400" />
                <span className="text-sm font-semibold text-gray-700">주요 경쟁사</span>
                <span className="text-xs text-muted-foreground">({primaryRivals.length})</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {primaryRivals.map((c) => <CompetitorCard key={c.id} comp={c} />)}
              </div>
            </div>
          )}

          <div>
            {primaryRivals.length > 0 && (
              <div className="text-sm font-semibold text-gray-700 mb-3">
                전체 ({others.length})
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {others.map((c) => <CompetitorCard key={c.id} comp={c} />)}
            </div>
          </div>

          {data.length >= limitN && (
            <div className="text-center">
              <button
                className="text-xs text-blue-600 underline"
                onClick={() => setLimitN((n) => n + 50)}
              >
                더 보기 (+50)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
