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

// ── 사용자 관리 ──────────────────────────────────────────────────────────────
export interface UserOut {
  username:     string
  display_name: string | null
  is_active:    boolean
  created_at:   string
  last_login:   string | null
}

export async function apiListUsers(token: string): Promise<UserOut[]> {
  const res = await axios.get<UserOut[]>(`${BASE}/api/v1/auth/users`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
}

export async function apiCreateUser(
  token: string,
  username: string,
  password: string,
  displayName?: string,
): Promise<UserOut> {
  const res = await axios.post<UserOut>(
    `${BASE}/api/v1/auth/users`,
    { username, password, display_name: displayName },
    { headers: { Authorization: `Bearer ${token}` } },
  )
  return res.data
}

export async function apiUpdateUser(
  token: string,
  username: string,
  body: { display_name?: string; is_active?: boolean; new_password?: string },
): Promise<UserOut> {
  const res = await axios.put<UserOut>(
    `${BASE}/api/v1/auth/users/${username}`,
    body,
    { headers: { Authorization: `Bearer ${token}` } },
  )
  return res.data
}

export async function apiDeleteUser(token: string, username: string): Promise<void> {
  await axios.delete(`${BASE}/api/v1/auth/users/${username}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function apiChangePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await axios.post(
    `${BASE}/api/v1/auth/change-password`,
    { current_password: currentPassword, new_password: newPassword },
    { headers: { Authorization: `Bearer ${token}` } },
  )
}
