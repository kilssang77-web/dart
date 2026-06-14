import { http } from './client'

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