import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { companyApi } from '../api'

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
    mutationFn: (data: Profile) => companyApi.upsertProfile(data as Record<string, unknown>),
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

  if (isLoading) return <div className="p-8 text-gray-500">로딩 중...</div>

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">회사 프로파일</h1>
          <p className="text-sm text-gray-500 mt-1">
            E1 공고 선별 · E2 적격심사 · E7 포트폴리오 최적화의 기반 데이터
          </p>
        </div>
        <button
          onClick={() => mutation.mutate(form)}
          disabled={mutation.isPending}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {saved ? '✓ 저장됨' : mutation.isPending ? '저장 중...' : '저장'}
        </button>
      </div>

      {/* 기본 정보 */}
      <section className="bg-white rounded-xl border p-5 space-y-4">
        <h2 className="font-semibold text-gray-700">기본 정보</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">회사명 *</label>
            <input value={form.company_name} onChange={set('company_name')}
              className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="(주)건설회사" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">사업자등록번호</label>
            <input value={form.biz_reg_no} onChange={set('biz_reg_no')}
              className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="000-00-00000" />
          </div>
        </div>
      </section>

      {/* 수주 목표 */}
      <section className="bg-white rounded-xl border p-5 space-y-4">
        <h2 className="font-semibold text-gray-700">수주 목표</h2>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">월 수주 목표 건수</label>
            <input type="number" value={form.monthly_win_target} onChange={set('monthly_win_target')}
              min={1} max={20} className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">최소 목표 마진율 (%)</label>
            <input type="number" value={(form.target_min_margin * 100).toFixed(1)}
              onChange={(e) => setForm((p) => ({ ...p, target_min_margin: Number(e.target.value) / 100 }))}
              min={0} max={30} step={0.5} className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">최대 동시 투찰 건수</label>
            <input type="number" value={form.max_concurrent_bids} onChange={set('max_concurrent_bids')}
              min={1} max={20} className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
      </section>

      {/* 재무/보증 */}
      <section className="bg-white rounded-xl border p-5 space-y-4">
        <h2 className="font-semibold text-gray-700">재무 / 보증한도</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">보증한도 총액 (원)</label>
            <input type="number" value={form.bond_limit_total} onChange={set('bond_limit_total')}
              step={10000000} className="w-full border rounded-lg px-3 py-2 text-sm" />
            <p className="text-xs text-gray-400 mt-1">{fmt억(form.bond_limit_total)}</p>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">연매출 (원)</label>
            <input type="number" value={form.annual_revenue} onChange={set('annual_revenue')}
              step={10000000} className="w-full border rounded-lg px-3 py-2 text-sm" />
            <p className="text-xs text-gray-400 mt-1">{fmt억(form.annual_revenue)}</p>
          </div>
        </div>
        {form.bond_limit_total > 0 && (
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>보증한도 사용률</span>
              <span className={bondUsage > 80 ? 'text-red-500 font-semibold' : ''}>{bondUsage}%</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${bondUsage > 80 ? 'bg-red-500' : bondUsage > 60 ? 'bg-yellow-500' : 'bg-green-500'}`}
                style={{ width: `${Math.min(100, bondUsage)}%` }}
              />
            </div>
          </div>
        )}
      </section>

      {/* 역량 */}
      <section className="bg-white rounded-xl border p-5 space-y-4">
        <h2 className="font-semibold text-gray-700">공사 역량</h2>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">기술인력 수</label>
          <input type="number" value={form.workforce_count} onChange={set('workforce_count')}
            min={0} className="w-full border rounded-lg px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">보유 면허 코드</label>
          <div className="flex gap-2 mb-2">
            <input value={licenseInput} onChange={(e) => setLicenseInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addLicense()}
              className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="면허코드 입력 후 Enter" />
            <button onClick={addLicense} className="px-3 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200">추가</button>
          </div>
          <div className="flex flex-wrap gap-2">
            {form.license_codes.map((code) => (
              <span key={code} className="flex items-center gap-1 bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded-full">
                {code}
                <button onClick={() => removeLicense(code)} className="text-blue-400 hover:text-blue-700">×</button>
              </span>
            ))}
          </div>
        </div>
      </section>

      {mutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          저장 실패: {String(mutation.error)}
        </div>
      )}
    </div>
  )
}
