import { http } from './client'
import type { TelegramLog, TelegramLogList, TelegramLogStats } from '@/types'

export interface LogQuery {
  msg_type?: string
  code?:     string
  success?:  boolean
  limit?:    number
  offset?:   number
}

export const notificationsApi = {
  getLogs: async (q: LogQuery = {}): Promise<TelegramLogList> => {
    const params: Record<string, string | number | boolean> = {}
    if (q.msg_type !== undefined) params.msg_type = q.msg_type
    if (q.code     !== undefined) params.code     = q.code
    if (q.success  !== undefined) params.success  = q.success
    if (q.limit    !== undefined) params.limit    = q.limit
    if (q.offset   !== undefined) params.offset   = q.offset
    const res = await http.get('/notifications', { params })
    return res.data
  },

  getStats: async (): Promise<TelegramLogStats> => {
    const res = await http.get('/notifications/stats')
    return res.data
  },
}
