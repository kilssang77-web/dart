import { http } from './client'

export interface WatchlistItem {
  id:             number
  session_id:     string
  code:           string
  name:           string
  market:         string
  added_at:       string
  note?:          string
  current_price?: number
  change_rate?:   number
}

const SESSION_KEY = 'fstock_session_id'

export function getSessionId(): string {
  let sid = localStorage.getItem(SESSION_KEY)
  if (!sid) {
    sid = `s_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    localStorage.setItem(SESSION_KEY, sid)
  }
  return sid
}

export const watchlistApi = {
  list: (sessionId?: string): Promise<WatchlistItem[]> =>
    http.get('/watchlist', {
      params: { session_id: sessionId ?? getSessionId() },
    }).then((r) => r.data as WatchlistItem[]),

  add: (code: string, note?: string): Promise<WatchlistItem> =>
    http.post('/watchlist', {
      code,
      session_id: getSessionId(),
      note,
    }).then((r) => r.data as WatchlistItem),

  remove: (code: string): Promise<void> =>
    http.delete(`/watchlist/${code}`, {
      params: { session_id: getSessionId() },
    }).then(() => undefined),
}