import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff, TrendingUp, Lock } from 'lucide-react'
import { clsx } from 'clsx'
import { useAuthStore } from '@/store/auth'
import { apiLogin } from '@/api/auth'

export function Login() {
  const navigate           = useNavigate()
  const { token, setAuth } = useAuthStore()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw,   setShowPw]   = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  // 이미 로그인된 경우 바로 이동
  useEffect(() => {
    if (token) navigate('/', { replace: true })
  }, [token, navigate])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setLoading(true)
    setError(null)
    try {
      const res = await apiLogin(username.trim(), password)
      setAuth(res.access_token, {
        username:     username.trim(),
        display_name: res.display_name,
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }, [username, password, setAuth, navigate])

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] px-4">
      {/* 배경 그라디언트 효과 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -left-40 w-96 h-96 rounded-full bg-blue-600/10 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 w-96 h-96 rounded-full bg-purple-600/10 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        {/* 로고 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-blue-500/15 border border-blue-500/30 mb-4">
            <TrendingUp size={28} className="text-blue-400" />
          </div>
          <h1 className="text-2xl font-bold text-[var(--fg)] tracking-tight">Quant Eye</h1>
          <p className="text-xs text-[var(--muted)] mt-1">KOSPI/KOSDAQ 실시간 특징주 탐지 시스템</p>
        </div>

        {/* 카드 */}
        <div className="bg-[var(--bg2)] border border-[var(--border)] rounded-2xl p-8 shadow-2xl">
          <div className="flex items-center gap-2 mb-6">
            <Lock size={15} className="text-[var(--muted)]" />
            <span className="text-sm font-semibold text-[var(--fg)]">로그인</span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* 아이디 */}
            <div>
              <label className="block text-xs font-medium text-[var(--muted)] mb-1.5">
                아이디
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
                placeholder="아이디를 입력하세요"
                className={clsx(
                  'w-full px-3.5 py-2.5 rounded-lg text-sm',
                  'bg-[var(--bg)] border border-[var(--border)]',
                  'text-[var(--fg)] placeholder:text-[var(--muted)]/50',
                  'focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50',
                  'transition-colors'
                )}
              />
            </div>

            {/* 비밀번호 */}
            <div>
              <label className="block text-xs font-medium text-[var(--muted)] mb-1.5">
                비밀번호
              </label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  placeholder="비밀번호를 입력하세요"
                  className={clsx(
                    'w-full px-3.5 py-2.5 pr-10 rounded-lg text-sm',
                    'bg-[var(--bg)] border border-[var(--border)]',
                    'text-[var(--fg)] placeholder:text-[var(--muted)]/50',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50',
                    'transition-colors'
                  )}
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* 에러 메시지 */}
            {error && (
              <div className="px-3.5 py-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                {error}
              </div>
            )}

            {/* 로그인 버튼 */}
            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className={clsx(
                'w-full py-2.5 rounded-lg text-sm font-semibold transition-all',
                'bg-blue-600 hover:bg-blue-500 text-white',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-[var(--bg2)]'
              )}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  로그인 중...
                </span>
              ) : '로그인'}
            </button>
          </form>
        </div>

        <p className="text-center text-[10px] text-[var(--muted)]/50 mt-6">
          Quant Eye v1.0 &middot; 권한이 없는 접근은 기록됩니다
        </p>
      </div>
    </div>
  )
}
