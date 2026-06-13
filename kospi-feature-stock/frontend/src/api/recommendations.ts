import { http } from './client'
import type { Recommendation, PerformanceStats } from '@/types'

export interface SignalItem extends Recommendation {
  fe_event_type?: string
  fe_signal_score?: number
  fe_detected_at?: string
}

export interface CodeSignalsResponse {
  total_count: number
  signals: SignalItem[]
}

export const recommendationsApi = {
  list: (params?: { action?: string; market?: string; code?: string; min_prob?: number; hours?: number; limit?: number; dedupe?: boolean }) =>
    http.get<Recommendation[]>('/recommendations', { params }).then((r) => r.data),

  getBuySignals: (min_prob = 0.55) =>
    http.get<Recommendation[]>('/recommendations/buy', { params: { min_prob } }).then((r) => r.data),

  getPerformance: (days = 30) =>
    http.get<PerformanceStats>('/recommendations/stats/performance', { params: { days } }).then((r) => r.data),

  getLatestByCode: (code: string) =>
    http.get<Recommendation>(`/recommendations/${code}/latest`).then((r) => r.data),

  codeSignals: (code: string, hours = 168) =>
    http.get<CodeSignalsResponse>(`/recommendations/${code}/signals`, { params: { hours } }).then((r) => r.data),
}