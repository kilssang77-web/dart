import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL ?? ''

export const http = axios.create({
  baseURL: `${BASE}/api/v1`,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail ?? err.message
    return Promise.reject(new Error(msg))
  }
)
