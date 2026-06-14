import { http } from './client'
import type { Disclosure } from '@/types'

export interface DisclosureStats {
  total:           number
  favorable:       number
  unfavorable:     number
  neutral:         number
  avg_sentiment:   number
  positive_impact: number
  avg_1d_impact:   number
  by_type: Array<{ type: string; count: number; avg_score: number }>
}

export const disclosuresApi = {
  list: (params?: {
    code?:       string
    category?:   string
    hours?:      number
    limit?:      number
    sort_by?:    string
    sort_dir?:   'asc' | 'desc'
    min_amount?: number
  }) =>
    http.get<Disclosure[]>('/disclosures', { params }).then((r) => r.data),

  getStats: (hours = 72) =>
    http.get<DisclosureStats>('/disclosures/stats', { params: { hours } }).then((r) => r.data),

  getById: (rcept_no: string) =>
    http.get<Disclosure>(`/disclosures/${rcept_no}`).then((r) => r.data),

  predictImpact: (rcept_no: string) =>
    http.get(`/disclosures/${rcept_no}/predict-impact`).then((r) => r.data),
}
