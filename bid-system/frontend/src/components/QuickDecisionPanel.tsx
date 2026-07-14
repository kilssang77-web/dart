import { useQuery } from '@tanstack/react-query'
import { decisionApi } from '@/api'
import type { QuickDecisionResponse } from '@/types'
import { CheckCircle2, XCircle, MinusCircle, TrendingUp, AlertCircle, Users, ShieldCheck, Database, BarChart3 } from 'lucide-react'
import { cn } from '@/lib/utils'

const fmt = (n: number) => n.toLocaleString('ko-KR')

interface Props {
  bidId: number
}

const GRADE_CONFIG = {
  S: { label: '강력 GO', sub: '다수 강한 긍정 신호 확인', bg: 'bg-emerald-600', border: 'border-emerald-400', text: 'text-white', badgeBg: 'bg-emerald-500', ring: 'ring-emerald-300' },
  A: { label: 'GO', sub: '참여 권장 — 우호적 조건', bg: 'bg-emerald-500', border: 'border-emerald-400', text: 'text-white', badgeBg: 'bg-emerald-400', ring: 'ring-emerald-200' },
  B: { label: '신중 검토', sub: '중립 — 추가 확인 후 결정', bg: 'bg-amber-500', border: 'border-amber-400', text: 'text-white', badgeBg: 'bg-amber-400', ring: 'ring-amber-200' },
  C: { label: '재검토 권장', sub: '리스크 요인 점검 필요', bg: 'bg-orange-500', border: 'border-orange-400', text: 'text-white', badgeBg: 'bg-orange-400', ring: 'ring-orange-200' },
  F: { label: 'NO-GO', sub: '참여 비권장 — 불리한 조건', bg: 'bg-red-600', border: 'border-red-500', text: 'text-white', badgeBg: 'bg-red-500', ring: 'ring-red-300' },
} as const

const DATA_QUALITY_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: '전국 평균 (낮음)', color: 'text-red-500' },
  2: { label: '공종 통계 (제한)', color: 'text-orange-500' },
  3: { label: '지역/유형 통계', color: 'text-amber-600' },
  4: { label: '기관 이력 (보통)', color: 'text-blue-600' },
  5: { label: '기관 이력 (충분)', color: 'text-emerald-600' },
}

function SignalDots({ value, count = 5 }: { value: number; count?: number }) {
  const filled = Math.round(value * count)
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className={cn(
            'w-2 h-2 rounded-full',
            i < filled ? 'bg-current opacity-90' : 'bg-gray-200',
          )}
        />
      ))}
    </div>
  )
}

export default function QuickDecisionPanel({ bidId }: Props) {
  const { data, isLoading } = useQuery<QuickDecisionResponse>({
    queryKey: ['quick-decision', bidId],
    queryFn: () => decisionApi.quickDecision(bidId),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border shadow-sm p-4 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
        <div className="h-10 bg-gray-200 rounded w-2/3 mb-3" />
        <div className="h-3 bg-gray-100 rounded w-full" />
      </div>
    )
  }
  if (!data) return null

  const grade = data.grade ?? (data.go_decision === 'go' ? 'A' : data.go_decision === 'pass' ? 'F' : 'B')
  const cfg = GRADE_CONFIG[grade]
  const dql = data.data_quality_level ?? 1
  const dqlInfo = DATA_QUALITY_LABELS[dql] ?? DATA_QUALITY_LABELS[1]
  const scoreBar = Math.round(data.go_score * 100)
  const sigs = data.signals

  const GoIcon = grade === 'S' || grade === 'A' ? CheckCircle2 : grade === 'F' ? XCircle : MinusCircle

  return (
    <div className={cn('rounded-xl border-2 overflow-hidden shadow-sm', cfg.border)}>
      {/* ── 헤더: 등급 + 판정 ── */}
      <div className={cn('px-5 py-4 flex items-center gap-4', cfg.bg)}>
        {/* 등급 뱃지 */}
        <div className={cn(
          'w-14 h-14 rounded-full flex items-center justify-center shrink-0 ring-4',
          cfg.badgeBg, cfg.ring,
        )}>
          <span className="text-2xl font-black text-white leading-none">{grade}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <GoIcon className="w-5 h-5 text-white shrink-0" />
            <span className="text-lg font-bold text-white">{cfg.label}</span>
          </div>
          <div className="text-xs text-white/80 mt-0.5">{cfg.sub}</div>
          {/* 종합 점수 바 */}
          <div className="flex items-center gap-2 mt-2">
            <div className="flex-1 h-2 bg-white/30 rounded-full overflow-hidden">
              <div
                className="h-full bg-white rounded-full transition-all"
                style={{ width: `${scoreBar}%` }}
              />
            </div>
            <span className="text-xs text-white/90 font-mono shrink-0">{scoreBar}점</span>
          </div>
        </div>

        {/* 데이터 품질 */}
        <div className="shrink-0 text-right">
          <div className="text-[10px] text-white/70 mb-1">데이터 품질</div>
          <div className="flex items-center gap-0.5 justify-end">
            {Array.from({ length: 5 }, (_, i) => (
              <div
                key={i}
                className={cn('w-2.5 h-2.5 rounded-sm', i < dql ? 'bg-white' : 'bg-white/25')}
              />
            ))}
          </div>
          <div className="text-[10px] text-white/80 mt-0.5">Lv.{dql}</div>
        </div>
      </div>

      <div className="px-5 py-4 bg-white space-y-4">
        {/* ── 데이터 품질 경고 (저품질 시) ── */}
        {dql <= 2 && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2 text-xs">
            <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-amber-700">데이터 부족 — 신뢰도 제한적</span>
              <div className="text-amber-600 mt-0.5">
                이 기관의 사정율 이력이 적어 {dqlInfo.label} 기반으로 추정했습니다.
                SUCVIEW 이력 등록 시 정확도가 크게 향상됩니다.
              </div>
            </div>
          </div>
        )}

        {/* ── 추천 투찰율 & 낙찰확률 ── */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1">AI 추천 투찰율 (기초대비)</div>
            {data.recommended_rate != null ? (
              <>
                <div className="text-xl font-bold font-mono text-blue-800">
                  {(data.recommended_rate * 100).toFixed(4)}%
                </div>
                {data.recommended_amount != null && (
                  <div className="text-xs text-blue-600 mt-0.5">
                    {fmt(data.recommended_amount)}원
                  </div>
                )}
              </>
            ) : (
              <div className="text-sm text-gray-400">데이터 부족</div>
            )}
          </div>

          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              AI 낙찰 예상 확률
            </div>
            {data.win_prob != null ? (
              <div className={cn(
                'text-xl font-bold',
                data.win_prob >= 0.35 ? 'text-emerald-700' :
                data.win_prob >= 0.20 ? 'text-amber-700' : 'text-red-600',
              )}>
                {(data.win_prob * 100).toFixed(1)}%
              </div>
            ) : (
              <div className="text-sm text-gray-400">계산 불가</div>
            )}
            <div className="flex items-center gap-1 text-xs text-gray-400 mt-0.5">
              <Users className="w-3 h-3" />
              경쟁 {data.expected_competitors}개사 기준
            </div>
          </div>
        </div>

        {/* ── 5대 신호 행렬 ── */}
        {sigs && (
          <div className="border border-gray-100 rounded-lg p-3">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2.5 flex items-center gap-1">
              <BarChart3 className="w-3.5 h-3.5" />
              신호 행렬
            </div>
            <div className="space-y-2">
              {([
                { key: 'win_prob',    label: '낙찰확률',    icon: TrendingUp,  val: sigs.win_prob },
                { key: 'competition', label: '경쟁 강도',   icon: Users,       val: sigs.competition },
                { key: 'data_quality',label: '데이터 품질', icon: Database,    val: sigs.data_quality },
                { key: 'agency_rate', label: '기관 낙찰율', icon: ShieldCheck, val: sigs.agency_rate },
                { key: 'confidence',  label: '추천 신뢰도', icon: CheckCircle2,val: sigs.confidence },
              ] as const).map(({ label, icon: Icon, val }) => (
                <div key={label} className="flex items-center gap-2">
                  <Icon className="w-3 h-3 text-gray-400 shrink-0" />
                  <span className="w-20 text-xs text-gray-500 shrink-0">{label}</span>
                  <div className={cn(
                    val >= 0.7 ? 'text-emerald-600' : val >= 0.4 ? 'text-amber-600' : 'text-red-500',
                    'flex items-center gap-1 flex-1',
                  )}>
                    <SignalDots value={val} />
                  </div>
                  <span className={cn(
                    'text-[10px] font-mono w-8 text-right shrink-0',
                    val >= 0.7 ? 'text-emerald-600' : val >= 0.4 ? 'text-amber-600' : 'text-red-500',
                  )}>
                    {Math.round(val * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── 긍정 근거 ── */}
        {data.reasons.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">참여 근거</div>
            {data.reasons.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                <span>{r}</span>
              </div>
            ))}
          </div>
        )}

        {/* ── 위험 요인 ── */}
        {data.risk_factors.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">주의 요인</div>
            {data.risk_factors.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-700">
                <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                <span>{r}</span>
              </div>
            ))}
          </div>
        )}

        {/* ── 부가 정보 ── */}
        <div className="flex flex-wrap gap-3 pt-1 border-t text-xs text-gray-500">
          {data.agency_win_rate != null && (
            <span>기관 낙찰율 <strong className="text-gray-700">{(data.agency_win_rate * 100).toFixed(1)}%</strong></span>
          )}
          {data.best_rate_source && (
            <span>추천근거 <strong className="text-gray-700">{
              data.best_rate_source === 'winner+hotzone' ? '실낙찰+HotZone' :
              data.best_rate_source === 'winner'         ? '실낙찰 분포' :
              data.best_rate_source === 'hotzone+prism'  ? 'HotZone+프리즘' :
              data.best_rate_source === 'hotzone'        ? 'HotZone' :
              data.best_rate_source === 'prism'          ? '프리즘' :
                                                           '통계 추정'
            }</strong></span>
          )}
          <span>신뢰도 <strong className="text-gray-700">{Math.round(data.confidence * 100)}%</strong></span>
          <span>낙찰하한율 <strong className="font-mono text-red-600">{(data.floor_rate * 100).toFixed(4)}%</strong></span>
          <span className={cn('ml-auto font-medium', dqlInfo.color)}>
            데이터 {dqlInfo.label}
          </span>
        </div>
      </div>
    </div>
  )
}
