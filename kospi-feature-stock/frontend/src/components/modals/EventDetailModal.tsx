import { X, FileText, ExternalLink } from 'lucide-react'
import { clsx } from 'clsx'
import { useQuery } from '@tanstack/react-query'
import { fmt, pctColor } from '@/lib/utils'
import { disclosuresApi } from '@/api/disclosures'
import type { FeatureEvent } from '@/types'

export const EVENT_META: Record<string, { title: string; icon: string; summary: string }> = {
  VOLUME_SURGE:          { title: '거래량 급증',             icon: '📊', summary: '평소보다 이례적으로 높은 거래량이 집중된 종목' },
  AMOUNT_SURGE:          { title: '거래대금 급증',           icon: '💰', summary: '시가총액 대비 거래대금이 급증한 종목' },
  BREAKOUT_52W:          { title: '52주 신고가 돌파',        icon: '🏆', summary: '1년간 최고가를 돌파한 강력한 상승 모멘텀' },
  BREAKOUT_26W:          { title: '26주(6개월) 신고가 돌파', icon: '📈', summary: '6개월 기준 최고가 돌파, 중기 상승 추세 전환 신호' },
  BREAKOUT_13W:          { title: '13주(분기) 신고가 돌파',  icon: '📈', summary: '분기 기준 최고가 돌파, 단기 모멘텀 강화' },
  BREAKOUT_20D:          { title: '20일 신고가 돌파',        icon: '📈', summary: '20거래일(약 1개월) 최고가 돌파, 단기 추세 우위' },
  VI_TRIGGERED:          { title: '변동성 완화장치(VI) 발동', icon: '⚡', summary: '2분간 단일가 매매 전환, 급격한 주가 변동 발생' },
  LONG_WHITE_CANDLE:     { title: '장대 양봉',               icon: '🕯️', summary: '전 거래일 대비 강한 상승 마감, 매수 우위 캔들' },
  HAMMER_CANDLE:         { title: '망치형 캔들',             icon: '🔨', summary: '하락 후 하단 지지 확인, 반전 가능성 캔들 패턴' },
  MORNING_STAR:          { title: '모닝스타 패턴',           icon: '⭐', summary: '3봉 반전 패턴, 하락 추세 종료 신호' },
  SUPPLY_ANOMALY:        { title: '수급 이상 징후',          icon: '🔍', summary: '외국인·기관 순매수/순매도 이상 집중' },
  POST_DISCLOSURE_SURGE: { title: '공시 후 급등',            icon: '📢', summary: '공시 발표 이후 주가·거래량이 동반 급등' },
}

export function buildEventNarrative(f: {
  event_type: string; price?: number; change_rate?: number
  volume_ratio?: number; signal_score?: number; amount?: number
}): string {
  const price    = fmt.price(f.price)
  const chg      = f.change_rate != null
    ? `${f.change_rate >= 0 ? '+' : ''}${f.change_rate.toFixed(2)}%`
    : '—'
  const volRatio = f.volume_ratio != null ? `${f.volume_ratio.toFixed(1)}배` : '—'
  const score    = f.signal_score != null ? f.signal_score.toFixed(2) : '—'
  const amt      = fmt.amount(f.amount)

  switch (f.event_type) {
    case 'VOLUME_SURGE':
      return `20일 평균 거래량 대비 ${volRatio}의 이례적 거래량이 탐지됐습니다. 탐지 시각 주가는 ${price}(${chg})이었으며, 이 수준의 거래량 폭발은 기관·외국인의 대규모 매집이나 테마 재료 유입의 전조로 해석되는 경우가 많습니다. 거래량 급증 후 2~5거래일 내 방향성이 결정되는 패턴이 반복되므로, 당일 종가 및 익일 시가 흐름을 집중 관찰하세요. 신호 강도 ${score}는 과거 동일 패턴 대비 신뢰도를 나타냅니다.`
    case 'AMOUNT_SURGE':
      return `탐지 시각 기준 거래대금 ${amt}이 집중됐습니다. 거래대금 급증은 단순 거래량 증가보다 실질적인 자금 유입 규모를 반영하며, 기관 및 외국인의 순매수 여부와 함께 확인 시 신뢰도가 높아집니다. 탐지 시 주가 ${price}(${chg}), 신호 강도 ${score}.`
    case 'BREAKOUT_52W':
      return `${price}에서 52주(1년) 최고가를 돌파했습니다. 연간 신고가 돌파는 장기 기술적 저항선이 지지선으로 전환되는 전형적인 추세 추종 진입 시점입니다. 역사적으로 이 패턴은 추세 지속 시 수개월 이상의 상승 모멘텀이 이어지는 경향이 있으나, 반락 시 전 고가 부근이 강한 저항 구간이 됩니다. 등락률 ${chg}, 신호 강도 ${score}.`
    case 'BREAKOUT_26W':
      return `${price}에서 26주(6개월) 최고가를 돌파했습니다. 중기 저항선 돌파로, 수급 균형이 매수 우위로 전환되고 있음을 시사합니다. 52주 신고가 돌파 전 선행 지표로 활용되며, 돌파 이후 거래량 지속 여부가 추세 확인의 핵심입니다. 등락률 ${chg}, 신호 강도 ${score}.`
    case 'BREAKOUT_13W':
      return `${price}에서 13주(1분기) 최고가를 돌파했습니다. 단기 고점 돌파로, 분기 실적 발표 전후 또는 테마 재료 초기 단계에 자주 나타납니다. 거래량이 뒷받침되는 돌파는 짧은 기간 내 추가 상승 가능성을 높입니다. 신호 강도 ${score}.`
    case 'BREAKOUT_20D':
      return `${price}에서 20거래일 최고가를 돌파했습니다. 단기 추세 전환의 1차 신호로, 이후 60일선과 볼린저 밴드 상단 돌파 여부를 함께 확인하면 추세 강도를 가늠할 수 있습니다. 등락률 ${chg}, 신호 강도 ${score}.`
    case 'VI_TRIGGERED':
      return `주가가 기준가 대비 급격히 변동하여 변동성 완화장치(VI)가 발동됐습니다. 탐지 시 주가 ${price}(${chg}). VI 발동 후 2분간 단일가 매매로 전환되어 주가 안정을 유도하며, 발동 방향(상승 VI·하락 VI)에 따라 추세 방향이 결정되는 경우가 많습니다. 상승 VI 해제 후 매수세 유지 여부, 하락 VI 후 반등 강도를 확인하세요.`
    case 'LONG_WHITE_CANDLE':
      return `탐지 시각 기준 장대 양봉이 형성됐습니다. 주가 ${price}(${chg}). 당일 시가 대비 강한 상승 마감은 매수 우위 심리를 반영하며, 특히 전일 음봉 이후 발생한 장대 양봉이나 횡보 구간 이탈 후 발생한 경우 신뢰도가 높습니다. 거래량 ${volRatio}이 수반됐는지 함께 확인하세요.`
    case 'HAMMER_CANDLE':
      return `망치형 캔들이 탐지됐습니다. 주가 ${price}(${chg}). 하락 추세 또는 지지선 근방에서 발생한 망치형 캔들은 매도 압력 소진과 저점 지지 확인을 의미합니다. 다음 거래일 갭 상승 여부 또는 전고점 회복 시 반전 신호 확정으로 판단합니다.`
    case 'MORNING_STAR':
      return `3봉 반전 패턴(모닝스타)이 탐지됐습니다. 주가 ${price}(${chg}). 하락 추세 이후 소형 바디 캔들과 장대 양봉이 연속 형성된 패턴으로, 매도 세력 약화와 매수 세력 출현을 동시에 보여줍니다. 세 번째 봉의 종가가 첫 번째 봉의 중간 이상을 회복하면 패턴 완성도가 높습니다.`
    case 'SUPPLY_ANOMALY':
      return `외국인 또는 기관의 수급 이상이 탐지됐습니다. 탐지 시 주가 ${price}(${chg}). 수급 이상은 대형 기관의 전략적 매집이나 외국인 집중 매수·매도를 의미하며, 수급 주체 확인 후 대응 전략을 수립해야 합니다. 거래량 비율 ${volRatio}, 신호 강도 ${score}.`
    case 'POST_DISCLOSURE_SURGE':
      return `공시 발표 이후 주가와 거래량이 동반 급등했습니다. 탐지 시 주가 ${price}(${chg}), 거래량 비율 ${volRatio}. 아래 공시 내용을 확인하여 모멘텀의 지속 여부와 추가 재료 유무를 판단하세요.`
    default:
      return `${f.event_type} 이벤트가 탐지됐습니다. 탐지 시 주가 ${price}(${chg}), 거래량 비율 ${volRatio}, 신호 강도 ${score}.`
  }
}


const _CAT_KO_DISC: Record<string, string> = { favorable: '호재', unfavorable: '악재', neutral: '중립' }

function PostDisclosureNarrativeText({
  code, detectedAt, event,
}: {
  code: string; detectedAt: string
  event: { price?: number; change_rate?: number; volume_ratio?: number }
}) {
  const { data } = useQuery({
    queryKey: ['disclosures-event', code],  // DisclosurePanel과 캐시 공유
    queryFn:  () => disclosuresApi.list({ code, hours: 168, limit: 5 }),
    staleTime: 60_000,
  })

  const price    = fmt.price(event.price)
  const chg      = event.change_rate != null
    ? `${event.change_rate >= 0 ? '+' : ''}${event.change_rate.toFixed(2)}%` : '—'
  const volRatio = event.volume_ratio != null ? `${event.volume_ratio.toFixed(1)}배` : '—'

  const detected = new Date(detectedAt).getTime()
  const best = (data ?? []).find(
    (d) => Math.abs(new Date(d.disclosed_at).getTime() - detected) <= 72 * 3600 * 1000
  )

  const base = `공시 발표 이후 주가와 거래량이 동반 급등했습니다. 탐지 시 주가 ${price}(${chg}), 거래량 비율 ${volRatio}.`

  if (!best) {
    return <>{base} 연관 공시 내용을 확인하여 모멘텀의 지속 여부와 추가 재료 유무를 판단하세요.</>
  }

  const catKo   = _CAT_KO_DISC[best.category ?? ''] ?? '미분류'
  const scoreStr = best.sentiment_score != null && Math.abs(best.sentiment_score) >= 0.05
    ? ` · 감성점수 ${best.sentiment_score >= 0 ? '+' : ''}${best.sentiment_score.toFixed(2)}`
    : ''
  const kwStr   = best.keywords?.slice(0, 3).join(', ')
  const advice  = best.category === 'favorable'
    ? '호재성 공시로 모멘텀 지속 가능성이 높습니다. 추가 재료 소진 여부를 확인하며 단계적으로 접근하세요.'
    : best.category === 'unfavorable'
    ? '악재성 공시임에도 급등이 발생했습니다. 단기 반등에 그칠 수 있으므로 손절 원칙을 철저히 지키세요.'
    : '수급 흐름과 거래량 지속 여부를 확인하여 모멘텀 지속 여부를 판단하세요.'

  return (
    <>
      {base} 관련 공시 <strong className="font-semibold">&ldquo;{best.title}&rdquo;</strong>({catKo}{scoreStr})이
      급등의 직접적 원인으로 식별됩니다.{kwStr ? ` 주요 키워드: ${kwStr}.` : ''} {advice}
    </>
  )
}

function DisclosurePanel({ code, detectedAt }: { code: string; detectedAt: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['disclosures-event', code],
    queryFn: () => disclosuresApi.list({ code, hours: 168, limit: 5 }),
    staleTime: 60_000,
  })

  // detectedAt 기준 ±72h 이내 공시만 필터
  const detected = new Date(detectedAt).getTime()
  const filtered = (data ?? []).filter((d) => {
    const t = new Date(d.disclosed_at).getTime()
    return Math.abs(t - detected) <= 72 * 3600 * 1000
  }).slice(0, 3)

  if (isLoading) return (
    <div className="h-10 rounded-xl skeleton" />
  )
  if (!filtered.length) return (
    <div className="text-xs text-[var(--muted)] text-center py-2">연관 공시 없음</div>
  )
  return (
    <div className="space-y-2">
      {filtered.map((d) => {
        const catColor = d.category === 'favorable'
          ? 'text-red-400 bg-red-500/10 border-red-500/20'
          : d.category === 'unfavorable'
          ? 'text-blue-400 bg-blue-500/10 border-blue-500/20'
          : 'text-[var(--muted)] bg-[var(--bg)] border-[var(--border)]'
        const dartUrl = d.rcept_no
          ? `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${d.rcept_no}`
          : null
        return (
          <div key={d.id} className="bg-[var(--bg)] rounded-xl p-3.5 border border-[var(--border)]/60">
            <div className="flex items-start gap-2 mb-1.5">
              <span className={clsx('shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-full border', catColor)}>
                {d.category === 'favorable' ? '호재' : d.category === 'unfavorable' ? '악재' : '중립'}
              </span>
              <span className="text-xs text-[var(--muted)] tabular whitespace-nowrap">
                {fmt.dateTime(d.disclosed_at)}
              </span>
            </div>
            <p className="text-xs font-medium text-[var(--fg)] leading-5">{d.title}</p>
            {d.keywords && d.keywords.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1.5">
                {d.keywords.slice(0, 4).map((k) => (
                  <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    #{k}
                  </span>
                ))}
              </div>
            )}
            {dartUrl && (
              <a
                href={dartUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-400 hover:text-amber-300 transition-colors mt-2"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink size={10} />
                DART 바로가기
              </a>
            )}
          </div>
        )
      })}
    </div>
  )
}

interface EventModalProps {
  event: FeatureEvent
  onClose: () => void
  onGoDetail: () => void
}

export function EventDetailModal({ event, onClose, onGoDetail }: EventModalProps) {
  const meta      = EVENT_META[event.event_type] ?? { title: event.event_type, icon: '🔔', summary: '' }
  const narrative = buildEventNarrative(event)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--card)] border border-[var(--border)] rounded-2xl w-full max-w-xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <span className="text-3xl leading-none">{meta.icon}</span>
            <div>
              <div className="text-base font-bold text-[var(--fg)]">{meta.title}</div>
              <div className="text-sm text-[var(--muted)] mt-0.5">{meta.summary}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="ml-4 shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--border)] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* 종목 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]/60">
          <div>
            <div className="text-lg font-bold text-[var(--fg)]">{event.name}</div>
            <div className="text-sm text-[var(--muted)] mt-0.5">{event.code} · {event.market}</div>
          </div>
          <div className="text-right">
            <div className="text-xl font-bold tabular text-[var(--fg)]">{fmt.price(event.price)}</div>
            <div className={clsx('text-base font-semibold tabular mt-0.5', pctColor(event.change_rate))}>
              {event.change_rate != null
                ? `${event.change_rate >= 0 ? '+' : ''}${event.change_rate.toFixed(2)}%`
                : '—'}
            </div>
          </div>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* 지표 4박스 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[var(--bg)] rounded-xl p-4 text-center">
              <div className="text-xs font-medium text-[var(--muted)] mb-1.5">탐지가</div>
              <div className="text-base font-bold tabular text-[var(--fg)]">{fmt.price(event.price)}</div>
            </div>
            <div className={clsx(
              'rounded-xl p-4 text-center',
              event.change_rate != null && event.change_rate >= 0 ? 'bg-red-500/10' : 'bg-blue-500/10'
            )}>
              <div className="text-xs font-medium text-[var(--muted)] mb-1.5">등락률</div>
              <div className={clsx('text-base font-bold tabular', pctColor(event.change_rate))}>
                {event.change_rate != null
                  ? `${event.change_rate >= 0 ? '+' : ''}${event.change_rate.toFixed(2)}%`
                  : '—'}
              </div>
            </div>
            <div className="bg-[var(--bg)] rounded-xl p-4 text-center">
              <div className="text-xs font-medium text-[var(--muted)] mb-1.5">거래량 비율</div>
              <div className="text-base font-bold tabular text-cyan-400">
                {event.volume_ratio != null ? `${event.volume_ratio.toFixed(1)}배` : '—'}
              </div>
            </div>
            <div className="bg-[var(--bg)] rounded-xl p-4 text-center">
              <div className="text-xs font-medium text-[var(--muted)] mb-1.5">신호 강도</div>
              <div className="text-base font-bold tabular text-yellow-400">
                {event.signal_score != null ? event.signal_score.toFixed(2) : '—'}
              </div>
            </div>
          </div>

          {/* 서술형 분석 */}
          <div className="bg-[var(--bg)] rounded-xl p-5 border border-[var(--border)]/60">
            <div className="text-sm font-semibold text-[var(--fg)] mb-3">📋 이벤트 분석</div>
            <p className="modal-narrative text-sm text-[var(--fg)] leading-7">
              {event.event_type === 'POST_DISCLOSURE_SURGE'
                ? <PostDisclosureNarrativeText
                    code={event.code}
                    detectedAt={event.detected_at}
                    event={event}
                  />
                : narrative}
            </p>
          </div>

          {/* 공시 후 급등: 실제 공시 내용 */}
          {event.event_type === 'POST_DISCLOSURE_SURGE' && (
            <div className="bg-[var(--bg)] rounded-xl p-5 border border-amber-500/30">
              <div className="flex items-center gap-2 mb-3">
                <FileText size={14} className="text-amber-400" />
                <span className="text-sm font-semibold text-amber-400">연관 공시</span>
              </div>
              <DisclosurePanel code={event.code} detectedAt={event.detected_at} />
            </div>
          )}

          {/* 하단 */}
          <div className="flex items-center justify-between pt-1">
            <span className="text-sm text-[var(--muted)]">탐지 당시 가격 기준</span>
            <button
              onClick={onGoDetail}
              className="text-sm font-medium text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1"
            >
              종목 상세 보기 →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}