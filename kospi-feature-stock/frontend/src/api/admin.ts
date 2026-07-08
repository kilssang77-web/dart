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
    opt_f1: number | null
    opt_recall: number | null
    opt_precision: number | null
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
  services: { db: boolean; redis: boolean; ml: boolean; recommender: boolean; trader: boolean }
  redis_channels: Record<string, number>
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

export interface DataQuality {
  bar_completeness: {
    active_stocks:       number
    bars_last7d_stocks:  number
    bars_today_stocks:   number
    coverage_7d_pct:     number
    coverage_today_pct:  number
    latest_bar_date:     string | null
    missing_bars_count:  number
    missing_bars_sample: { code: string; name: string; sector: string | null; last_bar_date: string | null }[]
  }
  supply_coverage: {
    coverage_7d_stocks:  number
    coverage_30d_stocks: number
    coverage_7d_pct:     number
    coverage_30d_pct:    number
    latest_sd_date:      string | null
    missing_stocks:      number
  }
  ml_confidence: {
    model_loaded:         boolean
    auc:                  number | null
    f1:                   number | null
    trained_at:           string | null
    model_age_days:       number | null
    feature_count:        number | null
    train_samples:        number | null
    threshold:            number | null
    vector_coverage_pct:  number
  }
}

export interface PipelineStatus {
  realtime: {
    events_24h: number
    recs_24h: number
    redis_stats_keys: number
    last_stats_refresh: string | null
    status: 'ok' | 'degraded'
  }
  disclosures: { count_24h: number; status: string }
  news: { count_24h: number; with_sentiment: number; sentiment_redis_keys: number; status: string }
  ml: { events_with_result: number; events_with_vector: number; total_events: number; result_coverage_pct: number; vector_coverage_pct: number }
}

export interface TrackingSummary {
  total: number
  completed: number
  success: number
  fail: number
  avg_r_1d: number | null
  avg_r_3d: number | null
  avg_r_5d: number | null
  avg_r_10d: number | null
  avg_max_return: number | null
  success_rate: number | null
  hit_target_cnt: number
  hit_stop_cnt: number
  by_event: { event_type: string; cnt: number; win_rate: number | null; avg_r5d: number | null }[]
}

export interface DailyPnlItem {
  date: string
  avg_r5d: number
  cum_r: number
  cnt: number
  wins: number
  win_rate: number
}

export interface DailyPnl {
  items: DailyPnlItem[]
  mdd: number
  total_return: number
}

export const adminApi = {
  getSystemStatus:    () => http.get<SystemStatus>('/admin/system-status').then(r => r.data),
  getPipelineStatus:  () => http.get<PipelineStatus>('/admin/pipeline-status').then(r => r.data),
  getTrackingSummary: (days = 30) => http.get<TrackingSummary>('/tracking/summary', { params: { days } }).then(r => r.data),
  forceRefreshStats:  () => http.post('/admin/force-refresh-stats').then(r => r.data),
  triggerMlRetrain:   () => http.post('/ml/retrain').then(r => r.data),
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
  getDataQuality:     () => http.get<DataQuality>('/admin/data-quality').then(r => r.data),
  getWeeklyBacktest:  () => http.get<any>('/admin/weekly-backtest').then(r => r.data),
  getDailyPnl:        (days = 90) => http.get<DailyPnl>('/tracking/daily-pnl', { params: { days } }).then(r => r.data),
}
