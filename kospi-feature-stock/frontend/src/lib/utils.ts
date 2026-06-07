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
    const d = new Date(iso)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  },

  date: (iso?: string | null) => {
    if (!iso) return '—'
    const d = new Date(iso)
    return `${d.getMonth() + 1}/${d.getDate()}`
  },

  dateTime: (iso?: string | null) => {
    if (!iso) return '—'
    const d = new Date(iso)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  },
}

export function pctColor(v?: number | null) {
  if (v == null || v === 0) return 'text-[var(--muted)]'
  return v > 0 ? 'text-red-400' : 'text-blue-400'
}

export function probColor(v?: number | null) {
  if (v == null) return 'text-[var(--muted)]'
  if (v >= 0.7)  return 'text-green-400'
  if (v >= 0.55) return 'text-yellow-400'
  return 'text-[var(--muted)]'
}
