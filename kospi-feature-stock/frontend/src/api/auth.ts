import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL ?? ''

export interface LoginResponse {
  access_token: string
  token_type:   string
  display_name: string
}

export interface UserInfo {
  username:     string
  display_name: string
}

export async function apiLogin(username: string, password: string): Promise<LoginResponse> {
  const res = await axios.post<LoginResponse>(`${BASE}/api/v1/auth/login`, { username, password })
  return res.data
}

export async function apiGetMe(token: string): Promise<UserInfo> {
  const res = await axios.get<UserInfo>(`${BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
}

export async function apiLogout(token: string): Promise<void> {
  await axios.post(`${BASE}/api/v1/auth/logout`, {}, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
