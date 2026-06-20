function _parseKST(iso: string) {
  // naive ISO (no tz): treat as KST, extract components directly
  // tz-aware (Z or +hh:mm): let the browser convert (all users are KST)
  const hasTz = iso.endsWith('Z') || iso.indexOf('+', 10) >= 0
  if (!hasTz) {
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso)
    if (!m) return null
    return { year: +m[1], month: +m[2], day: +m[3], hours: +m[4], minutes: +m[5] }
  }
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(), hours: d.getHours(), minutes: d.getMinutes() }
}

function _todayKST() {
  const now = new Date()
  // KST = UTC+9
  const kst = new Date(now.getTime() + 9 * 3600 * 1000)
  return { year: kst.getUTCFullYear(), month: kst.getUTCMonth() + 1, day: kst.getUTCDate() }
}

export const fmt = {
  price: (v?: number | null) =>
    v == null ? '—' : v.toLocaleString('ko-KR'),

  pct: (v?: number | null) =>
    v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`,

  vol: (v?: number | null) => {
    if (v == null) return '—'
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
    if (v >= 1_000)     return `${(v / 1_000).toFixed(0)}K`
    return String(v)
  },

  amount: (v?: number | null) => {
    if (v == null) return '—'
    if (v >= 1_000_000_000_000) return `${(v / 1_000_000_000_000).toFixed(1)}조`
    if (v >= 100_000_000)       return `${(v / 100_000_000).toFixed(1)}억`
    if (v >= 10_000)            return `${(v / 10_000).toFixed(0)}만`
    return v.toLocaleString('ko-KR')
  },

  prob: (v?: number | null) =>
    v == null ? '—' : `${(v * 100).toFixed(1)}%`,

  time: (iso?: string | null) => {
    if (!iso) return '—'
    const p = _parseKST(iso)
    if (!p) return '—'
    return `${p.hours.toString().padStart(2, '0')}:${p.minutes.toString().padStart(2, '0')}`
  },

  date: (iso?: string | null) => {
    if (!iso) return '—'
    const p = _parseKST(iso)
    if (!p) return '—'
    return `${p.month}/${p.day}`
  },

  dateTime: (iso?: string | null) => {
    if (!iso) return '—'
    const p = _parseKST(iso)
    if (!p) return '—'
    return `${p.month}/${p.day} ${p.hours.toString().padStart(2, '0')}:${p.minutes.toString().padStart(2, '0')}`
  },

  // 스마트 시각: 오늘=HH:mm, 어제=어제 HH:mm, 그 이전=MM/DD HH:mm
  smartTime: (iso?: string | null) => {
    if (!iso) return '—'
    const p = _parseKST(iso)
    if (!p) return '—'
    const today = _todayKST()
    const hm = `${p.hours.toString().padStart(2, '0')}:${p.minutes.toString().padStart(2, '0')}`
    if (p.year === today.year && p.month === today.month && p.day === today.day) {
      return hm
    }
    // 어제 판정
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    const yKST = new Date(yesterday.getTime() + 9 * 3600 * 1000)
    if (p.year === yKST.getUTCFullYear() && p.month === yKST.getUTCMonth() + 1 && p.day === yKST.getUTCDate()) {
      return `어제 ${hm}`
    }
    return `${p.month}/${p.day} ${hm}`
  },
}

export function pctColor(v?: number | null) {
  if (v == null || v === 0) return 'text-[var(--muted)]'
  return v > 0 ? 'text-red-400' : 'text-blue-400'
}

export function probColor(v?: number | null) {
  if (v == null) return 'text-[var(--muted)]'
  if (v >= 0.55) return 'text-green-400'
  if (v >= 0.35) return 'text-orange-400'
  if (v >= 0.22) return 'text-yellow-400'
  return 'text-[var(--muted)]'
}

// ML 확률 → 1~100점 (BUY 최소 임계값 0.28 ~ 모델 상한 0.95 기준)
const _SCORE_MIN = 0.28
const _SCORE_MAX = 0.95
const _SCORE_RANGE = _SCORE_MAX - _SCORE_MIN  // 0.67

export function probToScore(prob: number): number {
  return Math.min(100, Math.max(1, Math.round(((prob - _SCORE_MIN) / _SCORE_RANGE) * 99 + 1)))
}

export function scoreToProb(score: number): number {
  return _SCORE_MIN + ((score - 1) / 99) * _SCORE_RANGE
}

export function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-300'
  if (score >= 65) return 'text-green-400'
  if (score >= 50) return 'text-orange-400'
  if (score >= 31) return 'text-yellow-400'
  return 'text-[var(--muted)]'
}

export function scoreBarColor(score: number): string {
  if (score >= 80) return 'bg-green-300'
  if (score >= 65) return 'bg-green-400'
  if (score >= 50) return 'bg-orange-400'
  if (score >= 31) return 'bg-yellow-500'
  return 'bg-zinc-500'
}

export interface RecScoreBand {
  label:         string
  stars:         string
  colorClass:    string
  barColorClass: string
}

export function recScoreBand(score: number): RecScoreBand {
  if (score >= 80) return { label: '최강매수', stars: '★★★', colorClass: 'text-green-300',      barColorClass: 'bg-green-300' }
  if (score >= 65) return { label: '강한매수', stars: '★★',  colorClass: 'text-green-400',      barColorClass: 'bg-green-400' }
  if (score >= 50) return { label: '매수',     stars: '★',   colorClass: 'text-orange-400',     barColorClass: 'bg-orange-400' }
  if (score >= 31) return { label: '중립',     stars: '',    colorClass: 'text-yellow-400',     barColorClass: 'bg-yellow-500' }
  return               { label: '위험',     stars: '',    colorClass: 'text-[var(--muted)]', barColorClass: 'bg-zinc-500' }
}
