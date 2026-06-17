import { useState, useMemo } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  ArrowLeft, History, TrendingUp, TrendingDown, Search, ChevronRight,
  BarChart2, Info,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { featuresApi } from '@/api/features'
import type { SimilarCase } from '@/api/features'
import { CandleChart } from '@/components/charts/CandleChart'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { fmt, pctColor } from '@/lib/utils'
import type { DailyBar } from '@/types'

// ── 색상 팔레트 (유사사례 라인 구분) ──────────────────────────────────────────
const COLORS = ['#22d3ee', '#a78bfa', '#fb923c', '#4ade80', '#f472b6', '#facc15']

// ── 일봉 데이터를 "이벤트 기준 정규화 (=100)" ─────────────────────────────────
function normalizeBars(bars: DailyBar[], eventDate: string): { day: number; price: number }[] {
  if (!bars || bars.length === 0) return []
  const pivot = new Date(eventDate.slice(0, 10))
  const baseBar = bars.find((b) => b.date >= eventDate.slice(0, 10)) ?? bars[0]
  const basePrice = baseBar?.close ?? 1
  return bars.map((b) => {
    const d = new Date(b.date)
    const dayOffset = Math.round((d.getTime() - pivot.getTime()) / 86_400_000)
    return { day: dayOffset, price: +((b.close / basePrice) * 100).toFixed(2) }
  })
}

// ── 수익률 배지 ──────────────────────────────────────────────────────────────
function RetBadge({ value, label }: { value?: number | null; label: string }) {
  if (value == null) return null
  return (
    <div className="text-center">
      <div className="text-xs text-[var(--muted)] mb-0.5">{label}</div>
      <div className={clsx('text-sm font-bold tabular', pctColor(value))}>
        {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}%
      </div>
    </div>
  )
}

// ── 오버레이 차트: 현재 + 유사사례 정규화 선 ──────────────────────────────────
function OverlayChart({
  eventBars,
  eventDate,
  cases,
}: {
  eventBars: DailyBar[]
  eventDate: string
  cases: SimilarCase[]
}) {
  const series = useMemo(() => {
    const result: { key: string; label: string; color: string; data: { day: number; price: number }[] }[] = []
    if (eventBars.length > 0) {
      result.push({
        key:   'current',
        label: '현재',
        color: '#ffffff',
        data:  normalizeBars(eventBars, eventDate),
      })
    }
    cases.forEach((c, i) => {
      if (!c.bars || c.bars.length === 0) return
      result.push({
        key:   `case-${i}`,
        label: `${c.code} (${c.detected_at?.slice(0, 10)})`,
        color: COLORS[i % COLORS.length],
        data:  normalizeBars(c.bars, c.detected_at),
      })
    })
    return result
  }, [eventBars, eventDate, cases])

  // 모든 day 값을 합쳐서 x축 구성
  const allDays = useMemo(() => {
    const daySet = new Set<number>()
    series.forEach((s) => s.data.forEach((d) => daySet.add(d.day)))
    return Array.from(daySet).sort((a, b) => a - b)
  }, [series])

  // recharts용 데이터 (day 기준 조인)
  const chartData = useMemo(() => {
    const byDay: Record<number, Record<string, number>> = {}
    allDays.forEach((day) => { byDay[day] = { day } })
    series.forEach((s) => {
      s.data.forEach(({ day, price }) => {
        if (byDay[day]) byDay[day][s.key] = price
      })
    })
    return allDays.map((day) => byDay[day])
  }, [allDays, series])

  if (series.length === 0) return (
    <div className="h-48 flex items-center justify-center text-sm text-[var(--muted)]">
      차트 데이터 없음
    </div>
  )

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="day"
          tick={{ fontSize: 11, fill: '#71717a' }}
          tickFormatter={(v) => `${v >= 0 ? '+' : ''}${v}일`}
        />
        <YAxis
          domain={['auto', 'auto']}
          tick={{ fontSize: 11, fill: '#71717a' }}
          tickFormatter={(v) => `${v}%`}
          width={48}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 8, fontSize: 12,
          }}
          formatter={(v: number) => [`${v.toFixed(1)}%`]}
          labelFormatter={(l) => `이벤트 기준 ${l >= 0 ? '+' : ''}${l}일`}
        />
        <ReferenceLine x={0} stroke="#71717a" strokeDasharray="4 4" label={{ value: '이벤트', fill: '#71717a', fontSize: 11 }} />
        <ReferenceLine y={100} stroke="#71717a" strokeDasharray="2 2" />
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            stroke={s.color}
            strokeWidth={s.key === 'current' ? 2.5 : 1.5}
            dot={false}
            connectNulls
            opacity={s.key === 'current' ? 1 : 0.7}
          />
        ))}
        <Legend
          formatter={(value) => {
            const s = series.find((x) => x.key === value)
            return <span style={{ color: s?.color, fontSize: 11 }}>{s?.label ?? value}</span>
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── 개별 유사사례 카드 ─────────────────────────────────────────────────────────
function CaseCard({ sc, rank, color }: { sc: SimilarCase; rank: number; color: string }) {
  const best = sc.result_5d ?? sc.result_3d ?? sc.result_1d
  const eventBars: DailyBar[] = sc.bars ?? []

  return (
    <Card>
      <CardBody>
        {/* 헤더 */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <div
              className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
              style={{ backgroundColor: color + '33', color }}
            >
              {rank}
            </div>
            <div>
              <div className="font-bold text-[var(--fg)]">{sc.name ?? sc.code}</div>
              <div className="text-xs text-[var(--muted)]">{sc.code} · {sc.detected_at?.slice(0, 10)}</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-[var(--muted)] mb-0.5">유사도</div>
            <div className="text-sm font-bold" style={{ color }}>
              {(sc.similarity * 100).toFixed(0)}%
            </div>
          </div>
        </div>

        {/* 수익률 */}
        <div className="grid grid-cols-3 gap-2 mb-3 bg-[var(--bg)] rounded-xl p-3">
          <RetBadge value={sc.result_1d} label="1일" />
          <RetBadge value={sc.result_3d} label="3일" />
          <RetBadge value={sc.result_5d} label="5일" />
        </div>

        {/* 이벤트 타입 */}
        {sc.event_type && (
          <div className="mb-3">
            <Badge eventType={sc.event_type} size="sm" />
          </div>
        )}

        {/* 미니 캔들 차트 */}
        {eventBars.length > 0 && (
          <CandleChart data={eventBars} height={140} showMA={false} />
        )}
        {eventBars.length === 0 && (
          <div className="h-12 flex items-center justify-center text-xs text-[var(--muted)]">
            차트 데이터 없음
          </div>
        )}
      </CardBody>
    </Card>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export function SimilarCases() {
  const nav = useNavigate()
  const { eventId: paramEventId } = useParams<{ eventId?: string }>()
  const [searchParams] = useSearchParams()
  const qEventId = searchParams.get('event_id')
  const eventId  = paramEventId ?? qEventId ?? null

  // 이벤트 ID가 없을 때: 최근 특징주 목록 표시
  const { data: recentEvents, isLoading: listLoading } = useQuery({
    queryKey: ['features-for-similar'],
    queryFn:  () => featuresApi.list({ min_score: 0.6, hours: 72, limit: 30, dedupe: true }),
    enabled:  eventId == null,
    staleTime: 120_000,
  })

  // 이벤트 ID가 있을 때: 유사사례 + 차트 로드
  const { data, isLoading, error } = useQuery({
    queryKey: ['similar-with-bars', eventId],
    queryFn:  () => featuresApi.getSimilarWithBars(Number(eventId), 5, 5, 15),
    enabled:  eventId != null,
    staleTime: 300_000,
    retry: false,
  })

  // ── 이벤트 선택 화면 ──────────────────────────────────────────────────────
  if (!eventId) {
    return (
      <div className="p-5 space-y-4 max-w-4xl">
        <div className="flex items-center gap-3">
          <History size={20} className="text-purple-400" />
          <div>
            <h2 className="text-lg font-bold text-[var(--fg)]">유사사례 차트 비교</h2>
            <p className="text-sm text-[var(--muted)]">분석할 특징주 이벤트를 선택하세요</p>
          </div>
        </div>

        {listLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-14 skeleton rounded-xl" />)}
          </div>
        ) : (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
            {recentEvents?.map((ev) => (
              <button
                key={ev.id}
                className="w-full flex items-center gap-4 px-5 py-4 border-b border-[var(--border)]/50 hover:bg-[var(--border)]/30 transition-colors text-left"
                onClick={() => nav(`/similar-cases/${ev.id}`)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-[var(--fg)]">{ev.name}</span>
                    <code className="text-xs text-[var(--muted)] font-mono">{ev.code}</code>
                    <Badge eventType={ev.event_type} size="sm" />
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-0.5">{fmt.dateTime(ev.detected_at)}</div>
                </div>
                <div className="flex items-center gap-4 shrink-0">
                  <div className="text-right">
                    <div className="text-xs text-[var(--muted)]">신호 점수</div>
                    <div className="text-sm font-bold text-cyan-400 tabular">{ev.signal_score?.toFixed(2) ?? '—'}</div>
                  </div>
                  {ev.change_rate != null && (
                    <div className={clsx('text-sm font-bold tabular', pctColor(ev.change_rate))}>
                      {ev.change_rate >= 0 ? '+' : ''}{ev.change_rate.toFixed(2)}%
                    </div>
                  )}
                  <ChevronRight size={16} className="text-[var(--muted)]" />
                </div>
              </button>
            ))}
            {!listLoading && !recentEvents?.length && (
              <div className="py-12 text-center text-sm text-[var(--muted)]">
                최근 72시간 내 이벤트 없음
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // ── 로딩 / 에러 ──────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="p-5 space-y-4">
        <div className="h-20 skeleton rounded-xl" />
        <div className="h-64 skeleton rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-64 skeleton rounded-xl" />)}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-5 flex flex-col items-center justify-center py-24 gap-3 text-[var(--muted)]">
        <BarChart2 size={32} className="opacity-30" />
        <p className="text-sm">유사사례 데이터를 불러올 수 없습니다.</p>
        <button onClick={() => nav('/similar-cases')} className="text-sm text-cyan-400 hover:underline">
          이벤트 목록으로 돌아가기
        </button>
      </div>
    )
  }

  const { event, event_bars, cases } = data
  const avgReturn = cases.length > 0
    ? cases.reduce((s, c) => s + (c.result_5d ?? c.result_3d ?? 0), 0) / cases.length
    : null
  const successCount = cases.filter((c) => (c.result_5d ?? c.result_3d ?? 0) > 0).length

  return (
    <div className="p-5 space-y-5 max-w-[1400px]">

      {/* 상단 헤더 */}
      <div className="flex items-start gap-4">
        <button
          onClick={() => nav('/similar-cases')}
          className="mt-1 p-1.5 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-xl font-bold text-[var(--fg)]">
              {event.name ?? event.code} 유사사례 분석
            </h2>
            <Badge eventType={event.event_type} />
          </div>
          <div className="text-sm text-[var(--muted)] mt-1">
            {fmt.dateTime(event.detected_at)} · 신호 점수 {event.signal_score?.toFixed(2) ?? '—'}
          </div>
        </div>
        {/* 집계 통계 */}
        <div className="flex items-center gap-6 bg-[var(--card)] border border-[var(--border)] rounded-xl px-5 py-3 shrink-0">
          <div className="text-center">
            <div className="text-xs text-[var(--muted)] mb-0.5">검색 케이스</div>
            <div className="text-lg font-bold text-cyan-400 tabular">{cases.length}건</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-[var(--muted)] mb-0.5">성공(양전) 비율</div>
            <div className="text-lg font-bold text-green-400 tabular">
              {cases.length > 0 ? Math.round((successCount / cases.length) * 100) : 0}%
            </div>
          </div>
          {avgReturn != null && (
            <div className="text-center">
              <div className="text-xs text-[var(--muted)] mb-0.5">평균 수익률</div>
              <div className={clsx('text-lg font-bold tabular', pctColor(avgReturn))}>
                {avgReturn >= 0 ? '+' : ''}{(avgReturn * 100).toFixed(1)}%
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 차트 2열: 현재 캔들 + 오버레이 비교 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* 현재 이벤트 캔들 차트 */}
        <Card>
          <CardHeader>
            <CardTitle>현재 이벤트 — {event.name ?? event.code}</CardTitle>
          </CardHeader>
          <CardBody>
            {event_bars.length > 0
              ? <CandleChart data={event_bars} height={220} showMA />
              : <div className="h-48 flex items-center justify-center text-sm text-[var(--muted)]">차트 데이터 없음</div>
            }
          </CardBody>
        </Card>

        {/* 오버레이 비교 차트 */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>이벤트 기준 수익률 비교</CardTitle>
              <span className="flex items-center gap-1 text-xs text-[var(--muted)]">
                <Info size={11} />이벤트일 종가 = 100
              </span>
            </div>
          </CardHeader>
          <CardBody>
            <OverlayChart
              eventBars={event_bars}
              eventDate={event.detected_at}
              cases={cases}
            />
          </CardBody>
        </Card>
      </div>

      {/* 유사사례 개별 카드 */}
      {cases.length > 0 ? (
        <>
          <div className="flex items-center gap-2">
            <History size={16} className="text-purple-400" />
            <h3 className="text-base font-bold text-[var(--fg)]">유사 과거 사례 TOP {cases.length}</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {cases.map((sc, i) => (
              <CaseCard key={`${sc.code}-${i}`} sc={sc} rank={i + 1} color={COLORS[i % COLORS.length]} />
            ))}
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-[var(--muted)] bg-[var(--card)] border border-[var(--border)] rounded-xl">
          <Search size={28} className="opacity-30" />
          <p className="text-sm">
            유사한 과거 패턴이 아직 축적되지 않았습니다.
            <br />시스템이 운영되어 데이터가 쌓이면 자동으로 표시됩니다.
          </p>
        </div>
      )}
    </div>
  )
}
