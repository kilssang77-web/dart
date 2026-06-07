import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TrendingUp, BarChart2, Shield, Zap, CheckCircle2, Lock, Mail } from 'lucide-react'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

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

  const features = [
    { icon: BarChart2,   title: 'AI 투찰률 추천',    desc: 'Monte Carlo 시뮬레이션으로 최적 투찰률 계산' },
    { icon: Shield,      title: '적격심사 자동 계산', desc: '낙찰하한율·가중치 실시간 산출' },
    { icon: Zap,         title: '경쟁사 분석',        desc: '등록 경쟁사 입찰 패턴 분석 및 예측' },
    { icon: TrendingUp,  title: '수주 성과 관리',     desc: '월별 KPI 추적 및 개선 인사이트 제공' },
  ]

  return (
    <div className="min-h-screen flex bg-slate-950">
      {/* 왼쪽 브랜드 패널 */}
      <div className="hidden lg:flex lg:w-[55%] flex-col justify-between p-12 relative overflow-hidden">
        {/* 배경 그라디언트 장식 */}
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 via-slate-900 to-slate-950" />
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4" />
        <div className="absolute bottom-0 left-0 w-72 h-72 bg-blue-600/10 rounded-full blur-3xl translate-y-1/3 -translate-x-1/4" />

        <div className="relative">
          {/* 로고 */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 shadow-lg shadow-blue-600/30">
              <TrendingUp className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-white font-bold text-lg leading-none">BidAI</p>
              <p className="text-blue-400 text-xs">입찰 분석 플랫폼</p>
            </div>
          </div>
        </div>

        <div className="relative space-y-8">
          <div>
            <h2 className="text-4xl font-bold text-white leading-tight">
              건설 입찰,<br />
              <span className="text-blue-400">AI로 더 스마트하게</span>
            </h2>
            <p className="text-slate-400 mt-4 text-base leading-relaxed">
              나라장터 공고를 실시간 분석하고 최적 투찰률을<br />
              자동 추천하는 로컬 AI 입찰 지원 시스템입니다.
            </p>
          </div>

          <div className="space-y-4">
            {features.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex items-start gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600/20 border border-blue-500/20 shrink-0">
                  <Icon className="h-4 w-4 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative flex items-center gap-6">
          {[
            { label: '등록 공고', value: '50,000+' },
            { label: '분석 경쟁사', value: '1,200+' },
            { label: '예측 정확도', value: '94.2%' },
          ].map((stat) => (
            <div key={stat.label}>
              <p className="text-2xl font-bold text-white tabular-nums">{stat.value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 오른쪽 로그인 폼 */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 bg-slate-900">
        {/* 모바일 로고 */}
        <div className="flex items-center gap-2.5 mb-8 lg:hidden">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600">
            <TrendingUp className="h-5 w-5 text-white" />
          </div>
          <span className="text-white font-bold text-lg">BidAI</span>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white">로그인</h1>
            <p className="text-slate-400 text-sm mt-1.5">계속하려면 계정 정보를 입력하세요</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-sm font-medium text-slate-300">
                이메일
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="pl-10 bg-slate-800 border-slate-700 text-white placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-sm font-medium text-slate-300">
                비밀번호
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="pl-10 bg-slate-800 border-slate-700 text-white placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm shadow-lg shadow-blue-600/20 transition-all"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  로그인 중...
                </span>
              ) : '로그인'}
            </Button>
          </form>

          <div className="mt-6 rounded-xl bg-slate-800/50 border border-slate-700/50 px-4 py-3">
            <p className="text-xs text-slate-500 font-medium mb-1">테스트 계정</p>
            <p className="text-xs text-slate-400 font-mono">admin@bid.local / admin1234</p>
          </div>
        </div>
      </div>
    </div>
  )
}
