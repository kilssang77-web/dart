import { http } from './client'

// ── Bootstrap / Admin ─────────────────────────────────────────────────────────

export interface BootstrapStepInfo {
  count?: number
  ready?: boolean
  ok:     boolean
  label:  string
}

export interface BootstrapStatus {
  steps: {
    stocks:  BootstrapStepInfo
    bars:    BootstrapStepInfo
    model:   BootstrapStepInfo
    vectors: BootstrapStepInfo
  }
  logs:       string[]
  overall_ok: boolean
}

export const adminApi = {
  getBootstrapStatus: () =>
    http.get<BootstrapStatus>('/admin/bootstrap-status').then((r) => r.data),

  runLoadStocks: () =>
    http.post('/admin/bootstrap/load-stocks').then((r) => r.data),

  runFetchHistorical: () =>
    http.post('/admin/bootstrap/fetch-historical').then((r) => r.data),

  runTrainModel: () =>
    http.post('/admin/bootstrap/train-model').then((r) => r.data),

  runBackfillVectors: () =>
    http.post('/admin/bootstrap/backfill-vectors').then((r) => r.data),
}

export interface TelegramConfig {
  enabled:             boolean
  min_prob:            number
  max_risk:            number
  min_risk_reward:     number
  disclosure_keywords: string[]
}

export interface ModelStatus {
  mode:          'lgbm' | 'rule_based'
  model_exists:  boolean
  trained_at?:   string | null
  file_mtime?:   string | null
  feature_count?: number | null
  metrics?:      Record<string, number | null>
  warning?:      string | null
}

export const settingsApi = {
  getModelStatus: () =>
    http.get<ModelStatus>('/settings/model-status').then((r) => r.data),

  getTelegram: () =>
    http.get<TelegramConfig>('/settings/telegram').then((r) => r.data),

  updateTelegram: (cfg: TelegramConfig) =>
    http.put<TelegramConfig>('/settings/telegram', cfg).then((r) => r.data),

  addKeyword: (keyword: string) =>
    http.post<TelegramConfig>('/settings/telegram/keywords', null, { params: { keyword } }).then((r) => r.data),

  removeKeyword: (keyword: string) =>
    http.delete<TelegramConfig>(`/settings/telegram/keywords/${encodeURIComponent(keyword)}`).then((r) => r.data),
}