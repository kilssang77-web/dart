import { http } from './client'

export interface SystemStatus {
  ml: {
    model_loaded: boolean
    model_mode: 'ml' | 'fallback'
    model_dir: string
    trained_at: string | null
    auc: number | null
    f1: number | null
    optimal_threshold: number | null
  }
  data: {
    latest_daily_bar: string | null
    latest_feature_event: string | null
    latest_recommendation: string | null
    latest_disclosure: string | null
    stock_count: number
    bar_count: number
    event_count: number
    vector_count: number
    rec_count: number
    disc_count: number
    pattern_vector_coverage: number
    redis_stats_count: number
  }
  services: { db: boolean; redis: boolean }
  kafka_lag: Record<string, number>
}

export interface BootstrapStep {
  id: string
  label: string
  done: boolean
  count: number | null
  target: number | null
  detail: string
}

export interface BootstrapStatus {
  steps: BootstrapStep[]
  logs: string[]
  overall_ok: boolean
}

export const adminApi = {
  getSystemStatus:    () => http.get<SystemStatus>('/admin/system-status').then(r => r.data),
  getBootstrapStatus: () => http.get<BootstrapStatus>('/admin/bootstrap-status').then(r => r.data),
  runLoadStocks:       () => http.post('/admin/bootstrap/load-stocks').then(r => r.data),
  runFetchHistorical:  () => http.post('/admin/bootstrap/fetch-historical').then(r => r.data),
  runRefreshStats:     () => http.post('/admin/bootstrap/refresh-stats').then(r => r.data),
  runTrainModel:       () => http.post('/admin/bootstrap/train-model').then(r => r.data),
  runBackfillVectors:  () => http.post('/admin/bootstrap/backfill-vectors').then(r => r.data),
}
