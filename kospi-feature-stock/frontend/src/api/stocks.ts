import { http } from './client'
import type { Stock, DailyBar, SupplyDemand, StockAnalysis } from '@/types'

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

  getSupply: (code: string, days = 30) =>
    http.get<SupplyDemand[]>(`/stocks/${code}/supply`, { params: { days } }).then((r) => r.data),

  getAnalysis: (code: string, purchasePrice?: number) =>
    http.get<StockAnalysis>(`/stocks/${code}/analysis`, {
      params: purchasePrice ? { purchase_price: purchasePrice } : undefined,
    }).then((r) => r.data),

  watchStock: (code: string) =>
    http.post(`/stocks/${code}/watch`).then((r) => r.data),
}
