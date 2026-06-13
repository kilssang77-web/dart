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

  getOrderbook: (code: string) =>
    http.get<Orderbook>(`/stocks/${code}/orderbook`).then((r) => r.data),
}

export interface OrderbookLevel {
  price: number
  qty:   number
}

export interface Orderbook {
  code:           string
  asks:           OrderbookLevel[]   // 매도 (낮은가→높은가)
  bids:           OrderbookLevel[]   // 매수 (높은가→낮은가)
  total_ask_qty:  number
  total_bid_qty:  number
  ts?:            string
}
