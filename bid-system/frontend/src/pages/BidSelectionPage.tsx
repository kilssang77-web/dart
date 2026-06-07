import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { selectionApi } from '../api'

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
  GO:    { label: 'GO',    bg: 'bg-green-50',  border: 'border-green-200', badge: 'bg-green-500 text-white',  icon: '✓' },
  WATCH: { label: 'WATCH', bg: 'bg-yellow-50', border: 'border-yellow-200', badge: 'bg-yellow-500 text-white', icon: '~' },
  NO_GO: { label: 'NO-GO', bg: 'bg-gray-50',   border: 'border-gray-200',  badge: 'bg-gray-400 text-white',   icon: '✕' },
}

const RISK_COLOR = { LOW: 'text-green-600', MEDIUM: 'text-yellow-600', HIGH: 'text-red-600' }

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
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`rounded-xl border ${cfg.border} ${cfg.bg} p-4 space-y-3`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${cfg.badge}`}>
              {cfg.icon} {cfg.label}
            </span>
            <span className="text-xs text-gray-500">점수 {item.score.toFixed(1)}/10</span>
            {item.recommended_strategy && (
              <span className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">
                {STRATEGY_LABELS[item.recommended_strategy] || item.recommended_strategy}
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-gray-900 truncate" title={item.title}>{item.title}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {fmt억(item.base_amount)} | {item.bid_open_date?.slice(0, 10) || '날짜 미상'}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-semibold text-gray-800">EV {fmt억(item.ev_score)}</div>
          <div className="text-xs text-gray-500">낙찰확률 {(item.win_prob_best * 100).toFixed(0)}%</div>
        </div>
      </div>

      {/* 지표 행 */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-white/60 rounded-lg p-2 text-center">
          <div className="text-gray-400">적격통과</div>
          <div className="font-semibold text-gray-700">{(item.qualify_prob * 100).toFixed(0)}%</div>
        </div>
        <div className="bg-white/60 rounded-lg p-2 text-center">
          <div className="text-gray-400">낙찰확률</div>
          <div className="font-semibold text-gray-700">{(item.win_prob_best * 100).toFixed(0)}%</div>
        </div>
        <div className="bg-white/60 rounded-lg p-2 text-center">
          <div className="text-gray-400">경쟁 위험</div>
          <div className={`font-semibold ${RISK_COLOR[item.competitor_risk]}`}>{item.competitor_risk}</div>
        </div>
      </div>

      {/* NO_GO 이유 / 추천 투찰률 */}
      {item.no_go_reasons.length > 0 && (
        <div>
          <button onClick={() => setExpanded(!expanded)} className="text-xs text-gray-400 hover:text-gray-600">
            {expanded ? '▲ 이유 접기' : '▼ NO-GO 이유 보기'}
          </button>
          {expanded && (
            <ul className="mt-1 space-y-0.5">
              {item.no_go_reasons.map((r, i) => (
                <li key={i} className="text-xs text-gray-600 flex items-start gap-1">
                  <span className="text-red-400 mt-0.5">•</span>
                  <span>{r.replace(/^[a-z_]+:/, '')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {item.recommended_rate && item.verdict === 'GO' && (
        <div className="bg-blue-50 rounded-lg px-3 py-2 text-xs">
          <span className="text-blue-500 font-medium">추천 투찰률:</span>
          <span className="ml-1 font-bold text-blue-700">{(item.recommended_rate * 100).toFixed(3)}%</span>
        </div>
      )}
    </div>
  )
}

export default function BidSelectionPage() {
  const [days, setDays] = useState(7)
  const [activeTab, setActiveTab] = useState<'GO' | 'WATCH' | 'NO_GO'>('GO')
  const [evaluatingId, setEvaluatingId] = useState<number | null>(null)
  const [newBidId, setNewBidId] = useState('')
  const qc = useQueryClient()

  const { data, isLoading, refetch } = useQuery<GoListData>({
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

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">공고 선별 — GO 목록</h1>
          <p className="text-sm text-gray-500 mt-1">E1 엔진이 선별한 투찰 권장 공고</p>
        </div>
        <div className="flex items-center gap-3">
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="text-sm border rounded-lg px-3 py-2">
            {[3, 7, 14, 30].map((d) => <option key={d} value={d}>최근 {d}일</option>)}
          </select>
          <button onClick={() => refetch()} className="px-3 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200">
            새로고침
          </button>
        </div>
      </div>

      {/* 공고 평가 입력 */}
      <div className="bg-blue-50 rounded-xl border border-blue-200 p-4 flex items-center gap-3">
        <input
          value={newBidId}
          onChange={(e) => setNewBidId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleEval()}
          placeholder="공고 ID 입력 후 평가"
          className="flex-1 border rounded-lg px-3 py-2 text-sm bg-white"
          type="number"
        />
        <button
          onClick={handleEval}
          disabled={evalMut.isPending || !newBidId}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {evalMut.isPending ? '평가 중...' : 'GO/NO-GO 판정'}
        </button>
      </div>

      {/* 요약 카드 */}
      {data && (
        <div className="grid grid-cols-3 gap-4">
          {([['GO', 'bg-green-50 border-green-200 text-green-700'], ['WATCH', 'bg-yellow-50 border-yellow-200 text-yellow-700'], ['NO_GO', 'bg-gray-50 border-gray-200 text-gray-600']] as const).map(([v, cls]) => (
            <button key={v} onClick={() => setActiveTab(v as 'GO' | 'WATCH' | 'NO_GO')}
              className={`rounded-xl border p-4 text-center cursor-pointer transition-all ${cls} ${activeTab === v ? 'ring-2 ring-offset-1 ring-blue-400' : ''}`}>
              <div className="text-2xl font-bold">{data[`${v.toLowerCase()}_count` as 'go_count' | 'watch_count' | 'no_go_count']}</div>
              <div className="text-sm font-medium mt-0.5">{v === 'NO_GO' ? 'NO-GO' : v}</div>
            </button>
          ))}
        </div>
      )}

      {/* 목록 */}
      {isLoading ? (
        <div className="text-center text-gray-400 py-12">로딩 중...</div>
      ) : items.length === 0 ? (
        <div className="text-center text-gray-400 py-12 bg-gray-50 rounded-xl border">
          {activeTab} 항목이 없습니다. 위에서 공고 ID를 입력해 평가해보세요.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((item) => <SelectionCard key={item.bid_id} item={item} />)}
        </div>
      )}
    </div>
  )
}
