import { http } from './client'

export interface NewsItem {
  id:               number
  codes?:           string[]
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
  list: (params?: { code?: string; category?: string; hours?: number; limit?: number }) =>
    http.get<NewsItem[]>('/news', { params }).then((r) => r.data),
}
