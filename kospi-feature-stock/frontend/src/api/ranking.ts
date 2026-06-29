import { http } from './client'

export interface RankingItem {
  code:            string
  name:            string
  market:          string
  sector:          string | null
  current_price:   number
  change_pct:      number
  volume:          number
  score:           number
  ml_score:        number
  supply_score:    number
  tech_score:      number
  momentum_score:  number
  expected_return: number
  risk_level:      'LOW' | 'MEDIUM' | 'HIGH'
}

export type RankingMarket = 'ALL' | 'KOSPI' | 'KOSDAQ'
export type RankingSortBy = 'score' | 'supply_score' | 'ml_score' | 'momentum_score' | 'expected_return' | 'change_pct'

export const rankingApi = {
  getDaily: (params?: {
    market?:  RankingMarket
    limit?:   number
    sort_by?: RankingSortBy
  }) =>
    http.get<RankingItem[]>('/ranking/daily', { params }).then((r) => r.data),

  getDailyChange: () =>
    http.get<RankingItem[]>('/ranking/daily-change').then((r) => r.data),

  clearCache: () =>
    http.delete('/ranking/cache').then((r) => r.data),
}
