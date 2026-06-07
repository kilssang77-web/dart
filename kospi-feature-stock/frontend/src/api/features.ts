import { http } from './client'
import type { FeatureEvent, TodaySummary } from '@/types'

export interface FeaturesParams {
  event_type?: string
  code?:       string
  market?:     string
  min_score?:  number
  hours?:      number
  limit?:      number
  dedupe?:     boolean
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

  getEventTypes: () =>
    http.get<string[]>('/features/types').then((r) => r.data),
}
