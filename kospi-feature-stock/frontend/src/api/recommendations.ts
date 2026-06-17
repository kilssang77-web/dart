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

export interface ActivePerformanceItem {
  id:               number
  code:             string
  name:             string
  market:           string
  action:           string
  entry_price:      number
  target_price:     number
  stop_loss_price:  number
  success_prob:     number
  created_at:       string
  r_1d:             number | null
  r_3d:             number | null
  r_5d:             number | null
  hit_target:       boolean | null
  hit_stop:         boolean | null
}

export interface HistoryPerformanceItem {
  id:           number
  code:         string
  name:         string
  market:       string
  action:       string
  entry_price:  number
  success_prob: number
  event_type:   string | null
  created_at:   string
  r_1d:         number | null
  r_3d:         number | null
  r_5d:         number | null
  r_10d:        number | null
  max_return:   number | null
  is_success:   boolean | null
  hit_target:   boolean | null
  hit_stop:     boolean | null
}

export interface PerformanceSummary {
  total:          number
  active_count:   number
  completed:      number
  wins:           number
  hit_target:     number
  hit_stop:       number
  win_rate:       number
  avg_return_5d:  number
  avg_max_return: number
  days:           number
}

export const recommendationsApi = {
  getById: (recId: number) =>
    http.get<Recommendation>(`/recommendations/by-id/${recId}`).then((r) => r.data),

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

  getActivePerformance: () =>
    http.get<ActivePerformanceItem[]>('/recommendations/performance/active').then((r) => r.data),

  getPerformanceHistory: (days = 30, limit = 100) =>
    http.get<HistoryPerformanceItem[]>('/recommendations/performance/history', { params: { days, limit } }).then((r) => r.data),

  getPerformanceSummary: (days = 30) =>
    http.get<PerformanceSummary>('/recommendations/performance/summary', { params: { days } }).then((r) => r.data),
}