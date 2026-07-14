import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, Phone, MapPin, User, BadgeCheck,
  TrendingDown, TrendingUp, BarChart3, Calendar,
  Target, Wallet, Wrench, Plus, X, Save,
  CheckCircle2, Loader2, AlertCircle, Trash2,
} from 'lucide-react'
import { companyApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface ConstructionCapability {
  industry_name: string
  year: number
  amount: number
  perf_3y: number
  perf_5y: number
  last_updated: string
  is_closed: boolean
  is_suspended: boolean
}

interface Profile {
  id?: number
  // 기본정보
  company_name: string
  biz_reg_no: string
  phone: string
  address: string
  ceo_name: string
  is_women_company: boolean
  // 경영상태
  credit_grade: string
  credit_valid_date: string
  ppsq_rating: number | null
  moi_rating: number | null
  debt_ratio: number | null
  total_debt: number | null
  equity: number | null
  current_ratio: number | null
  current_assets: number | null
  current_liabilities: number | null
  region: string
  general_operation_period: string
  specialty_operation_period: string
  disclosure_year: number | null
  // 시공능력
  construction_capabilities: ConstructionCapability[]
  // 시스템 필수
  license_codes: string[]
  region_codes: string[]
  bond_limit_total: number
  bond_limit_used: number
  annual_revenue: number
  max_concurrent_bids: number
  target_min_margin: number
  target_regions: string[]
  target_industries: number[]
  performance_records: Record<string, unknown>
  workforce_count: number
  monthly_win_target: number
  bond_usage_rate?: number
  remaining_bond?: number
}

const defaultProfile: Profile = {
  company_name: '', biz_reg_no: '', phone: '', address: '', ceo_name: '',
  is_women_company: false,
  credit_grade: '', credit_valid_date: '',
  ppsq_rating: null, moi_rating: null,
  debt_ratio: null, total_debt: null, equity: null,
  current_ratio: null, current_assets: null, current_liabilities: null,
  region: '', general_operation_period: '', specialty_operation_period: '',
  disclosure_year: null,
  construction_capabilities: [],
  license_codes: [], region_codes: [],
  bond_limit_total: 0, bond_limit_used: 0, annual_revenue: 0,
  max_concurrent_bids: 5, target_min_margin: 0.05,
  target_regions: [], target_industries: [],
  performance_records: {}, workforce_count: 0, monthly_win_target: 3,
}

const emptyCapability = (): ConstructionCapability => ({
  industry_name: '', year: new Date().getFullYear(),
  amount: 0, perf_3y: 0, perf_5y: 0,
  last_updated: '', is_closed: false, is_suspended: false,
})

function fmtAmt(v: number | null | undefined) {
  if (!v) return '0'
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}억`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}만`
  return v.toLocaleString()
}

function fmtBiz(v: string) {
  const d = v.replace(/\D/g, '')
  if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`
  return v
}

function SectionBadge({ label }: { label: string }) {
  return (
    <span className="ml-2 text-xs font-semibold px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 border border-blue-200">
      {label}
    </span>
  )
}

export default function CompanyProfilePage() {
  const qc = useQueryClient()
  const [form, setForm] = useState<Profile>(defaultProfile)
  const [saved, setSaved] = useState(false)
  const [licenseInput, setLicenseInput] = useState('')
  const [addingCap, setAddingCap] = useState(false)
  const [newCap, setNewCap] = useState<ConstructionCapability>(emptyCapability())

  const { data: profile, isLoading } = useQuery({
    queryKey: ['company-profile'],
    queryFn: companyApi.getProfile,
    retry: false,
  })

  useEffect(() => {
    if (profile) setForm({ ...defaultProfile, ...profile })
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
    const v = e.target.type === 'number' ? (e.target.value === '' ? null : Number(e.target.value))
              : e.target.type === 'checkbox' ? e.target.checked
              : e.target.value
    setForm((p) => ({ ...p, [field]: v }))
  }

  const addLicense = () => {
    if (!licenseInput.trim()) return
    setForm((p) => ({ ...p, license_codes: [...p.license_codes, licenseInput.trim()] }))
    setLicenseInput('')
  }

  const removeLicense = (code: string) =>
    setForm((p) => ({ ...p, license_codes: p.license_codes.filter((c) => c !== code) }))

  const addCapability = () => {
    if (!newCap.industry_name.trim()) return
    setForm((p) => ({ ...p, construction_capabilities: [...p.construction_capabilities, { ...newCap }] }))
    setNewCap(emptyCapability())
    setAddingCap(false)
  }

  const removeCap = (idx: number) =>
    setForm((p) => ({ ...p, construction_capabilities: p.construction_capabilities.filter((_, i) => i !== idx) }))

  const bondUsage = form.bond_limit_total > 0
    ? Math.round((form.bond_limit_used / form.bond_limit_total) * 100) : 0

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-slate-500">
          <Loader2 className="h-7 w-7 animate-spin text-blue-400" />
          <p className="text-sm">프로파일 로딩 중...</p>
        </div>
      </div>
    )
  }

  const SaveBtn = ({ size = 'default' as 'default' | 'lg', className = '' }) => (
    <Button
      onClick={() => mutation.mutate(form)}
      disabled={mutation.isPending}
      size={size}
      className={cn('gap-2', saved ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 hover:bg-blue-700', className)}
    >
      {saved ? <><CheckCircle2 className="h-4 w-4" />저장됨</>
        : mutation.isPending ? <><Loader2 className="h-4 w-4 animate-spin" />저장 중...</>
        : <><Save className="h-4 w-4" />저장</>}
    </Button>
  )

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-600" />회사 프로파일
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">E1 공고 선별 · E2 적격심사 · E7 포트폴리오 최적화의 기반 데이터</p>
          </div>
          <SaveBtn />
        </div>
      </div>

      <div className="max-w-4xl mx-auto p-6 space-y-5">
        {mutation.isError && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" />
            저장 실패: {String(mutation.error)}
          </div>
        )}

        {/* ── 기본정보 ─────────────────────────── */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-blue-600" />기본정보
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600 flex items-center gap-1">
                  <Building2 className="h-3 w-3" />업체명 *
                </Label>
                <Input value={form.company_name} onChange={set('company_name')}
                  placeholder="주식회사 ○○건설" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600 flex items-center gap-1">
                  <Phone className="h-3 w-3" />전화번호
                </Label>
                <Input value={form.phone ?? ''} onChange={set('phone')}
                  placeholder="042-000-0000" className="border-slate-200" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">사업자번호</Label>
                <Input value={form.biz_reg_no ?? ''} onChange={set('biz_reg_no')}
                  onBlur={(e) => setForm((p) => ({ ...p, biz_reg_no: fmtBiz(e.target.value) }))}
                  placeholder="000-00-00000" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600 flex items-center gap-1">
                  <User className="h-3 w-3" />대표자
                </Label>
                <Input value={form.ceo_name ?? ''} onChange={set('ceo_name')}
                  placeholder="홍길동" className="border-slate-200" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-sm font-medium text-slate-600 flex items-center gap-1">
                <MapPin className="h-3 w-3" />주소
              </Label>
              <Input value={form.address ?? ''} onChange={set('address')}
                placeholder="대전광역시 중구 ○○로 00" className="border-slate-200" />
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.is_women_company}
                  onChange={set('is_women_company')}
                  className="w-4 h-4 rounded border-slate-300 accent-blue-600" />
                <span className="text-sm text-slate-700 flex items-center gap-1">
                  <BadgeCheck className="h-3.5 w-3.5 text-pink-500" />여성기업
                </span>
              </label>
            </div>
          </CardContent>
        </Card>

        {/* ── 경영상태 ─────────────────────────── */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-blue-600" />경영상태
              <span className="text-xs text-slate-500 font-normal">(재무비율 표기 최대값: 999999.99%)</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-5">
            {/* 신용 */}
            <div className="grid grid-cols-4 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">신용등급</Label>
                <Input value={form.credit_grade ?? ''} onChange={set('credit_grade')}
                  placeholder="BBB+" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600 flex items-center gap-1">
                  <Calendar className="h-3 w-3" />신용 유효일자
                </Label>
                <Input type="date" value={form.credit_valid_date ?? ''} onChange={set('credit_valid_date')}
                  className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">조달청 신인도</Label>
                <Input type="number" value={form.ppsq_rating ?? ''} onChange={set('ppsq_rating')}
                  step={0.1} placeholder="3" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">행안부 신인도</Label>
                <Input type="number" value={form.moi_rating ?? ''} onChange={set('moi_rating')}
                  step={0.1} placeholder="2" className="border-slate-200" />
              </div>
            </div>

            {/* 부채 */}
            <div>
              <p className="text-xs font-semibold text-slate-500 mb-2 flex items-center gap-1">
                <TrendingDown className="h-3 w-3 text-red-400" />부채비율
              </p>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">부채비율 (%)</Label>
                  <Input type="number" value={form.debt_ratio ?? ''} onChange={set('debt_ratio')}
                    step={0.01} placeholder="0.39" className="border-slate-200" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">부채총계 (원)</Label>
                  <Input type="number" value={form.total_debt ?? ''} onChange={set('total_debt')}
                    step={1000} placeholder="623000" className="border-slate-200" />
                  {form.total_debt ? <p className="text-xs text-slate-500">{fmtAmt(form.total_debt)}</p> : null}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">자기자본 (원)</Label>
                  <Input type="number" value={form.equity ?? ''} onChange={set('equity')}
                    step={1000} placeholder="157505000" className="border-slate-200" />
                  {form.equity ? <p className="text-xs text-slate-500">{fmtAmt(form.equity)}</p> : null}
                </div>
              </div>
            </div>

            {/* 유동 */}
            <div>
              <p className="text-xs font-semibold text-slate-500 mb-2 flex items-center gap-1">
                <TrendingUp className="h-3 w-3 text-emerald-500" />유동비율
              </p>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">유동비율 (%)</Label>
                  <Input type="number" value={form.current_ratio ?? ''} onChange={set('current_ratio')}
                    step={0.01} placeholder="17174.47" className="border-slate-200" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">유동자산 (원)</Label>
                  <Input type="number" value={form.current_assets ?? ''} onChange={set('current_assets')}
                    step={1000} placeholder="106997000" className="border-slate-200" />
                  {form.current_assets ? <p className="text-xs text-slate-500">{fmtAmt(form.current_assets)}</p> : null}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-slate-500">유동부채 (원)</Label>
                  <Input type="number" value={form.current_liabilities ?? ''} onChange={set('current_liabilities')}
                    step={1000} placeholder="623000" className="border-slate-200" />
                  {form.current_liabilities ? <p className="text-xs text-slate-500">{fmtAmt(form.current_liabilities)}</p> : null}
                </div>
              </div>
            </div>

            {/* 기타 */}
            <div className="grid grid-cols-4 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">지역</Label>
                <Input value={form.region ?? ''} onChange={set('region')}
                  placeholder="대전" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">종합영업기간</Label>
                <Input value={form.general_operation_period ?? ''} onChange={set('general_operation_period')}
                  placeholder="2010-01-01" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">전문영업기간</Label>
                <Input value={form.specialty_operation_period ?? ''} onChange={set('specialty_operation_period')}
                  placeholder="2010-01-01" className="border-slate-200" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">공시년도</Label>
                <Input type="number" value={form.disclosure_year ?? ''} onChange={set('disclosure_year')}
                  placeholder="2025" className="border-slate-200" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── 시공능력 ─────────────────────────── */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                <Wrench className="h-4 w-4 text-blue-600" />시공능력
              </CardTitle>
              <Button type="button" variant="outline" size="sm"
                onClick={() => setAddingCap(true)}
                className="gap-1 text-blue-600 border-blue-200 hover:bg-blue-50">
                <Plus className="h-3.5 w-3.5" />업종 추가
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {form.construction_capabilities.length === 0 && !addingCap ? (
              <p className="text-sm text-slate-500 text-center py-8">등록된 시공능력 업종이 없습니다.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      {['업종(주력분야)', '공시년도', '시평액', '3년 실적', '5년 실적', '최근수정일', '폐업', '영업정지', ''].map((h) => (
                        <th key={h} className="px-3 py-2.5 text-left font-semibold text-slate-600 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {form.construction_capabilities.map((cap, idx) => (
                      <tr key={idx} className="border-b border-slate-50 hover:bg-slate-50/50">
                        <td className="px-3 py-2 font-medium text-slate-800">{cap.industry_name}</td>
                        <td className="px-3 py-2 text-slate-600">{cap.year}</td>
                        <td className="px-3 py-2 text-slate-700">{cap.amount.toLocaleString()}</td>
                        <td className="px-3 py-2 text-slate-700">{cap.perf_3y.toLocaleString()}</td>
                        <td className="px-3 py-2 text-slate-700">{cap.perf_5y.toLocaleString()}</td>
                        <td className="px-3 py-2 text-slate-500">{cap.last_updated || '-'}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={cn('font-medium', cap.is_closed ? 'text-red-500' : 'text-emerald-600')}>
                            {cap.is_closed ? 'Y' : 'N'}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span className={cn('font-medium', cap.is_suspended ? 'text-red-500' : 'text-emerald-600')}>
                            {cap.is_suspended ? 'Y' : 'N'}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <button onClick={() => removeCap(idx)}
                            className="text-slate-300 hover:text-red-500 transition-colors">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 신규 추가 폼 */}
            {addingCap && (
              <div className="border-t border-slate-100 p-4 bg-blue-50/40 space-y-3">
                <p className="text-xs font-semibold text-blue-700">새 업종 추가</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-sm text-slate-600">업종명 *</Label>
                    <Input value={newCap.industry_name}
                      onChange={(e) => setNewCap((p) => ({ ...p, industry_name: e.target.value }))}
                      placeholder="실내건축공사업[대]" className="border-slate-200 bg-white h-8 text-xs" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-sm text-slate-600">공시년도</Label>
                    <Input type="number" value={newCap.year}
                      onChange={(e) => setNewCap((p) => ({ ...p, year: Number(e.target.value) }))}
                      className="border-slate-200 bg-white h-8 text-xs" />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-sm text-slate-600">시평액 (원)</Label>
                    <Input type="number" value={newCap.amount}
                      onChange={(e) => setNewCap((p) => ({ ...p, amount: Number(e.target.value) }))}
                      className="border-slate-200 bg-white h-8 text-xs" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-sm text-slate-600">3년 실적 (원)</Label>
                    <Input type="number" value={newCap.perf_3y}
                      onChange={(e) => setNewCap((p) => ({ ...p, perf_3y: Number(e.target.value) }))}
                      className="border-slate-200 bg-white h-8 text-xs" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-sm text-slate-600">5년 실적 (원)</Label>
                    <Input type="number" value={newCap.perf_5y}
                      onChange={(e) => setNewCap((p) => ({ ...p, perf_5y: Number(e.target.value) }))}
                      className="border-slate-200 bg-white h-8 text-xs" />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-sm text-slate-600">최근수정일</Label>
                    <Input value={newCap.last_updated}
                      onChange={(e) => setNewCap((p) => ({ ...p, last_updated: e.target.value }))}
                      placeholder="2026-05-11" className="border-slate-200 bg-white h-8 text-xs" />
                  </div>
                  <div className="flex items-end gap-4 pb-0.5">
                    <label className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer">
                      <input type="checkbox" checked={newCap.is_closed}
                        onChange={(e) => setNewCap((p) => ({ ...p, is_closed: e.target.checked }))}
                        className="accent-red-500" />폐업
                    </label>
                    <label className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer">
                      <input type="checkbox" checked={newCap.is_suspended}
                        onChange={(e) => setNewCap((p) => ({ ...p, is_suspended: e.target.checked }))}
                        className="accent-red-500" />영업정지
                    </label>
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <Button type="button" size="sm" onClick={addCapability}
                    className="bg-blue-600 hover:bg-blue-700 h-8 text-xs gap-1">
                    <Plus className="h-3 w-3" />추가
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => { setAddingCap(false); setNewCap(emptyCapability()) }}
                    className="h-8 text-xs">취소</Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── 수주 목표 (시스템 필수) ─────────── */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Target className="h-4 w-4 text-blue-600" />수주 목표
              <SectionBadge label="ML 필수" />
            </CardTitle>
            <CardDescription className="text-slate-500">KPI 대시보드 · E1 선별 · E7 포트폴리오 목표 기준값</CardDescription>
          </CardHeader>
          <CardContent className="p-5">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">월 수주 목표 건수</Label>
                <Input type="number" value={form.monthly_win_target} onChange={set('monthly_win_target')}
                  min={1} max={20} className="border-slate-200" />
                <p className="text-xs text-slate-500">건/월</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">최소 목표 마진율</Label>
                <Input type="number"
                  value={(form.target_min_margin * 100).toFixed(1)}
                  onChange={(e) => setForm((p) => ({ ...p, target_min_margin: Number(e.target.value) / 100 }))}
                  min={0} max={30} step={0.5} className="border-slate-200" />
                <p className="text-xs text-slate-500">% 이상</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">최대 동시 투찰 건수</Label>
                <Input type="number" value={form.max_concurrent_bids} onChange={set('max_concurrent_bids')}
                  min={1} max={20} className="border-slate-200" />
                <p className="text-xs text-slate-500">건 동시</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── 재무 / 보증한도 (시스템 필수) ─── */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Wallet className="h-4 w-4 text-blue-600" />재무 / 보증한도
              <SectionBadge label="ML 필수" />
            </CardTitle>
            <CardDescription className="text-slate-500">E2 적격심사 · E7 포트폴리오 최적화 기반 데이터</CardDescription>
          </CardHeader>
          <CardContent className="p-5 space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">보증한도 총액 (원)</Label>
                <Input type="number" value={form.bond_limit_total} onChange={set('bond_limit_total')}
                  step={10000000} className="border-slate-200" />
                <p className="text-xs text-blue-600 font-medium">{fmtAmt(form.bond_limit_total)}</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium text-slate-600">연매출 (원)</Label>
                <Input type="number" value={form.annual_revenue} onChange={set('annual_revenue')}
                  step={10000000} className="border-slate-200" />
                <p className="text-xs text-blue-600 font-medium">{fmtAmt(form.annual_revenue)}</p>
              </div>
            </div>
            {form.bond_limit_total > 0 && (
              <div className="bg-slate-50 rounded-xl p-4 space-y-3">
                <div className="flex justify-between items-center text-sm">
                  <span className="font-medium text-slate-700">보증한도 사용률</span>
                  <span className={cn('font-bold tabular-nums',
                    bondUsage > 80 ? 'text-red-600' : bondUsage > 60 ? 'text-amber-600' : 'text-emerald-600')}>
                    {bondUsage}%
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2.5">
                  <div className={cn('h-2.5 rounded-full transition-all duration-500',
                    bondUsage > 80 ? 'bg-red-500' : bondUsage > 60 ? 'bg-amber-500' : 'bg-emerald-500')}
                    style={{ width: `${Math.min(100, bondUsage)}%` }} />
                </div>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>사용 {fmtAmt(form.bond_limit_used)}</span>
                  <span>한도 {fmtAmt(form.bond_limit_total)}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── 공사 역량 (시스템 필수) ─────────── */}
        <Card className="bg-white border-slate-200 shadow-sm">
          <CardHeader className="border-b border-slate-100 pb-4">
            <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
              <Wrench className="h-4 w-4 text-blue-600" />공사 역량
              <SectionBadge label="ML 필수" />
            </CardTitle>
            <CardDescription className="text-slate-500">E2 적격심사 기술인력 배점 · E1 공고 매칭 기반 데이터</CardDescription>
          </CardHeader>
          <CardContent className="p-5 space-y-5">
            <div className="space-y-1.5">
              <Label className="text-sm font-medium text-slate-600">기술인력 수</Label>
              <Input type="number" value={form.workforce_count} onChange={set('workforce_count')}
                min={0} className="border-slate-200 max-w-xs" />
              <p className="text-xs text-slate-500">적격심사 기술인력 배점에 활용됩니다</p>
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium text-slate-600">보유 면허 코드</Label>
              <div className="flex gap-2">
                <Input value={licenseInput}
                  onChange={(e) => setLicenseInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addLicense()}
                  className="flex-1 border-slate-200"
                  placeholder="면허코드 입력 후 Enter 또는 추가 클릭" />
                <Button type="button" variant="outline" onClick={addLicense}
                  className="border-slate-200 text-slate-600 gap-1">
                  <Plus className="h-3.5 w-3.5" />추가
                </Button>
              </div>
              {form.license_codes.length > 0 ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {form.license_codes.map((code) => (
                    <span key={code}
                      className="flex items-center gap-1.5 bg-blue-50 text-blue-700 border border-blue-200 text-sm font-medium px-2.5 py-1 rounded-full">
                      {code}
                      <button type="button" onClick={() => removeLicense(code)}
                        className="text-blue-400 hover:text-blue-700 transition-colors ml-0.5">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500">등록된 면허 코드가 없습니다.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 하단 저장 버튼 */}
        <div className="flex justify-end pt-2 pb-8">
          <SaveBtn size="lg" className="px-8" />
        </div>
      </div>
    </div>
  )
}
