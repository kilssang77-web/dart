import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TrendingUp } from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function LoginPage() {
  const [email, setEmail]       = useState('admin@bid.local')
  const [password, setPassword] = useState('admin1234')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const { setToken, setUser }   = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      setToken(res.access_token)
      const me = await authApi.me()
      setUser(me)
      navigate('/dashboard')
    } catch {
      setError('이메일 또는 비밀번호가 올바르지 않습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{backgroundColor:"#f1f5f9"}}>
      <div className="w-full max-w-sm">
        {/* 로고 */}
        <div className="flex flex-col items-center mb-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary mb-3">
            <TrendingUp className="h-6 w-6 text-primary-foreground" />
          </div>
          <h1 className="text-xl font-bold text-foreground">건설 입찰 분석</h1>
          <p className="text-sm text-muted-foreground mt-1">로컬 AI 기반 투찰률 추천 시스템</p>
        </div>

        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-base">로그인</CardTitle>
            <CardDescription>계정 정보를 입력하세요</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">이메일</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">비밀번호</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? '로그인 중...' : '로그인'}
              </Button>
            </form>
            <p className="text-xs text-muted-foreground text-center mt-4">
              기본 계정: admin@bid.local / admin1234
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
