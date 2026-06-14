import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Layers, TrendingUp, BarChart2, ChevronRight, ArrowUp, ArrowDown, Minus } from 'lucide-react'
import { http } from '@/api/client'
import { ErrorState } from '@/components/ui/ErrorState'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

// ── API 타입 ────────────────────────────────────────────────────────────────
interface TrendingTheme {
  theme:       string
  count:       number
  stock_count: number
  avg_score:   number
  source:      'news' | 'sector'
}

interface ThemeCluster {
  cluster_id:  number
  keywords:    string[]
  news_count:  number
  stock_codes: string[]
  trend?:      'rising' | 'falling' | 'stable'
}

interface ThemeDetail {
  theme:  string
  hours:  number
  stocks: Array<{
    code:          string
    name:          string
    sector?:       string
    max_score:     number
    event_count:   number
    last_detected: string
  }>
  hourly: Array<{ bucket: string; count: number }>
}

interface ThemeSpreadDaily {
  theme:     string
  days:      number
  snapshots: Array<{ snap_date: string; stock_count: number; avg_return?: number }>
  source:    string
}

interface ThemeHistoryItem {
  snap_date:      string
  stock_count:    number
  avg_return:     number | null
  momentum_score: number | null
  velocity:       number | null
  lead_codes:     string[]
  top_codes:      string[]
}

interface ThemeHistory {
  theme:   string
  days:    number
  history: ThemeHistoryItem[]
}

// ── API 함수 ────────────────────────────────────────────────────────────────
const themesApi = {
  trending: (hours = 72) =>
    http.get<{ themes: TrendingTheme[] }>('/themes/trending', { params: { hours } })
        .then((r) => r.data.themes),
  clusters: () =>
    http.get<{ clusters: ThemeCluster[]; updated_at: string | null }>('/themes/clusters')
        .then((r) => r.data),
  detail: (theme: string, hours = 72) =>
    http.get<ThemeDetail>(`/themes/${encodeURIComponent(theme)}`, { params: { hours } })
        .then((r) => r.data),
  spreadDaily: (theme: string, days = 14) =>
    http.get<ThemeSpreadDaily>('/themes/spread/daily', { params: { theme, days } })
        .then((r) => r.data),
  spreadHistory: (theme: string, days = 30) =>
    http.get<ThemeHistory>('/themes/spread/history', { params: { theme, days } })
        .then((r) => r.data),
}

// ── 메인 페이지 ─────────────────────────────────────────────────────────────
export function Themes() {
  const [hours,         setHours]         = useState(72)
  const [selectedTheme, setSelectedTheme] = useState<string | null>(null)
  const [activeTab,     setActiveTab]     = useState<'trending' | 'clusters'>('trending')

  const { data: trending, isLoading: trendLoading, error: trendErr, refetch: refetchTrend } = useQuery({
    queryKey:        ['themes-trending', hours],
    queryFn:         () => themesApi.trending(hours),
    refetchInterval: 300_000,
  })

  const { data: clusters, isLoading: clusterLoading, error: clusterErr } = useQuery({
    queryKey:        ['themes-clusters'],
    queryFn:         themesApi.clusters,
    refetchInterval: 600_000,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['themes-detail', selectedTheme, hours],
    queryFn:  () => themesApi.detail(selectedTheme!, hours),
    enabled:  !!selectedTheme,
  })

  const maxCount = trending ? Math.max(...trending.map((t) => t.count), 1) : 1

  return (
    <div className="p-5 space-y-4 max-w-[1600px]">

      {/* 탭 + 시간 필터 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
          {(['trending', 'clusters'] as const).map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={clsx('px-4 py-2 text-sm font-medium transition-colors',
                activeTab === tab
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)]')}>
              {tab === 'trending' ? '트렌딩 테마' : 'AI 클러스터'}
            </button>
          ))}
        </div>
        {activeTab === 'trending' && (
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] focus:outline-none focus:border-cyan-500"
          >
            <option value={24}>24시간</option>
            <option value={48}>48시간</option>
            <option value={72}>72시간</option>
            <option value={168}>1주</option>
          </select>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 좌측: 테마 목록 */}
        <div className="space-y-2">
          {activeTab === 'trending' ? (
            <>
              {trendLoading && Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-14 skeleton rounded-xl" />
              ))}
              {trendErr && (
                <ErrorState message="테마 데이터를 불러오지 못했습니다" retry={refetchTrend} />
              )}
              {trending?.map((t) => (
                <ThemeCard
                  key={t.theme}
                  theme={t}
                  maxCount={maxCount}
                  selected={selectedTheme === t.theme}
                  onClick={() => setSelectedTheme(selectedTheme === t.theme ? null : t.theme)}
                />
              ))}
              {trending?.length === 0 && (
                <div className="py-12 text-center text-[var(--muted)] text-sm">
                  탐지된 테마가 없습니다
                </div>
              )}
            </>
          ) : (
            <>
              {clusterLoading && Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-20 skeleton rounded-xl" />
              ))}
              {clusterErr && <ErrorState message="클러스터 데이터를 불러오지 못했습니다" />}
              {clusters?.clusters.map((c) => (
                <ClusterCard key={c.cluster_id} cluster={c} />
              ))}
              {clusters?.clusters.length === 0 && (
                <div className="py-12 text-center text-[var(--muted)] text-sm">
                  <p>클러스터가 없습니다.</p>
                  <p className="text-xs mt-1">analyzer 서비스가 뉴스를 처리한 후 생성됩니다.</p>
                </div>
              )}
              {clusters?.updated_at && (
                <p className="text-xs text-[var(--muted)] text-center pt-1">
                  최종 업데이트: {clusters.updated_at.slice(0, 16).replace('T', ' ')}
                </p>
              )}
            </>
          )}
        </div>

        {/* 우측: 테마 상세 */}
        <div className="lg:col-span-2">
          {selectedTheme ? (
            <ThemeDetailPanel
              theme={selectedTheme}
              detail={detail ?? null}
              isLoading={detailLoading}
              hours={hours}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-64 gap-3 text-[var(--muted)] bg-[var(--card)] border border-[var(--border)] rounded-xl">
              <Layers size={32} className="opacity-30" />
              <p className="text-sm">테마를 클릭하면 상세 정보를 확인할 수 있습니다</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 트렌딩 테마 카드 ──────────────────────────────────────────────────────────
function ThemeCard({ theme: t, maxCount, selected, onClick }: {
  theme: TrendingTheme; maxCount: number; selected: boolean; onClick: () => void
}) {
  const pct = Math.max(4, (t.count / maxCount) * 100)
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left p-3 rounded-xl border transition-all',
        selected
          ? 'bg-cyan-500/10 border-cyan-500/40'
          : 'bg-[var(--card)] border-[var(--border)] hover:border-cyan-500/30',
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--fg)]">{t.theme}</span>
          <span className={clsx('text-xs px-1.5 py-0.5 rounded',
            t.source === 'news' ? 'bg-purple-500/15 text-purple-400' : 'bg-green-500/15 text-green-400')}>
            {t.source === 'news' ? '뉴스' : '섹터'}
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs text-[var(--muted)]">
          <span>{t.count}건</span>
          <ChevronRight size={12} />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs text-[var(--muted)] tabular w-14 text-right">
          {t.stock_count}종목 · {t.avg_score.toFixed(2)}점
        </span>
      </div>
    </button>
  )
}

// ── AI 클러스터 카드 ──────────────────────────────────────────────────────────
function ClusterCard({ cluster: c }: { cluster: ThemeCluster }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-xs flex items-center justify-center font-bold">
            {c.cluster_id + 1}
          </span>
          <span className="text-xs text-[var(--muted)]">
            뉴스 {c.news_count}건 · 종목 {c.stock_codes.length}개
          </span>
        </div>
        {c.trend && (
          <span className={clsx('text-xs px-1.5 py-0.5 rounded',
            c.trend === 'rising' ? 'bg-red-500/15 text-red-400' :
            c.trend === 'falling' ? 'bg-blue-500/15 text-blue-400' :
            'bg-[var(--border)] text-[var(--muted)]')}>
            {c.trend === 'rising' ? '↑ 상승' : c.trend === 'falling' ? '↓ 하락' : '— 횡보'}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        {c.keywords.slice(0, 6).map((k) => (
          <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--fg)]">
            {k}
          </span>
        ))}
      </div>
      {c.stock_codes.length > 0 && (
        <div className="text-xs text-[var(--muted)] font-mono">
          {c.stock_codes.slice(0, 5).join(' · ')}
          {c.stock_codes.length > 5 && ` 외 ${c.stock_codes.length - 5}개`}
        </div>
      )}
    </div>
  )
}

const TOOLTIP_STYLE = {
  background: 'var(--card)', border: '1px solid var(--border)',
  borderRadius: 8, fontSize: 11, color: 'var(--fg)',
}

// ── 테마 상세 패널 ────────────────────────────────────────────────────────────
function ThemeDetailPanel({ theme, detail, isLoading, hours }: {
  theme: string; detail: ThemeDetail | null; isLoading: boolean; hours: number
}) {
  const { data: histData } = useQuery({
    queryKey: ['theme-history', theme],
    queryFn:  () => themesApi.spreadHistory(theme, 30),
    enabled:  !!theme,
    staleTime: 300_000,
  })

  const hist = histData?.history ?? []

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <TrendingUp size={15} className="text-cyan-400" />
          <CardTitle>{theme}</CardTitle>
          <span className="text-xs text-[var(--muted)]">최근 {hours}시간</span>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 skeleton rounded-lg" />)}
          </div>
        ) : !detail ? (
          <p className="text-sm text-[var(--muted)] text-center py-8">데이터 없음</p>
        ) : (
          <>
            {/* 모멘텀 추이 차트 */}
            {hist.length > 1 && (
              <div>
                <div className="text-xs text-[var(--muted)] mb-2 font-medium flex items-center gap-1.5">
                  <BarChart2 size={11} /> 30일 종목 수 추이
                  {hist.length > 0 && (() => {
                    const latest  = hist[hist.length - 1]
                    const vel     = latest.velocity ?? 0
                    const VIcon   = vel > 0 ? ArrowUp : vel < 0 ? ArrowDown : Minus
                    const vColor  = vel > 0 ? 'text-green-400' : vel < 0 ? 'text-red-400' : 'text-[var(--muted)]'
                    return (
                      <span className={clsx('flex items-center gap-0.5 text-[10px] font-semibold ml-1', vColor)}>
                        <VIcon size={10} /> {vel > 0 ? '+' : ''}{vel}
                      </span>
                    )
                  })()}
                </div>
                <ResponsiveContainer width="100%" height={100}>
                  <AreaChart data={hist} margin={{ top: 2, right: 4, bottom: 0, left: -20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="snap_date" tick={{ fontSize: 9, fill: '#71717a' }}
                      tickFormatter={(v: string) => v.slice(5)} />
                    <YAxis tick={{ fontSize: 9, fill: '#71717a' }} />
                    <Tooltip contentStyle={TOOLTIP_STYLE}
                      formatter={(v: number) => [v, '종목 수']} />
                    <Area dataKey="stock_count" stroke="#22d3ee" fill="#22d3ee22"
                      strokeWidth={1.5} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
                {/* 리드 종목 표시 */}
                {hist[hist.length - 1]?.lead_codes.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    <span className="text-[10px] text-[var(--muted)] mr-1">리드 종목:</span>
                    {hist[hist.length - 1].lead_codes.map((code) => (
                      <span key={code} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400">
                        {code}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 시간별 탐지 추이 */}
            {detail.hourly.length > 0 && (
              <div>
                <div className="text-xs text-[var(--muted)] mb-2 font-medium">시간별 탐지 건수</div>
                <div className="flex items-end gap-1 h-16">
                  {detail.hourly.map((h, i) => {
                    const maxC = Math.max(...detail.hourly.map((x) => x.count), 1)
                    const pct = (h.count / maxC) * 100
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center gap-1">
                        <div
                          className="w-full bg-cyan-500/50 rounded-sm"
                          style={{ height: `${Math.max(4, pct)}%` }}
                          title={`${h.bucket.slice(11, 16)} : ${h.count}건`}
                        />
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 종목 목록 */}
            {detail.stocks.length > 0 ? (
              <div>
                <div className="text-xs text-[var(--muted)] mb-2 font-medium">관련 종목 ({detail.stocks.length}개)</div>
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {detail.stocks.map((s) => (
                    <div key={s.code}
                      className="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--bg)] hover:bg-[var(--border)] transition-colors">
                      <div>
                        <span className="text-sm font-medium text-[var(--fg)]">{s.name}</span>
                        <span className="text-xs text-[var(--muted)] ml-2">{s.code}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
                        <span><BarChart2 size={11} className="inline mr-0.5" />{s.event_count}건</span>
                        <span className="text-cyan-400 font-semibold tabular">{s.max_score.toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)] text-center py-4">관련 종목 없음</p>
            )}
          </>
        )}
      </CardBody>
    </Card>
  )
}
