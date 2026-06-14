import { http } from './client'
import type { DailyBar, BacktestResult, SavedBacktestResult } from '@/types'

export interface MarketSummary {
  data_date:          string
  kospi_avg_change:   number
  kosdaq_avg_change:  number
  advancers:          number
  decliners:          number
  unchanged?:         number
  kospi_up?:          number
  kospi_down?:        number
  kosdaq_up?:         number
  kosdaq_down?:       number
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

export interface KafkaLag {
  total_lag: number
  by_topic:  Record<string, number>
  error?:    string
}

export interface ShapValue {
  feature: string
  shap:    number
}

export interface ShapExplain {
  base_value: number
  values:     ShapValue[]
  note?:      string
  error?:     string
}

export interface PerformanceTrendPoint {
  day:           string
  total:         number
  wins:          number
  win_rate:      number
  avg_return_5d: number
  avg_return_1d: number
}

export interface EventPerformance {
  event_type:    string
  total:         number
  wins:          number
  win_rate:      number
  avg_return_5d: number
  avg_return_1d: number
  avg_pred_prob: number
}

export interface ModelHistoryItem {
  id:         number
  model_type: string
  version:    string | null
  trained_at: string | null
  metrics:    Record<string, number>
  is_active:  boolean
}
export interface IndexQuote {
  code?:        string
  name:         string
  price?:       number
  change?:      number
  change_rate:  number
  open?:        number
  high?:        number
  low?:         number
  volume?:      number
}

export interface IndexLive {
  kospi:       IndexQuote
  kosdaq:      IndexQuote
  source:      'realtime' | 'daily'
  data_date?:  string
  fetched_at?: string
}

export const marketApi = {
  getSummary: () =>
    http.get<MarketSummary>('/market/summary').then((r) => r.data),

  getIndexLive: () =>
    http.get<IndexLive>('/market/index-live').then((r) => r.data),

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

  getKafkaLag: () =>
    http.get<KafkaLag>('/ml/kafka-lag').then((r) => r.data),

  getShapExplain: () =>
    http.get<ShapExplain>('/ml/shap').then((r) => r.data),

  getPerformanceTrend: (days = 30) =>
    http.get<PerformanceTrendPoint[]>('/ml/performance-trend', { params: { days } }).then((r) => r.data),

  getEventPerformance: (days = 90) =>
    http.get<EventPerformance[]>('/ml/event-performance', { params: { days } }).then((r) => r.data),

  getModelHistory: () =>
    http.get<ModelHistoryItem[]>('/ml/model-history').then((r) => r.data),

  runBacktest: (params: {
    start: string; end: string
    event_type?: string; event_types?: string[]
    market?: string
    min_score?: number; ml_min_prob?: number
    stop_loss_pct?: number; target_pct?: number
    walkforward?: boolean
  }) =>
    http.post<BacktestResult>('/backtest/run', params).then((r) => r.data),

  saveBacktestResult: (body: { name: string; params: object; result: object; equity_curve?: object[] }) =>
    http.post<{ id: number; name: string; created_at: string }>('/backtest/results', body).then((r) => r.data),

  listBacktestResults: () =>
    http.get<SavedBacktestResult[]>('/backtest/results').then((r) => r.data),

  getBacktestResult: (id: number) =>
    http.get<SavedBacktestResult>(`/backtest/results/${id}`).then((r) => r.data),

  deleteBacktestResult: (id: number) =>
    http.delete<{ deleted: number }>(`/backtest/results/${id}`).then((r) => r.data),
}

export const systemApi = {
  health: () =>
    fetch('/health').then((r) => r.json()),

  metrics: () =>
    fetch('/metrics').then((r) => r.text()),
}