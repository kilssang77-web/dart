import { http } from './client'

// ── 백필 이력 / 스케줄 현황 ────────────────────────────────────────────────────

export interface BackfillJob {
  id: number
  job_type: string
  triggered_by: string
  status: 'running' | 'done' | 'failed' | 'pending' | 'skipped'
  target_count: number | null
  success_count: number | null
  skip_count: number | null
  fail_count: number | null
  rows_added: number | null
  started_at: string
  finished_at: string | null
  error_msg: string | null
}

export interface BackfillStatus {
  current_job: BackfillJob | null
  last_completed: BackfillJob | null
  last_run_redis: string | null
  trigger_pending: boolean
}

export interface ScheduleStatus {
  bars_backfill_last: string | null
  financials_last: string | null
  govdata_last: string | null
  stats_last_refresh: string | null
}

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

  // 백필 이력 / 스케줄 현황
  getBackfillStatus:  () => http.get<BackfillStatus>('/admin/backfill-status').then(r => r.data),
  getBackfillHistory: (limit = 20) =>
    http.get<BackfillJob[]>('/admin/backfill-history', { params: { limit } }).then(r => r.data),
  triggerBackfill:    (job_type: string) =>
    http.post('/admin/backfill/trigger', null, { params: { job_type } }).then(r => r.data),
  getScheduleStatus:  () => http.get<ScheduleStatus>('/admin/schedule-status').then(r => r.data),
}
