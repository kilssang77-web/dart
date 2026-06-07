import { http } from './client'
import type { Recommendation, PerformanceStats } from '@/types'

export const recommendationsApi = {
  list: (params?: { action?: string; market?: string; min_prob?: number; hours?: number; limit?: number }) =>
    http.get<Recommendation[]>('/recommendations', { params }).then((r) => r.data),

  getBuySignals: (min_prob = 0.55) =>
    http.get<Recommendation[]>('/recommendations/buy', { params: { min_prob } }).then((r) => r.data),

  getPerformance: (days = 30) =>
    http.get<PerformanceStats>('/recommendations/stats/performance', { params: { days } }).then((r) => r.data),

  getLatestByCode: (code: string) =>
    http.get<Recommendation>(`/recommendations/${code}/latest`).then((r) => r.data),
}
