import { http } from './client'
import type { Stock, DailyBar } from '@/types'

export const stocksApi = {
  search: (q: string, market?: string) =>
    http.get<Stock[]>('/stocks', { params: { q, market, limit: 50 } }).then((r) => r.data),

  getActive: (limit = 100) =>
    http.get<Stock[]>('/stocks/active', { params: { limit } }).then((r) => r.data),

  getDetail: (code: string) =>
    http.get<Stock>(`/stocks/${code}`).then((r) => r.data),

  getDailyBars: (code: string, days = 120) =>
    http.get<DailyBar[]>(`/stocks/${code}/daily`, { params: { days } }).then((r) => r.data),

  getQuote: (code: string) =>
    http.get(`/stocks/${code}/quote`).then((r) => r.data),
}
