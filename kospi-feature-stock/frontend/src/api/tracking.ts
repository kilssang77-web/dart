import { http } from './client'

export interface TrackingItem {
  id:               number
  rec_id:           number
  code:             string
  name?:            string
  event_type?:      string
  entry_price:      number
  signal_time:      string
  r_1h?:            number
  r_3h?:            number
  r_5h?:            number
  r_1d?:            number
  r_2d?:            number
  r_3d?:            number
  r_4d?:            number
  r_5d?:            number
  r_7d?:            number
  r_10d?:           number
  r_special?:       number
  special_type?:    string
  special_date?:    string
  is_success?:      boolean
  max_return?:      number
  hit_target:       boolean
  hit_stop:         boolean
  tracking_complete: boolean
  last_updated:     string
}

export interface TrackingList {
  total:  number
  offset: number
  limit:  number
  items:  TrackingItem[]
}

export interface TrackingSummary {
  total:           number
  completed:       number
  success:         number
  fail:            number
  avg_r_1d?:       number
  avg_r_3d?:       number
  avg_r_5d?:       number
  avg_r_10d?:      number
  avg_max_return?: number
  success_rate?:   number
  hit_target_cnt:  number
  hit_stop_cnt:    number
  by_event: Array<{
    event_type: string
    cnt:        number
    win_rate?:  number
    avg_r5d?:   number
  }>
}

export const trackingApi = {
  list: (params?: { code?: string; event_type?: string; complete?: boolean; success?: boolean; limit?: number; offset?: number }) =>
    http.get<TrackingList>('/tracking', { params }).then((r) => r.data),

  summary: (days = 30) =>
    http.get<TrackingSummary>('/tracking/summary', { params: { days } }).then((r) => r.data),
}
