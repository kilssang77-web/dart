import { http } from './client'

export interface NewsStockLink {
  code: string
  name: string
}

export interface NewsItem {
  id:               number
  codes?:           string[]
  stock_links?:     NewsStockLink[]
  corp_name?:       string
  title:            string
  content?:         string
  url?:             string
  source?:          string
  published_at:     string
  category?:        'favorable' | 'unfavorable' | 'neutral'
  sentiment_score?: number
  keywords?:        string[]
}

export const newsApi = {
  list: (params?: {
    code?:     string
    category?: string
    hours?:    number
    limit?:    number
    offset?:   number
    source?:   string
  }) =>
    http.get<NewsItem[]>('/news', { params }).then((r) => r.data),

  getSources: (hours = 72) =>
    http.get<string[]>('/news/sources', { params: { hours } }).then((r) => r.data),

  getSimilar: (newsId: number, topK = 5) =>
    http.get<NewsItem[]>(`/news/${newsId}/similar`, { params: { top_k: topK } }).then((r) => r.data),
}
