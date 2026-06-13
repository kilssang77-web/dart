import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export const api = axios.create({
  baseURL: BASE + '/v1',
  timeout: 30_000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/* ─── 토큰 만료까지 남은 시간(ms) ─── */
export function tokenMsRemaining(): number {
  const token = localStorage.getItem('token')
  if (!token) return 0
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 - Date.now()
  } catch {
    return 0
  }
}

/* ─── 토큰 자동 갱신 ─── */
let _refreshing: Promise<void> | null = null

export async function silentRefresh(): Promise<boolean> {
  if (_refreshing) { await _refreshing; return true }
  _refreshing = (async () => {
    try {
      const res = await api.post('/auth/refresh')
      const token = res.data.access_token
      if (token) localStorage.setItem('token', token)
    } catch {
      // 갱신 실패 — 호출부에서 처리
    } finally {
      _refreshing = null
    }
  })()
  await _refreshing
  return !!localStorage.getItem('token')
}

/* ─── 401 인터셉터 — 즉시 로그아웃 대신 갱신 시도 ─── */
let _isShowingReauth = false

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const url: string = err.config?.url ?? ''

      // 로그인/갱신 요청 자체의 401 → 진짜 인증 실패
      if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
        localStorage.removeItem('token')
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login'
        }
        return Promise.reject(err)
      }

      // 그 외 401 → 토큰 갱신 1회 시도
      if (!err.config._retried) {
        err.config._retried = true
        const ok = await silentRefresh()
        if (ok) {
          // 갱신 성공 → 원래 요청 재시도
          err.config.headers.Authorization = `Bearer ${localStorage.getItem('token')}`
          return api(err.config)
        }
      }

      // 갱신도 실패 → 재로그인 안내 (페이지 이동 없이 모달)
      if (!_isShowingReauth && !window.location.pathname.startsWith('/login')) {
        _isShowingReauth = true
        const ok = window.confirm('세션이 만료되었습니다.\n확인을 누르면 로그인 페이지로 이동합니다.')
        if (ok) {
          localStorage.removeItem('token')
          window.location.href = '/login'
        }
        _isShowingReauth = false
      }
    }
    return Promise.reject(err)
  }
)
