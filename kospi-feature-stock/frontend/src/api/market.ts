import { http } from './client'
import type { DailyBar, BacktestResult } from '@/types'

export interface MarketSummary {
  data_date:          string
  kospi_avg_change:   number
  kosdaq_avg_change:  number
  advancers:          number
  decliners:          number
  unchanged?:         number
  total_volume?:      number
  total_amount?:      number
}

export interface MarketMover {
  code:        string
  name:        string
  market:      string
  sector?:     string | null
  price:       number
  change_rate: number
  volume:      number
}

export interface MarketMovers {
  gainers: MarketMover[]
  losers:  MarketMover[]
}

export interface TrendingTheme {
  theme:       string
  count:       number
  stock_count: number
  avg_score:   number
  source:      'news' | 'sector'
}

interface TrendingThemesResponse {
  hours:  number
  since:  string
  themes: TrendingTheme[]
}

export interface ModelMetrics {
  model_type:          string
  trained_at:          string
  n_features:          number
  auc:                 number
  f1:                  number
  precision:           number
  recall:              number
  accuracy:            number
  brier_score?:        number
  feature_importance?: Record<string, number>
}
export const marketApi = {
  getSummary: () =>
    http.get<MarketSummary>('/market/summary').then((r) => r.data),

  getMovers: () =>
    http.get<MarketMovers>('/market/movers').then((r) => r.data),

  getNewHighs: () =>
    http.get('/market/new-highs').then((r) => r.data),

  getForeignFlow: () =>
    http.get('/market/foreign-flow').then((r) => r.data),

  getThemes: () =>
    http.get<TrendingThemesResponse>('/themes/trending').then((r) => r.data.themes),

  getDailyBars: (code: string, days = 120) =>
    http.get<DailyBar[]>(`/stocks/${code}/daily`, { params: { days } }).then((r) => r.data),

  getModelMetrics: () =>
    http.get<ModelMetrics | null>('/ml/metrics').then((r) => r.data),

  runBacktest: (params: { start: string; end: string; event_type?: string; min_score?: number; stop_loss_pct?: number; target_pct?: number }) =>
    http.post<BacktestResult>('/backtest/run', params).then((r) => r.data),
}

export const systemApi = {
  health: () =>
    fetch('/health').then((r) => r.json()),

  metrics: () =>
    fetch('/metrics').then((r) => r.json()),
}