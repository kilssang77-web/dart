import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { selectionApi } from '../api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  CheckCircle2, MinusCircle, XCircle, RefreshCw, Loader2,
  TrendingUp, ChevronDown, ChevronUp, Zap, Target, CalendarDays,
} from 'lucide-react'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

interface SelectionItem {
  bid_id: number
  title: string
  base_amount: number
  bid_open_date?: string
  verdict: 'GO' | 'WATCH' | 'NO_GO'
  score: number
  ev_score: number
  qualify_prob: number
  win_prob_best: number
  competitor_risk: 'LOW' | 'MEDIUM' | 'HIGH'
  no_go_reasons: string[]
  recommended_strategy: string
  recommended_rate?: number
  actual_action?: string
  data_count?: number
  confidence?: 'high' | 'medium' | 'low'
}

interface GoListData {
  go: SelectionItem[]
  watch: SelectionItem[]
  no_go: SelectionItem[]
  total: number
  go_count: number
  watch_count: number
  no_go_count: number
}

const VERDICT_CONFIG = {
  GO:    {
    label: 'GO',
    headerBg: 'bg-emerald-500',
    sectionBg: 'bg-emerald-50 border-emerald-200',
    badge: 'bg-emerald-500 text-white',
    cardBorder: 'border-emerald-200',
    cardAccent: 'bg-emerald-500',
    icon: CheckCircle2,
    iconColor: 'text-emerald-600',
    countKey: 'go_count' as const,
    statBg: 'bg-emerald-50 border-emerald-200',
    statText: 'text-emerald-700',
    statCount: 'text-emerald-600',
    ringColor: 'ring-emerald-400',
  },
  WATCH: {
    label: 'WATCH',
    headerBg: 'bg-amber-400',
    sectionBg: 'bg-amber-50 border-amber-200',
    badge: 'bg-amber-400 text-white',
    cardBorder: 'border-amber-200',
    cardAccent: 'bg-amber-400',
    icon: MinusCircle,
    iconColor: 'text-amber-500',
    countKey: 'watch_count' as const,
    statBg: 'bg-amber-50 border-amber-200',
    statText: 'text-amber-700',
    statCount: 'text-amber-600',
    ringColor: 'ring-amber-400',
  },
  NO_GO: {
    label: 'NO-GO',
    headerBg: 'bg-slate-400',
    sectionBg: 'bg-slate-50 border-slate-200',
    badge: 'bg-slate-400 text-white',
    cardBorder: 'border-slate-200',
    cardAccent: 'bg-slate-400',
    icon: XCircle,
    iconColor: 'text-slate-400',
    countKey: 'no_go_count' as const,
    statBg: 'bg-slate-50 border-slate-200',
    statText: 'text-slate-700',
    statCount: 'text-slate-500',
    ringColor: 'ring-slate-400',
  },
}

const RISK_CONFIG = {
  LOW:    { cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'LOW' },
  MEDIUM: { cls: 'bg-amber-50 text-amber-700 border-amber-200',       label: 'MED' },
  HIGH:   { cls: 'bg-red-50 text-red-700 border-red-200',             label: 'HIGH' },
}

const STRATEGY_LABELS: Record<string, string> = {
  aggressive:   '공격형',
  balanced:     '균형형',
  conservative: '안정형',
}

function fmt억(v: number) {
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}억`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}만`
  return v.toLocaleString()
}

function SelectionCard({ item }: { item: SelectionItem }) {
  const cfg = VERDICT_CONFIG[item.verdict]
  const riskCfg = RISK_CONFIG[item.competitor_risk]
  const [expanded, setExpanded] = useState(false)

  return (
    <Card className={cn(
      'bg-white border shadow-sm hover:shadow-md transition-shadow overflow-hidden',
      cfg.cardBorder,
    )}>
      {/* Top accent bar */}
      <div className={cn('h-0.5', cfg.cardAccent)} />
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className={cn('inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full', cfg.badge)}>
                <cfg.icon className="h-3 w-3" />
                {cfg.label}
              </span>
              <span className="text-xs text-slate-400 tabular-nums">점수 {item.score.toFixed(1)}/10</span>
              {item.recommended_strategy && (
                <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded-full font-medium">
                  {STRATEGY_LABELS[item.recommended_strategy] || item.recommended_strategy}
                </span>
              )}
              {item.confidence && (
                <span className={cn(
                  'text-[10px] px-1.5 py-0.5 rounded-full border font-medium',
                  item.confidence === 'high'   ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                  item.confidence === 'medium' ? 'bg-amber-50 text-amber-600 border-amber-200' :
                                                 'bg-gray-50 text-gray-500 border-gray-200',
                )}>
                  근거 {item.data_count ?? 0}건
                </span>
              )}
            </div>
            <p className="text-sm font-semibold text-slate-900 leading-snug line-clamp-2" title={item.title}>
              {item.title}
            </p>
            <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400">
              <span className="font-medium text-slate-600">{fmt억(item.base_amount)}</span>
              <span className="flex items-center gap-1">
                <CalendarDays className="h-3 w-3" />
                {item.bid_open_date?.slice(0, 10) || '날짜 미상'}
              </span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="bg-slate-50 border border-slate-100 rounded-lg px-2.5 py-1.5">
              <div className="text-sm font-bold text-slate-800 tabular-nums">EV {fmt억(item.ev_score)}</div>
              <div className="text-[10px] text-slate-400 mt-0.5">낙찰확률 {(item.win_prob_best * 100).toFixed(0)}%</div>
            </div>
          </div>
        </div>

        {/* 지표 행 */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-slate-50 rounded-lg p-2 text-center border border-slate-100">
            <div className="text-slate-400 mb-0.5">적격통과</div>
            <div className="font-bold text-slate-800 tabular-nums">{(item.qualify_prob * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-slate-50 rounded-lg p-2 text-center border border-slate-100">
            <div className="text-slate-400 mb-0.5">낙찰확률</div>
            <div className={cn('font-bold tabular-nums',
              item.win_prob_best > 0.5 ? 'text-emerald-700' :
              item.win_prob_best > 0.3 ? 'text-amber-700' : 'text-slate-700'
            )}>
              {(item.win_prob_best * 100).toFixed(0)}%
            </div>
          </div>
          <div className="bg-slate-50 rounded-lg p-2 text-center border border-slate-100">
            <div className="text-slate-400 mb-0.5">경쟁 위험</div>
            <div className={cn('font-bold text-xs px-1.5 py-0.5 rounded-full border inline-block', riskCfg.cls)}>
              {riskCfg.label}
            </div>
          </div>
        </div>

        {/* NO_GO 이유 */}
        {item.no_go_reasons.length > 0 && (
          <div>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
            >
              {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              {expanded ? 'NO-GO 이유 접기' : 'NO-GO 이유 보기'}
            </button>
            {expanded && (
              <ul className="mt-2 space-y-1 bg-red-50/50 rounded-lg border border-red-100 p-2">
                {item.no_go_reasons.map((r, i) => (
                  <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                    <span className="text-red-400 mt-0.5 shrink-0">•</span>
                    <span>{r.replace(/^[a-z_]+:/, '')}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* 추천 투찰률 */}
        {item.recommended_rate && item.verdict === 'GO' && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-xs flex items-center justify-between">
            <span className="text-blue-500 font-medium flex items-center gap-1">
              <Target className="h-3 w-3" />추천 투찰률
            </span>
            <span className="font-bold text-blue-700 tabular-nums">{(item.recommended_rate * 100).toFixed(3)}%</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function BidSelectionPage() {
  const [days, setDays] = useState(7)
  const [activeTab, setActiveTab] = useState<'GO' | 'WATCH' | 'NO_GO'>('GO')
  const [evaluatingId, setEvaluatingId] = useState<number | null>(null)
  const [newBidId, setNewBidId] = useState('')
  const qc = useQueryClient()

  const { data, isLoading, refetch, isFetching } = useQuery<GoListData>({
    queryKey: ['go-list', days],
    queryFn: () => selectionApi.goList(days),
  })

  const evalMut = useMutation({
    mutationFn: (id: number) => selectionApi.evaluate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['go-list'] })
      setEvaluatingId(null)
      setNewBidId('')
    },
    onSettled: () => setEvaluatingId(null),
  })

  const handleEval = () => {
    const id = parseInt(newBidId)
    if (!id) return
    setEvaluatingId(id)
    evalMut.mutate(id)
  }

  const items = data ? data[activeTab.toLowerCase() as 'go' | 'watch' | 'no_go'] : []

  const tabOrder: ('GO' | 'WATCH' | 'NO_GO')[] = ['GO', 'WATCH', 'NO_GO']

  return (
    <div className="min-h-full bg-slate-50">
      {/* Sticky Page Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-5xl mx-auto">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Zap className="h-5 w-5 text-blue-600" />
              공고 선별 — GO 목록
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">E1 엔진이 선별한 투찰 권장 공고</p>
          </div>
          <div className="flex items-center gap-2">
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger className="w-28 h-8 text-xs border-slate-200 bg-slate-50">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[3, 7, 14, 30].map((d) => (
                  <SelectItem key={d} value={String(d)}>최근 {d}일</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 px-3 gap-1.5 border-slate-200 text-slate-600 hover:bg-slate-50"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
              새로고침
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-5 space-y-5">

        {/* 통계 카드 */}
        {isLoading ? (
          <div className="grid grid-cols-3 gap-4">
            {[0,1,2].map(i => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
          </div>
        ) : data && (
          <div className="grid grid-cols-3 gap-4">
            {tabOrder.map((v) => {
              const cfg = VERDICT_CONFIG[v]
              const count = data[cfg.countKey]
              const isActive = activeTab === v
              return (
                <button
                  key={v}
                  onClick={() => setActiveTab(v)}
                  className={cn(
                    'relative overflow-hidden rounded-xl border p-4 text-left cursor-pointer transition-all bg-white shadow-sm hover:shadow-md',
                    cfg.cardBorder,
                    isActive ? `ring-2 ring-offset-2 ${cfg.ringColor} shadow-md` : ''
                  )}
                >
                  <div className={cn('absolute top-0 left-0 right-0 h-1', cfg.headerBg)} />
                  <div className="flex items-center justify-between mt-1">
                    <div>
                      <p className={cn('text-3xl font-bold tabular-nums', cfg.statCount)}>{count}</p>
                      <p className={cn('text-sm font-semibold mt-0.5', cfg.statText)}>
                        {v === 'NO_GO' ? 'NO-GO' : v}
                      </p>
                    </div>
                    <div className={cn('rounded-xl p-2.5', cfg.statBg)}>
                      <cfg.icon className={cn('h-5 w-5', cfg.iconColor)} />
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* 공고 평가 입력 */}
        <Card className="bg-white border-blue-200 shadow-sm">
          <CardHeader className="border-b border-blue-100 pb-3">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-600" />공고 GO/NO-GO 판정
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-3 pb-3">
            <div className="flex items-center gap-2">
              <input
                value={newBidId}
                onChange={(e) => setNewBidId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleEval()}
                placeholder="공고 ID 입력 후 평가 실행"
                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm bg-slate-50 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-300 focus:border-blue-300 transition-colors text-slate-700 placeholder:text-slate-400"
                type="number"
              />
              <Button
                onClick={handleEval}
                disabled={evalMut.isPending || !newBidId}
                className="gap-1.5 bg-blue-600 hover:bg-blue-700 text-white h-9 px-4 text-sm"
              >
                {evalMut.isPending ? (
                  <><Loader2 className="h-3.5 w-3.5 animate-spin" />평가 중...</>
                ) : (
                  <><Zap className="h-3.5 w-3.5" />GO/NO-GO 판정</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 탭 섹션 헤더 */}
        <div className="flex items-center gap-2">
          {tabOrder.map((v) => {
            const cfg = VERDICT_CONFIG[v]
            const count = data?.[cfg.countKey] ?? 0
            return (
              <button
                key={v}
                onClick={() => setActiveTab(v)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all border',
                  activeTab === v
                    ? cn(cfg.badge, 'border-transparent shadow-sm')
                    : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                )}
              >
                <cfg.icon className="h-3.5 w-3.5" />
                {v === 'NO_GO' ? 'NO-GO' : v}
                <span className={cn(
                  'rounded-full px-1.5 py-px text-[10px] tabular-nums',
                  activeTab === v ? 'bg-white/30' : 'bg-slate-100 text-slate-500'
                )}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        {/* 목록 */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Card className="bg-white border-slate-200 shadow-sm">
            <CardContent className="py-16 text-center">
              <div className="flex items-center justify-center mb-3">
                {activeTab === 'GO'
                  ? <CheckCircle2 className="h-8 w-8 text-slate-200" />
                  : activeTab === 'WATCH'
                  ? <MinusCircle className="h-8 w-8 text-slate-200" />
                  : <XCircle className="h-8 w-8 text-slate-200" />
                }
              </div>
              <p className="text-sm text-slate-500">{activeTab} 항목이 없습니다.</p>
              <p className="text-xs text-slate-400 mt-1">위에서 공고 ID를 입력해 평가해보세요.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {items.map((item) => <SelectionCard key={item.bid_id} item={item} />)}
          </div>
        )}
      </div>
    </div>
  )
}
