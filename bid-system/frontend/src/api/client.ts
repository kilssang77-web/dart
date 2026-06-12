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

// 401 발생 시 로그아웃 — /auth/me 또는 /auth/login 에서만 트리거
// 배경 폴링(admin/ml/status 등) 401이 세션을 끊지 않도록 엔드포인트 한정
const AUTH_LOGOUT_PATHS = ['/auth/me', '/auth/login']

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const url: string = err.config?.url ?? ''
      const isAuthEndpoint = AUTH_LOGOUT_PATHS.some((p) => url.includes(p))
      if (isAuthEndpoint && !window.location.pathname.startsWith('/login')) {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)
