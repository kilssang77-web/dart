import { http } from './client'
import type { FeatureEvent, TodaySummary, DailyBar } from '@/types'

export interface FeaturesParams {
  event_type?: string
  code?:       string
  market?:     string
  min_score?:  number
  hours?:      number
  limit?:      number
  dedupe?:     boolean
}

export interface SimilarCase {
  id:          number
  code:        string
  name?:       string
  detected_at: string
  event_type:  string
  similarity:  number
  result_1d?:  number
  result_3d?:  number
  result_5d?:  number
  signal_score?: number
  bars:        DailyBar[]
}

export interface SimilarWithBarsResult {
  event:      FeatureEvent
  event_bars: DailyBar[]
  cases:      SimilarCase[]
}

export const featuresApi = {
  list: (params?: FeaturesParams) =>
    http.get<FeatureEvent[]>('/features', { params }).then((r) => r.data),

  todaySummary: () =>
    http.get<TodaySummary>('/features/today/summary').then((r) => r.data),

  getById: (id: number) =>
    http.get<FeatureEvent>(`/features/${id}`).then((r) => r.data),

  getSimilar: (id: number, topK = 10) =>
    http.get<FeatureEvent[]>(`/features/${id}/similar`, { params: { top_k: topK } }).then((r) => r.data),

  getSimilarWithBars: (id: number, topK = 5, windowBefore = 5, windowAfter = 15) =>
    http.get<SimilarWithBarsResult>(`/features/${id}/similar-with-bars`, {
      params: { top_k: topK, window_before: windowBefore, window_after: windowAfter },
    }).then((r) => r.data),

  getEventTypes: () =>
    http.get<string[]>('/features/types').then((r) => r.data),
}
