import axios from 'axios'

const BASE    = import.meta.env.VITE_API_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

const headers: Record<string, string> = { 'Content-Type': 'application/json' }
if (API_KEY) headers['X-API-Key'] = API_KEY

export const http = axios.create({
  baseURL: `${BASE}/api/v1`,
  timeout: 15_000,
  headers,
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail ?? err.message
    return Promise.reject(new Error(msg))
  }
)
