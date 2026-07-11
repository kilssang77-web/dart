import axios from 'axios'

const BASE    = import.meta.env.VITE_API_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

const _baseHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
if (API_KEY) _baseHeaders['X-API-Key'] = API_KEY

export const http = axios.create({
  baseURL: `${BASE}/api/v1`,
  timeout: 30_000,
  headers: _baseHeaders,
})

export const httpLong = axios.create({
  baseURL: `${BASE}/api/v1`,
  timeout: 180_000,
  headers: _baseHeaders,
})

/** 요청 인터셉터: localStorage의 JWT 토큰을 Authorization 헤더에 주입 */
function _injectToken(config: import('axios').InternalAxiosRequestConfig) {
  try {
    const raw = localStorage.getItem('quant-eye-auth')
    if (raw) {
      const { state } = JSON.parse(raw) as { state: { token: string | null } }
      if (state?.token) {
        config.headers = config.headers ?? {}
        config.headers['Authorization'] = `Bearer ${state.token}`
      }
    }
  } catch {
    // localStorage 파싱 실패 시 무시
  }
  return config
}

/** 응답 인터셉터: 401 → 토큰 삭제 + 로그인 페이지로 리다이렉트 */
function _handle401(error: unknown) {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    try {
      localStorage.removeItem('quant-eye-auth')
    } catch {
      // ignore
    }
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
    return Promise.reject(new Error('로그인이 필요합니다'))
  }
  const msg = axios.isAxiosError(error)
    ? (error.response?.data?.detail ?? error.message)
    : String(error)
  return Promise.reject(new Error(msg))
}

http.interceptors.request.use(_injectToken)
httpLong.interceptors.request.use(_injectToken)

http.interceptors.response.use((r) => r, _handle401)
httpLong.interceptors.response.use((r) => r, _handle401)
