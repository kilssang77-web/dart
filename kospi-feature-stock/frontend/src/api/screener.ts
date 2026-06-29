import { http } from './client'

export interface ScreenerParams {
  rsi_min?:           number
  rsi_max?:           number
  near_52w_high_pct?: number
  volume_ratio_min?:  number
  foreign_net_days?:  number
  ml_prob_min?:       number
  event_types?:       string[]
  market?:            'ALL' | 'KOSPI' | 'KOSDAQ'
  per_max?:           number
  roe_min?:           number
  limit?:             number
}

export interface ScreenerResult {
  code:             string
  name:             string
  sector:           string | null
  market:           string
  current_price:    number
  change_rate:      number
  rsi:              number | null
  volume_ratio:     number
  foreign_net_5d:   number
  ml_prob:          number | null
  per:              number | null
  roe:              number | null
  match_conditions: string[]
}

export const screenerApi = {
  run: (params: ScreenerParams) =>
    http.post<ScreenerResult[]>('/screener/run', params).then((r) => r.data),
}
