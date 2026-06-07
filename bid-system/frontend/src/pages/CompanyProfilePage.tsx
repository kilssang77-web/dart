import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, Target, Wallet, Wrench, Plus, X, Save, CheckCircle2, Loader2, AlertCircle } from 'lucide-react'
import { companyApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface Profile {
  id?: number
  company_name: string
  biz_reg_no: string
  license_codes: string[]
  region_codes: string[]
  bond_limit_total: number
  bond_limit_used: number
  annual_revenue: number
  max_concurrent_bids: number
  target_min_margin: number
  target_regions: string[]
  target_industries: number[]
  workforce_count: number
  monthly_win_target: number
  bond_usage_rate?: number
  remaining_bond?: number
}

const defaultProfile: Profile = {
  company_name: '',
  biz_reg_no: '',
  license_codes: [],
  region_codes: [],
  bond_limit_total: 0,
  bond_limit_used: 0,
  annual_revenue: 0,
  max_concurrent_bids: 5,
  target_min_margin: 0.05,
  target_regions: [],
  target_industries: [],
  workforce_count: 0,
  monthly_win_target: 3,
}

function fmt억(v: number) {
  return `${(v / 1e8).toFixed(1)}억`
}

export default function CompanyProfilePage() {
  const qc = useQueryClient()
  const [form, setForm] = useState<Profile>(defaultProfile)
  const [saved, setSaved] = useState(false)
  const [licenseInput, setLicenseInput] = useState('')

  const { data: profile, isLoading } = useQuery({
    queryKey: ['company-profile'],
    queryFn: companyApi.getProfile,
    retry: false,
  })

  useEffect(() => {
    if (profile) setForm(profile)
  }, [profile])

  const mutation = useMutation({
    mutationFn: (data: Profile) => companyApi.upsertProfile(data as unknown as Record<string, unknown>),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['company-profile'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const set = (field: keyof Profile) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.type === 'number' ? Number(e.target.value) : e.target.value
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const addLicense = () => {
    if (!licenseInput.trim()) return
    setForm((prev) => ({ ...prev, license_codes: [...prev.license_codes, licenseInput.trim()] }))
    setLicenseInput('')
  }

  const removeLicense = (code: string) =>
    setForm((prev) => ({ ...prev, license_codes: prev.license_codes.filter((c) => c !== code) }))

  const bondUsage = form.bond_limit_total > 0
    ? Math.round((form.bond_limit_used / form.bond_limit_total) * 100)
    : 0

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <Loader2 className="h-7 w-7 animate-spin text-blue-400" />
          <p className="text-sm">프로파일 로딩 중...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-600" />회사 프로파일
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              E1 공고 선별 · E2 적격심사 · E7 포트폴리오 최적화의 기반 데이터
            </p>
          </div>
          <Button
            onClick={() => mutation.mutate(form)}
            disabled={mutation.isPending}
            className={cn(
              'gap-2 min-w-[90px]',
              saved ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 hover:bg-blue-700'
            )}
          >
            {saved ? (
              <><CheckCircle2 className="h-4 w-4" />저장됨</>
            ) : mutation.isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" />저장 중...</>
            ) : (
              <><Save className="h-4 w-4" />저장</>
            )}
          </Button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-5">
        {/* 오류 메시지 */}
        {mutation.isError && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" />
            저장 실패: {String(mutation.error)}
          </div>
        )}

        {/* 기본 정보 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-blue-600" />기본 정보
            </CardTitle>
            <CardDescription className="text-slate-500">회사 식별 정보를 입력하세요</CardDescription>
          </CardHeader>
          <CardContent className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">회사명 *</Label>
                <Input
                  value={form.company_name}
                  onChange={set('company_name')}
                  placeholder="(주)건설회사"
                  className="border-slate-200"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">사업자등록번호</Label>
                <Input
                  value={form.biz_reg_no}
                  onChange={set('biz_reg_no')}
                  placeholder="000-00-00000"
                  className="border-slate-200"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 수주 목표 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Target className="h-4 w-4 text-blue-600" />수주 목표
            </CardTitle>
            <CardDescription className="text-slate-500">KPI 대시보드 목표 기준값</CardDescription>
          </CardHeader>
          <CardContent className="p-5 space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">월 수주 목표 건수</Label>
                <Input
                  type="number"
                  value={form.monthly_win_target}
                  onChange={set('monthly_win_target')}
                  min={1}
                  max={20}
                  className="border-slate-200"
                />
                <p className="text-xs text-slate-400">건/월</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">최소 목표 마진율</Label>
                <Input
                  type="number"
                  value={(form.target_min_margin * 100).toFixed(1)}
                  onChange={(e) => setForm((p) => ({ ...p, target_min_margin: Number(e.target.value) / 100 }))}
                  min={0}
                  max={30}
                  step={0.5}
                  className="border-slate-200"
                />
                <p className="text-xs text-slate-400">% 이상</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">최대 동시 투찰 건수</Label>
                <Input
                  type="number"
                  value={form.max_concurrent_bids}
                  onChange={set('max_concurrent_bids')}
                  min={1}
                  max={20}
                  className="border-slate-200"
                />
                <p className="text-xs text-slate-400">건 동시</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 재무 / 보증한도 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Wallet className="h-4 w-4 text-blue-600" />재무 / 보증한도
            </CardTitle>
            <CardDescription className="text-slate-500">적격심사 및 포트폴리오 최적화 기반 데이터</CardDescription>
          </CardHeader>
          <CardContent className="p-5 space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">보증한도 총액 (원)</Label>
                <Input
                  type="number"
                  value={form.bond_limit_total}
                  onChange={set('bond_limit_total')}
                  step={10000000}
                  className="border-slate-200"
                />
                <p className="text-xs text-blue-600 font-medium">{fmt억(form.bond_limit_total)}</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">연매출 (원)</Label>
                <Input
                  type="number"
                  value={form.annual_revenue}
                  onChange={set('annual_revenue')}
                  step={10000000}
                  className="border-slate-200"
                />
                <p className="text-xs text-blue-600 font-medium">{fmt억(form.annual_revenue)}</p>
              </div>
            </div>
            {form.bond_limit_total > 0 && (
              <div className="bg-slate-50 rounded-xl p-4 space-y-3">
                <div className="flex justify-between items-center text-sm">
                  <span className="font-medium text-slate-700">보증한도 사용률</span>
                  <span className={cn('font-bold tabular-nums', bondUsage > 80 ? 'text-red-600' : bondUsage > 60 ? 'text-amber-600' : 'text-emerald-600')}>
                    {bondUsage}%
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2.5">
                  <div
                    className={cn('h-2.5 rounded-full transition-all duration-500', bondUsage > 80 ? 'bg-red-500' : bondUsage > 60 ? 'bg-amber-500' : 'bg-emerald-500')}
                    style={{ width: `${Math.min(100, bondUsage)}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>사용 {fmt억(form.bond_limit_used)}</span>
                  <span>한도 {fmt억(form.bond_limit_total)}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 공사 역량 */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Wrench className="h-4 w-4 text-blue-600" />공사 역량
            </CardTitle>
            <CardDescription className="text-slate-500">기술 역량 및 보유 면허 정보</CardDescription>
          </CardHeader>
          <CardContent className="p-5 space-y-5">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-slate-600">기술인력 수</Label>
              <Input
                type="number"
                value={form.workforce_count}
                onChange={set('workforce_count')}
                min={0}
                className="border-slate-200 max-w-xs"
              />
              <p className="text-xs text-slate-400">적격심사 기술인력 배점에 활용됩니다</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-medium text-slate-600">보유 면허 코드</Label>
              <div className="flex gap-2">
                <Input
                  value={licenseInput}
                  onChange={(e) => setLicenseInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addLicense()}
                  className="flex-1 border-slate-200"
                  placeholder="면허코드 입력 후 Enter 또는 추가 클릭"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={addLicense}
                  className="border-slate-200 text-slate-600 gap-1"
                >
                  <Plus className="h-3.5 w-3.5" />추가
                </Button>
              </div>
              {form.license_codes.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {form.license_codes.map((code) => (
                    <span
                      key={code}
                      className="flex items-center gap-1.5 bg-blue-50 text-blue-700 border border-blue-200 text-xs font-medium px-2.5 py-1 rounded-full"
                    >
                      {code}
                      <button
                        type="button"
                        onClick={() => removeLicense(code)}
                        className="text-blue-400 hover:text-blue-700 transition-colors ml-0.5"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              {form.license_codes.length === 0 && (
                <p className="text-xs text-slate-400">등록된 면허 코드가 없습니다.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 하단 저장 버튼 */}
        <div className="flex justify-end pt-2 pb-8">
          <Button
            onClick={() => mutation.mutate(form)}
            disabled={mutation.isPending}
            size="lg"
            className={cn(
              'gap-2 px-8',
              saved ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 hover:bg-blue-700'
            )}
          >
            {saved ? (
              <><CheckCircle2 className="h-4 w-4" />저장됨</>
            ) : mutation.isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" />저장 중...</>
            ) : (
              <><Save className="h-4 w-4" />변경사항 저장</>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
