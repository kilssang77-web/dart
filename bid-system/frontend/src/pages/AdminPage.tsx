import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, ShieldCheck, Activity, Plus, Pencil, Trash2, RefreshCw, Database, Layers, Search, CheckSquare, Square, Save, ChevronDown, Loader2, Zap, Download, Info, ExternalLink, AlertCircle, CheckCircle2 } from 'lucide-react'
import { adminApi, statsApi } from '@/api'
import type { AdminUser, SystemStatus, ModelInfo, IndustryFilterItem, CollectionLogOut, CollectionLogDetail, CollectorStatus } from '@/types'
import { useAuthStore } from '@/store/auth'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter
} from '@/components/ui/dialog'

const ROLE_CONFIG: Record<string, { label: string; cls: string }> = {
  admin:   { label: '관리자', cls: 'bg-red-50 text-red-700 border border-red-200' },
  analyst: { label: '분석가', cls: 'bg-blue-50 text-blue-700 border border-blue-200' },
  viewer:  { label: '뷰어',   cls: 'bg-slate-100 text-slate-600 border border-slate-200' },
}

interface UserFormState { email: string; password: string; name: string; role: string; department: string }
const EMPTY_FORM: UserFormState = { email: '', password: '', name: '', role: 'viewer', department: '' }

export default function AdminPage() {
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [tab, setTab] = useState('system')
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<UserFormState>(EMPTY_FORM)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
  const [indSearch, setIndSearch] = useState('')
  const [checkedIds, setCheckedIds] = useState<Set<number> | null>(null)
  const [indSaved, setIndSaved] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [triggerMsg, setTriggerMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [inpoCollectMsg, setInpoCollectMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [selectedLog, setSelectedLog] = useState<CollectionLogOut | null>(null)

  const { data: users = [], isLoading: usersLoading } = useQuery<AdminUser[]>({
    queryKey: ['admin-users'], queryFn: adminApi.users, enabled: tab === 'users',
  })
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery<SystemStatus>({
    queryKey: ['admin-status'], queryFn: adminApi.systemStatus, enabled: tab === 'system', refetchInterval: 30000,
  })
  const { data: collectorStatus, refetch: refetchCollectorStatus } = useQuery<CollectorStatus>({
    queryKey: ['admin-collector-status'], queryFn: adminApi.collectorStatus, enabled: tab === 'system', refetchInterval: 60000,
  })
  const { data: modelInfo } = useQuery<ModelInfo>({
    queryKey: ['model-info'], queryFn: () => statsApi.modelInfo(), enabled: tab === 'system',
  })
  const { data: industryFilters = [], isLoading: indLoading } = useQuery<IndustryFilterItem[]>({
    queryKey: ['admin-industry-filters'], queryFn: adminApi.industryFilters, enabled: tab === 'industries',
  })
  const { data: collectionLogs = [], refetch: refetchLogs } = useQuery<CollectionLogOut[]>({
    queryKey: ['admin-collection-logs'],
    queryFn: () => adminApi.collectionLogs(7),
    enabled: tab === 'system' || tab === 'collection',
    refetchInterval: 60000,
  })
  const { data: inpoStatus, refetch: refetchInpoStatus } = useQuery({
    queryKey: ['admin-inpo21c-status'],
    queryFn: () => adminApi.inpo21cStatus(),
    enabled: tab === 'collection',
    staleTime: 60_000,
  })

  const inpoCollectMutation = useMutation({
    mutationFn: () => adminApi.triggerInpo21cCollect(4),
    onSuccess: () => { refetchInpoProgress() },
    onError: () => {
      setInpoCollectMsg({ type: 'error', text: 'inpo21c 수집 요청 실패' })
      setTimeout(() => setInpoCollectMsg(null), 5000)
    },
  })

  const { data: inpoProgress, refetch: refetchInpoProgress } = useQuery({
    queryKey: ['inpo21c-progress'],
    queryFn: () => adminApi.inpo21cProgress(),
    enabled: tab === 'collection',
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
    staleTime: 0,
  })

  if (checkedIds === null && industryFilters.length > 0) {
    setCheckedIds(new Set(industryFilters.filter((i) => i.is_active).map((i) => i.industry_id)))
  }

  const createMutation = useMutation({
    mutationFn: adminApi.createUser,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); resetForm() },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => adminApi.updateUser(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); resetForm() },
  })
  const deleteMutation = useMutation({
    mutationFn: adminApi.deleteUser,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); setDeleteConfirm(null) },
  })
  const retrainMutation = useMutation({
    mutationFn: async () => { const { recommendApi } = await import('@/api'); return recommendApi.retrain() },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['model-info'] }) },
  })
  const saveIndMutation = useMutation({
    mutationFn: (ids: number[]) => adminApi.updateIndustryFilters(ids),
    onSuccess: () => {
      setIndSaved(true)
      qc.invalidateQueries({ queryKey: ['admin-industry-filters'] })
      qc.invalidateQueries({ queryKey: ['stats-overview'] })
      qc.invalidateQueries({ queryKey: ['stats-cluster'] })
      qc.invalidateQueries({ queryKey: ['stats-heatmap'] })
      setTimeout(() => setIndSaved(false), 3000)
    },
  })
  const triggerMutation = useMutation({
    mutationFn: (collectType: 'all' | 'notices' | 'results') => adminApi.triggerCollect(collectType),
    onSuccess: (data) => {
      setTriggerMsg({ type: 'success', text: data.message ?? '수집이 시작되었습니다.' })
      qc.invalidateQueries({ queryKey: ['admin-collection-logs'] })
      setTimeout(() => setTriggerMsg(null), 5000)
    },
    onError: () => {
      setTriggerMsg({ type: 'error', text: '수집 요청에 실패했습니다.' })
      setTimeout(() => setTriggerMsg(null), 5000)
    },
  })

  function resetForm() { setShowForm(false); setEditId(null); setForm(EMPTY_FORM) }
  function handleEdit(u: AdminUser) {
    setEditId(u.id)
    setForm({ email: u.email, password: '', name: u.name ?? '', role: u.role, department: u.department ?? '' })
    setShowForm(true)
  }
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (editId !== null) {
      const body: Record<string, unknown> = { name: form.name, role: form.role, department: form.department || undefined }
      if (form.password) body.password = form.password
      updateMutation.mutate({ id: editId, body })
    } else {
      createMutation.mutate({ email: form.email, password: form.password, name: form.name, role: form.role, department: form.department || undefined })
    }
  }

  const currentChecked = useMemo(() => {
    if (checkedIds !== null) return checkedIds
    return new Set(industryFilters.filter((i) => i.is_active).map((i) => i.industry_id))
  }, [checkedIds, industryFilters])

  const filteredIndustries = useMemo(() =>
    industryFilters.filter((i) => i.name.toLowerCase().includes(indSearch.toLowerCase())),
    [industryFilters, indSearch]
  )

  function toggleIndustry(id: number) {
    const next = new Set(currentChecked)
    if (next.has(id)) next.delete(id); else next.add(id)
    setCheckedIds(next); setIndSaved(false)
  }

  const stats = status?.db_stats
  const collector = status?.collector
  const activeCount = currentChecked.size
  const totalCount = industryFilters.length

  interface CollectTypeMeta {
    label: string
    color: string
    provider: string       // 데이터 제공 기관
    method: string         // 수집 방식
    source: string         // 시스템명
    endpoint: string       // API 엔드포인트 또는 경로
    api_base: string       // 베이스 URL
    data_desc: string      // 수집 데이터 설명
  }
  const COLLECT_TYPE_META: Record<string, CollectTypeMeta> = {
    notice_cnstwk: {
      label: '공사 입찰공고', color: 'bg-blue-50 text-blue-700 border-blue-200',
      provider: '조달청 (나라장터)',
      method: 'REST API (공공데이터포털)',
      source: '나라장터 G2B API',
      endpoint: 'getBidPblancListInfoCnstwk',
      api_base: 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
      data_desc: '건설·토목·전기 등 공사 분야 입찰공고 목록 (공고번호·발주기관·금액·마감일)',
    },
    notice_servc: {
      label: '용역 입찰공고', color: 'bg-violet-50 text-violet-700 border-violet-200',
      provider: '조달청 (나라장터)',
      method: 'REST API (공공데이터포털)',
      source: '나라장터 G2B API',
      endpoint: 'getBidPblancListInfoServc',
      api_base: 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
      data_desc: 'IT·컨설팅·청소 등 용역 분야 입찰공고 목록 (공고번호·발주기관·금액·마감일)',
    },
    notice_thng: {
      label: '물품 입찰공고', color: 'bg-amber-50 text-amber-700 border-amber-200',
      provider: '조달청 (나라장터)',
      method: 'REST API (공공데이터포털)',
      source: '나라장터 G2B API',
      endpoint: 'getBidPblancListInfoThng',
      api_base: 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
      data_desc: '사무용품·장비 등 물품 분야 입찰공고 목록 (공고번호·발주기관·금액·마감일)',
    },
    result: {
      label: '낙찰결과', color: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      provider: '조달청 (나라장터)',
      method: 'REST API (공공데이터포털)',
      source: '나라장터 ScsbidInfoService',
      endpoint: 'getScsbidListSttusCnstwk',
      api_base: 'https://apis.data.go.kr/1230000/as/ScsbidInfoService',
      data_desc: '공사·용역 입찰 개찰결과 — 낙찰자·낙찰금액·투찰율·경쟁업체 참여 정보',
    },
    inpo21c: {
      label: 'inpo21c 공고', color: 'bg-orange-50 text-orange-700 border-orange-200',
      provider: 'inpo21c (나라장터 포털)',
      method: '웹 크롤링 (쿠키 인증)',
      source: 'inpo21c.co.kr',
      endpoint: '/bid/bidList.do',
      api_base: 'https://www.inpo21c.co.kr',
      data_desc: '나라장터 공고 상세 — 사전정보(예정가격·복수예가·A값 등) 및 참여자 목록',
    },
    inpo21c_yega: {
      label: 'inpo21c 예가', color: 'bg-rose-50 text-rose-700 border-rose-200',
      provider: 'inpo21c (나라장터 포털)',
      method: '웹 크롤링 (쿠키 인증)',
      source: 'inpo21c.co.kr',
      endpoint: '/bid/bidDetail.do',
      api_base: 'https://www.inpo21c.co.kr',
      data_desc: '개찰 후 복수예가 번호·A값·투찰율 상세 — 통계 모델 재훈련용 데이터',
    },
    inpo21c_daily: {
      label: 'inpo21c 전참여자', color: 'bg-orange-50 text-orange-700 border-orange-200',
      provider: 'info21c.net (inpo21c)',
      method: '웹 크롤링 (세션 쿠키 자동갱신)',
      source: 'infose.info21c.net',
      endpoint: '/suc/con (맞춤설정 division 1~3)',
      api_base: 'https://infose.info21c.net',
      data_desc: '당일 개찰 낙찰 결과 — 전 참여자·복수예가 15개 분포·공고 헤더 (맞춤설정 기관)',
    },
    inpo21c_national: {
      label: 'inpo21c 전국', color: 'bg-amber-50 text-amber-700 border-amber-200',
      provider: 'info21c.net (inpo21c)',
      method: '웹 크롤링 (세션 쿠키 자동갱신)',
      source: 'infose.info21c.net',
      endpoint: '/suc/con (전국, division 미지정)',
      api_base: 'https://infose.info21c.net',
      data_desc: '전국 낙찰 결과 — 전 참여자·복수예가·공고 헤더 (소규모 기관 포함 전국 커버리지)',
    },
    inpo21c_notices: {
      label: 'inpo21c 입찰공고', color: 'bg-yellow-50 text-yellow-700 border-yellow-200',
      provider: 'info21c.net (inpo21c)',
      method: '웹 크롤링 (세션 쿠키 자동갱신)',
      source: 'infose.info21c.net',
      endpoint: '/bid/con',
      api_base: 'https://infose.info21c.net',
      data_desc: '개찰 전 입찰공고 사전정보 — 예가방법·변동폭·낙찰하한율·개찰일시',
    },
  }

  interface ErrorInterpretation {
    icon: 'duplicate' | 'api' | 'network' | 'auth' | 'unknown'
    title: string
    cause: string
    impact: string
    severity: 'warning' | 'error'
  }

  function interpretErrorMessage(raw: string): ErrorInterpretation {
    const r = raw.toLowerCase()

    if (r.includes('uniqueviolation') && r.includes('uq_bid_competitor')) {
      return {
        icon: 'duplicate', severity: 'warning',
        title: '낙찰결과 중복 저장 시도',
        cause: '동일 공고에 동일 경쟁업체 결과가 이미 DB에 존재합니다. API가 이전에 수집한 데이터를 다시 반환한 것입니다.',
        impact: '데이터 손실 없음 — 기존 레코드가 그대로 유지됩니다. 정상적인 중복 방지 처리입니다.',
      }
    }
    if (r.includes('uniqueviolation') && r.includes('competitors_biz_reg_no_key')) {
      return {
        icon: 'duplicate', severity: 'warning',
        title: '경쟁업체 중복 등록 시도',
        cause: '동일한 사업자번호를 가진 경쟁업체가 이미 DB에 등록되어 있습니다. 동시 수집 또는 재수집 시 발생하는 정상적인 충돌입니다.',
        impact: '데이터 손실 없음 — 기존 경쟁업체 정보가 그대로 유지됩니다.',
      }
    }
    if (r.includes('uniqueviolation')) {
      return {
        icon: 'duplicate', severity: 'warning',
        title: '중복 데이터 저장 시도',
        cause: '이미 DB에 존재하는 데이터를 다시 저장하려 했습니다.',
        impact: '기존 데이터는 유지됩니다. 중복 방지 제약조건이 정상 동작한 것입니다.',
      }
    }
    if (r.includes('500 internal server error') && (r.includes('getbidresultlist') || r.includes('bidpublicinfoservice02'))) {
      return {
        icon: 'api', severity: 'error',
        title: '나라장터 구 API 엔드포인트 오류',
        cause: '공공데이터포털의 getBidResultListInfoCnstwk 엔드포인트가 HTTP 500 오류를 반환했습니다. 해당 엔드포인트는 현재 폐기된 구 버전입니다.',
        impact: '낙찰결과 수집이 실패했습니다. 현재는 ScsbidInfoService로 대체 수집 중이므로 이후 일정에서는 정상 수집됩니다.',
      }
    }
    if (r.includes('500 internal server error')) {
      return {
        icon: 'api', severity: 'error',
        title: '나라장터 API 서버 오류',
        cause: '공공데이터포털(data.go.kr) 서버가 HTTP 500 오류를 반환했습니다. 서버 측 일시적 장애입니다.',
        impact: '해당 수집 배치가 실패했습니다. 다음 정기 수집 시 자동 재시도됩니다.',
      }
    }
    if (r.includes('404') || r.includes('not found')) {
      return {
        icon: 'api', severity: 'error',
        title: 'API 엔드포인트 없음',
        cause: '요청한 API 주소가 존재하지 않습니다. 엔드포인트 URL이 변경됐거나 폐기된 API입니다.',
        impact: '해당 수집 유형이 전체 실패했습니다. 엔드포인트 URL 점검이 필요합니다.',
      }
    }
    if (r.includes('connectionerror') || r.includes('connection refused') || r.includes('timeout') || r.includes('timed out')) {
      return {
        icon: 'network', severity: 'error',
        title: '네트워크 연결 실패',
        cause: '나라장터 API 서버에 연결할 수 없거나 응답 시간이 초과됐습니다. 네트워크 장애 또는 서버 점검 중일 수 있습니다.',
        impact: '해당 수집 배치가 실패했습니다. 다음 정기 수집 시 자동 재시도됩니다.',
      }
    }
    if (r.includes('페이지네이션 오류') || r.includes('api 호출 실패')) {
      return {
        icon: 'api', severity: 'error',
        title: 'API 호출 중단',
        cause: 'API 페이지 목록 조회 중 오류가 발생해 수집이 중단됐습니다. 이전 페이지까지의 데이터는 정상 저장됩니다.',
        impact: '일부 데이터가 수집되지 않았을 수 있습니다. 다음 정기 수집에서 보완됩니다.',
      }
    }
    if (r.includes('importerror') || r.includes('modulenotfounderror')) {
      return {
        icon: 'unknown', severity: 'error',
        title: '수집 모듈 로드 실패',
        cause: '수집 코드의 모듈 의존성 오류가 발생했습니다. 시스템 업데이트 후 재시작이 필요한 상태입니다.',
        impact: '수집이 전혀 실행되지 않았습니다. 컨테이너 재시작으로 해결됩니다.',
      }
    }
    if (r.includes('invalid api key') || r.includes('servicekey') || r.includes('인증') || r.includes('401') || r.includes('403')) {
      return {
        icon: 'auth', severity: 'error',
        title: 'API 인증 오류',
        cause: '공공데이터포털 API 키가 유효하지 않거나 만료됐습니다.',
        impact: '인증 문제가 해결될 때까지 수집이 불가합니다. API 키 재발급이 필요합니다.',
      }
    }
    return {
      icon: 'unknown', severity: 'error',
      title: '알 수 없는 오류',
      cause: '수집 중 예상치 못한 오류가 발생했습니다.',
      impact: '일부 데이터가 수집되지 않았을 수 있습니다. 다음 정기 수집에서 자동 재시도됩니다.',
    }
  }

  function groupErrorDetails(errors: string[]): Array<{ interpretation: ErrorInterpretation; count: number; samples: string[] }> {
    const groups = new Map<string, { interpretation: ErrorInterpretation; count: number; samples: string[] }>()
    for (const err of errors) {
      const interp = interpretErrorMessage(err)
      const key = interp.title
      const existing = groups.get(key)
      if (existing) {
        existing.count++
        if (existing.samples.length < 2) existing.samples.push(err.replace(/^\[.*?\]\s*/, '').slice(0, 60))
      } else {
        groups.set(key, { interpretation: interp, count: 1, samples: [] })
      }
    }
    return Array.from(groups.values())
  }

  function formatDateRange(from?: string, to?: string) {
    if (!from || !to) return null
    const fmt = (s: string) => `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)} ${s.slice(8,10)}:${s.slice(10,12)}`
    return `${fmt(from)} ~ ${fmt(to)}`
  }

  function CollectionLogModal() {
    if (!selectedLog) return null
    const meta = COLLECT_TYPE_META[selectedLog.collect_type] ?? { label: selectedLog.collect_type, color: 'bg-slate-100 text-slate-600 border-slate-200' }
    const detail: CollectionLogDetail = selectedLog.detail_json ? (() => { try { return JSON.parse(selectedLog.detail_json!) } catch { return {} } })() : {}
    const isSuccess = selectedLog.fail_count === 0
    const dateRange = formatDateRange(detail.date_from, detail.date_to)
    return (
      <Dialog open={!!selectedLog} onOpenChange={(o) => { if (!o) setSelectedLog(null) }}>
        <DialogContent className="max-w-lg bg-white">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-semibold text-slate-800">
              <Database className="h-4 w-4 text-blue-600" />수집 상세 정보
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-500">
              #{selectedLog.id} · {new Date(selectedLog.collected_at).toLocaleString('ko-KR')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-1">
            {/* 상태 요약 */}
            <div className={cn('flex items-center gap-3 px-4 py-3 rounded-lg border', isSuccess ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200')}>
              {isSuccess
                ? <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                : <AlertCircle className="h-5 w-5 text-red-500 shrink-0" />}
              <div>
                <p className={cn('text-sm font-semibold', isSuccess ? 'text-emerald-700' : 'text-red-700')}>
                  {isSuccess ? '수집 성공' : `수집 완료 (실패 ${selectedLog.fail_count}건 포함)`}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  성공 {selectedLog.success_count}건 · 실패 {selectedLog.fail_count}건 · 소요 {selectedLog.duration_sec?.toFixed(1) ?? '-'}초
                </p>
              </div>
            </div>

            {/* 수집 유형 + 소스 통합 */}
            <div className="space-y-2.5">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">수집 유형</p>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={cn('text-xs font-semibold px-2.5 py-1 rounded-full border', meta.color)}>
                  {meta.label}
                </span>
                <span className="text-xs text-slate-400 font-mono">{selectedLog.collect_type}</span>
              </div>
              {meta.data_desc && (
                <p className="text-xs text-slate-500 leading-relaxed">{meta.data_desc}</p>
              )}
            </div>

            {/* 수집 소스 */}
            <div className="space-y-2.5">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">수집 소스</p>
              <div className="bg-slate-50 rounded-lg border border-slate-200 divide-y divide-slate-100">
                {/* 제공 기관 */}
                <div className="flex items-start gap-3 px-3 py-2.5">
                  <span className="text-xs text-slate-400 w-16 shrink-0 pt-0.5">제공기관</span>
                  <span className="text-sm text-slate-700 font-medium">{detail.source ?? meta.source}</span>
                </div>
                {/* 수집 방식 */}
                <div className="flex items-start gap-3 px-3 py-2.5">
                  <span className="text-xs text-slate-400 w-16 shrink-0 pt-0.5">수집방식</span>
                  <span className="text-sm text-slate-700">{meta.method}</span>
                </div>
                {/* 엔드포인트 */}
                <div className="flex items-start gap-3 px-3 py-2.5">
                  <span className="text-xs text-slate-400 w-16 shrink-0 pt-0.5">엔드포인트</span>
                  <div className="min-w-0">
                    <span className="text-sm font-mono text-blue-600 break-all">{detail.endpoint ?? meta.endpoint}</span>
                  </div>
                </div>
                {/* API Base URL */}
                <div className="flex items-start gap-3 px-3 py-2.5">
                  <span className="text-xs text-slate-400 w-16 shrink-0 pt-0.5">Base URL</span>
                  <span className="text-xs font-mono text-slate-500 break-all">{detail.api_base ?? meta.api_base}</span>
                </div>
              </div>
            </div>

            {/* 수집 기간 */}
            {dateRange && (
              <div className="space-y-2.5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">수집 기간</p>
                <div className="bg-slate-50 rounded-lg border border-slate-200 px-3 py-2.5 flex items-center justify-between">
                  <span className="text-sm text-slate-700 font-mono">{dateRange}</span>
                  {detail.days_back && (
                    <span className="text-xs text-slate-400">최근 {detail.days_back}일</span>
                  )}
                </div>
              </div>
            )}

            {/* 처리 건수 */}
            {detail.total_processed !== undefined && (
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: 'API 처리', value: detail.total_processed, color: 'text-slate-700' },
                  { label: '저장 성공', value: selectedLog.success_count, color: 'text-emerald-600' },
                  { label: '저장 실패', value: selectedLog.fail_count, color: selectedLog.fail_count > 0 ? 'text-red-600' : 'text-slate-400' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-center">
                    <p className={cn('text-lg font-bold tabular-nums', color)}>{value}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                  </div>
                ))}
              </div>
            )}

            {/* 실패 원인 */}
            {(selectedLog.error_summary || (detail.error_details && detail.error_details.length > 0)) && (() => {
              const summaryInterp = selectedLog.error_summary ? interpretErrorMessage(selectedLog.error_summary) : null
              const detailGroups = detail.error_details && detail.error_details.length > 0
                ? groupErrorDetails(detail.error_details) : []
              const allGroups = summaryInterp
                ? [{ interpretation: summaryInterp, count: selectedLog.fail_count || 1, samples: [] }, ...detailGroups.filter(g => g.interpretation.title !== summaryInterp.title)]
                : detailGroups
              return (
                <div className="space-y-2.5">
                  <p className="text-xs font-semibold text-red-500 uppercase tracking-wide">실패 원인 분석</p>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {allGroups.map((group, i) => {
                      const { interpretation: interp, count } = group
                      const isWarning = interp.severity === 'warning'
                      return (
                        <div key={i} className={cn('rounded-lg border p-3 space-y-2', isWarning ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200')}>
                          {/* 제목 + 건수 */}
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2">
                              {isWarning
                                ? <AlertCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                                : <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />}
                              <span className={cn('text-sm font-semibold', isWarning ? 'text-amber-700' : 'text-red-700')}>{interp.title}</span>
                            </div>
                            {count > 1 && (
                              <span className={cn('text-xs font-bold px-2 py-0.5 rounded-full shrink-0', isWarning ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700')}>
                                {count}건
                              </span>
                            )}
                          </div>
                          {/* 원인 */}
                          <div>
                            <p className="text-xs font-medium text-slate-500 mb-1">원인</p>
                            <p className={cn('text-sm leading-relaxed', isWarning ? 'text-amber-800' : 'text-red-800')}>{interp.cause}</p>
                          </div>
                          {/* 영향 */}
                          <div>
                            <p className="text-xs font-medium text-slate-500 mb-1">영향 및 조치</p>
                            <p className={cn('text-sm leading-relaxed', isWarning ? 'text-amber-700' : 'text-red-700')}>{interp.impact}</p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })()}
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <CollectionLogModal />
      {/* Sticky Header */}
      <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-red-50 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-red-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">관리자</h1>
            <p className="text-sm text-slate-500 mt-0.5">시스템 상태, 사용자, 공종, 수집기 관리</p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-5">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-slate-100 border border-slate-200 p-1">
            <TabsTrigger value="system" className="gap-1.5 data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">
              <Activity className="h-3.5 w-3.5" />시스템 현황
            </TabsTrigger>
            <TabsTrigger value="collection" className="gap-1.5 data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">
              <Download className="h-3.5 w-3.5" />수집 현황
            </TabsTrigger>
            <TabsTrigger value="users" className="gap-1.5 data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">
              <Users className="h-3.5 w-3.5" />사용자 관리
            </TabsTrigger>
            <TabsTrigger value="industries" className="gap-1.5 data-[state=active]:bg-white data-[state=active]:shadow-sm data-[state=active]:text-blue-600 text-slate-600 font-medium">
              <Layers className="h-3.5 w-3.5" />공종 관리
            </TabsTrigger>
          </TabsList>

          {/* 시스템 현황 탭 */}
          <TabsContent value="system" className="space-y-5 mt-4">
            {statusLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : stats ? (
              <>
                {/* DB 통계 카드 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: '전체 공고', value: stats.total_bids.toLocaleString(), sub: `나라장터 ${stats.g2b_bids.toLocaleString()}건`, icon: Database, bar: 'bg-blue-500', iconBg: 'bg-blue-50', iconColor: 'text-blue-600' },
                    { label: '7일 신규', value: stats.new_bids_7d.toLocaleString(), icon: Activity, bar: 'bg-emerald-500', iconBg: 'bg-emerald-50', iconColor: 'text-emerald-600' },
                    { label: '개찰결과', value: stats.total_results.toLocaleString(), icon: Activity, bar: 'bg-violet-500', iconBg: 'bg-violet-50', iconColor: 'text-violet-600' },
                    { label: '경쟁사', value: stats.total_competitors.toLocaleString(), icon: Users, bar: 'bg-amber-500', iconBg: 'bg-amber-50', iconColor: 'text-amber-600' },
                  ].map(({ label, value, sub, icon: Icon, bar, iconBg, iconColor }) => (
                    <Card key={label} className="relative overflow-hidden bg-white border-slate-200 shadow-sm">
                      <div className={cn('absolute top-0 left-0 right-0 h-0.5', bar)} />
                      <CardContent className="p-5">
                        <div className="flex items-start justify-between">
                          <div>
                            <p className="text-sm font-medium text-slate-500">{label}</p>
                            <p className="text-2xl font-bold mt-1 tabular-nums text-slate-900">{value}</p>
                            {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
                          </div>
                          <div className={cn('rounded-xl p-2.5', iconBg)}>
                            <Icon className={cn('h-5 w-5', iconColor)} />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  {/* 수집기 상태 */}
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                          <Activity className="h-4 w-4 text-blue-600" />수집기 상태
                        </CardTitle>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-blue-600" onClick={() => { refetchStatus(); refetchCollectorStatus() }}>
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent className="p-5 space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">상태</span>
                        <span className={cn('text-xs font-semibold px-2.5 py-1 rounded-full border', collector?.enabled ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-100 text-slate-500 border-slate-200')}>
                          {collector?.enabled ? '활성' : '비활성'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">오늘 수집 공고</span>
                        <span className="text-sm font-semibold text-blue-600 tabular-nums">{(collectorStatus?.today_notices ?? 0).toLocaleString()}건</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">오늘 수집 결과</span>
                        <span className="text-sm font-semibold text-violet-600 tabular-nums">{(collectorStatus?.today_results ?? 0).toLocaleString()}건</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">마지막 수집</span>
                        <span className="text-sm text-slate-600">
                          {collectorStatus?.last_run_at
                            ? new Date(collectorStatus.last_run_at).toLocaleString('ko-KR')
                            : collector?.last_g2b_collect
                            ? new Date(collector.last_g2b_collect).toLocaleString('ko-KR')
                            : '없음'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">다음 수집 예정</span>
                        <span className="text-xs text-emerald-600 font-medium">
                          {collectorStatus?.next_run_at ? new Date(collectorStatus.next_run_at).toLocaleString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : '-'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">활성 키워드</span>
                        <span className="text-sm font-medium text-slate-700">{stats.active_keywords}개</span>
                      </div>
                      {status?.daily_collection && status.daily_collection.length > 0 && (
                        <div className="border-t border-slate-100 pt-3 mt-1">
                          <div className="text-sm font-medium text-slate-500 mb-2">최근 수집 현황</div>
                          <div className="space-y-1">
                            {status.daily_collection.slice(0, 5).map((d) => (
                              <div key={d.date} className="flex justify-between text-xs">
                                <span className="text-slate-500">{d.date}</span>
                                <span className="text-slate-600 font-medium">{d.count.toLocaleString()}건</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* ML 모델 상태 */}
                  <Card className="bg-white border-slate-200 shadow-sm">
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                          <Zap className="h-4 w-4 text-blue-600" />ML 모델 상태
                        </CardTitle>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs border-slate-200 text-slate-600 hover:bg-slate-50 gap-1"
                          onClick={() => retrainMutation.mutate()}
                          disabled={retrainMutation.isPending}
                        >
                          {retrainMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                          재학습
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent className="p-5">
                      {modelInfo ? (
                        <div className="space-y-3">
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-500">모델 버전</span>
                            <span className="font-mono text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded">{modelInfo.model.version}</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-500">학습 데이터</span>
                            <span className="text-sm font-semibold text-slate-700">{(modelInfo.model.train_size || 0).toLocaleString()}건</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-500">낙찰 데이터</span>
                            <span className="text-sm font-semibold text-slate-700">{(modelInfo.model.winner_size || 0).toLocaleString()}건</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-500">ML 준비</span>
                            <span className={cn('text-xs font-semibold px-2.5 py-1 rounded-full border',
                              modelInfo.data_availability.ready_for_ml
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : 'bg-amber-50 text-amber-600 border-amber-200'
                            )}>
                              {modelInfo.data_availability.ready_for_ml ? '가능' : `미충족 (${modelInfo.data_availability.winner_results}/20건)`}
                            </span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-sm text-slate-500">30일 추천 요청</span>
                            <span className="text-sm font-medium text-slate-700">{modelInfo.usage.predictions_30d}회</span>
                          </div>
                          {retrainMutation.isSuccess && (
                            <div className="text-xs text-emerald-600 font-medium bg-emerald-50 rounded-lg px-3 py-2">재학습 완료!</div>
                          )}
                          {retrainMutation.isError && (
                            <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">재학습 실패 (관리자 권한 필요)</div>
                          )}
                        </div>
                      ) : (
                        <div className="text-sm text-slate-500 py-4 text-center">정보 없음</div>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* 수집 이력 테이블 */}
                {collectionLogs.length > 0 && (
                  <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                        <Database className="h-4 w-4 text-blue-600" />수집 이력 (최근 7일)
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow className="bg-slate-50 border-b border-slate-200">
                            <TableHead className="text-slate-600 font-semibold">수집 유형</TableHead>
                            <TableHead className="text-slate-600 font-semibold">수집 시각</TableHead>
                            <TableHead className="text-center text-slate-600 font-semibold">성공</TableHead>
                            <TableHead className="text-center text-slate-600 font-semibold">실패</TableHead>
                            <TableHead className="text-right text-slate-600 font-semibold">소요(초)</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {collectionLogs.map((log) => {
                            const m = COLLECT_TYPE_META[log.collect_type] ?? { label: log.collect_type, color: 'bg-slate-100 text-slate-600 border-slate-200' }
                            return (
                            <TableRow key={log.id} onClick={() => setSelectedLog(log)} className="hover:bg-blue-50/40 border-b border-slate-100 cursor-pointer">
                              <TableCell>
                                <span className={cn('text-xs font-semibold px-2.5 py-0.5 rounded-full border', m.color)}>{m.label}</span>
                              </TableCell>
                              <TableCell className="text-sm text-slate-500 whitespace-nowrap">
                                {new Date(log.collected_at).toLocaleString('ko-KR')}
                              </TableCell>
                              <TableCell className={cn('text-center font-bold text-sm', log.success_count > 0 ? 'text-emerald-600' : 'text-slate-500')}>
                                {log.success_count}
                              </TableCell>
                              <TableCell className={cn('text-center font-bold text-sm', log.fail_count > 0 ? 'text-red-600' : 'text-slate-400')}>
                                {log.fail_count}
                              </TableCell>
                              <TableCell className="text-right text-sm text-slate-500">{log.duration_sec?.toFixed(1) ?? '-'}</TableCell>
                            </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : null}
          </TabsContent>

          {/* 수집 현황 탭 */}
          <TabsContent value="collection" className="space-y-4 mt-4">
            {user?.role !== 'admin' ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                <ShieldCheck className="h-10 w-10 text-slate-200 mb-3" />
                <p className="text-sm">관리자만 접근할 수 있습니다.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-semibold text-slate-700">최근 수집 이력 (7일)</h2>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-blue-600" onClick={() => refetchLogs()}>
                      <RefreshCw className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="relative">
                    <Button
                      className="gap-2 bg-blue-600 hover:bg-blue-700"
                      onClick={() => setDropdownOpen((v) => !v)}
                      onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                      disabled={triggerMutation.isPending}
                    >
                      {triggerMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                      지금 수집
                      <ChevronDown className="h-3.5 w-3.5" />
                    </Button>
                    {dropdownOpen && (
                      <div className="absolute right-0 top-full mt-1 z-10 bg-white border border-slate-200 rounded-lg shadow-lg py-1 w-28">
                        {([['all', '전체'], ['notices', '공고만'], ['results', '결과만']] as const).map(([value, label]) => (
                          <button
                            key={value}
                            className="w-full text-left text-sm px-3 py-2 hover:bg-slate-50 transition-colors text-slate-700"
                            onMouseDown={() => { setDropdownOpen(false); triggerMutation.mutate(value) }}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {triggerMsg && (
                  <div className={cn('flex items-center gap-2 text-sm px-4 py-3 rounded-lg border',
                    triggerMsg.type === 'success'
                      ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                      : 'text-red-700 bg-red-50 border-red-200'
                  )}>
                    {triggerMsg.text}
                  </div>
                )}

                {/* inpo21c 연동 상태 */}
                <Card className="bg-white border-slate-200 shadow-sm">
                  <CardHeader className="border-b border-slate-100 pb-4">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                        <Activity className="h-4 w-4 text-blue-600" />inpo21c 연동 상태
                      </CardTitle>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-blue-600" onClick={() => refetchInpoStatus()}>
                        <RefreshCw className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="p-5 space-y-4">
                    {/* 연결 상태 + 수집 버튼 */}
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className={cn('shrink-0 text-xs font-semibold px-3 py-1 rounded-full border',
                          inpoStatus?.cookie_valid
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : inpoStatus?.has_autologin
                            ? 'bg-blue-50 text-blue-700 border-blue-200'
                            : inpoStatus?.has_cookie
                            ? 'bg-red-50 text-red-700 border-red-200'
                            : 'bg-slate-100 text-slate-500 border-slate-200'
                        )}>
                          {inpoStatus?.cookie_valid ? '쿠키 정상'
                            : inpoStatus?.has_autologin ? '자동 로그인'
                            : inpoStatus?.has_cookie ? '쿠키 만료'
                            : '쿠키 미설정'}
                        </span>
                        <span className="text-sm text-slate-500 truncate">{inpoStatus?.message ?? '상태 확인 중...'}</span>
                      </div>
                      <Button
                        size="sm"
                        className="shrink-0 gap-2 bg-blue-600 hover:bg-blue-700"
                        disabled={!inpoStatus?.can_collect || inpoCollectMutation.isPending || inpoProgress?.running}
                        onClick={() => inpoCollectMutation.mutate()}
                      >
                        {(inpoCollectMutation.isPending || inpoProgress?.running)
                          ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          : <Download className="h-3.5 w-3.5" />}
                        {inpoProgress?.running ? '수집 중...' : 'inpo21c 즉시 수집'}
                      </Button>
                    </div>

                    {/* 진행 상황 패널 (수집 중 또는 완료 직후) */}
                    {inpoProgress && (inpoProgress.running || inpoProgress.finished_at) && (
                      <div className={cn(
                        'rounded-xl border p-4 space-y-3',
                        inpoProgress.error
                          ? 'bg-red-50 border-red-200'
                          : inpoProgress.running
                          ? 'bg-blue-50 border-blue-200'
                          : 'bg-emerald-50 border-emerald-200'
                      )}>
                        {/* 헤더 */}
                        <div className="flex items-center justify-between">
                          <span className={cn('text-xs font-semibold',
                            inpoProgress.error ? 'text-red-700'
                              : inpoProgress.running ? 'text-blue-700'
                              : 'text-emerald-700'
                          )}>
                            {inpoProgress.error ? '수집 오류'
                              : inpoProgress.running
                              ? `수집 중 — ${inpoProgress.job_type === 'national' ? '전국' : '맞춤설정'} 모드`
                              : '수집 완료'}
                          </span>
                          <span className="text-[11px] text-slate-500">
                            {inpoProgress.running
                              ? `페이지 ${inpoProgress.page} / ${inpoProgress.max_pages}`
                              : inpoProgress.finished_at
                              ? new Date(inpoProgress.finished_at).toLocaleTimeString('ko-KR')
                              : ''}
                          </span>
                        </div>

                        {/* 프로그레스 바 */}
                        <div className="w-full h-2 bg-white/60 rounded-full overflow-hidden">
                          <div
                            className={cn(
                              'h-full rounded-full transition-all duration-500',
                              inpoProgress.error ? 'bg-red-400'
                                : inpoProgress.running ? 'bg-blue-500'
                                : 'bg-emerald-500'
                            )}
                            style={{ width: `${inpoProgress.pct}%` }}
                          />
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>{inpoProgress.pct.toFixed(1)}%</span>
                          {inpoProgress.running && (
                            <span className="flex items-center gap-1">
                              <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                              처리 중
                            </span>
                          )}
                        </div>

                        {/* 수집 카운터 */}
                        <div className="grid grid-cols-4 gap-2">
                          {[
                            { label: '신규 공고', value: inpoProgress.bids, color: 'text-blue-700' },
                            { label: '참여자', value: inpoProgress.participants, color: 'text-violet-700' },
                            { label: '예가', value: inpoProgress.yega, color: 'text-amber-700' },
                            { label: '스킵', value: inpoProgress.skipped, color: 'text-slate-500' },
                          ].map(({ label, value, color }) => (
                            <div key={label} className="bg-white/70 rounded-lg p-2 text-center">
                              <p className={cn('text-base font-bold tabular-nums', color)}>{value.toLocaleString()}</p>
                              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                            </div>
                          ))}
                        </div>

                        {/* 오류 메시지 */}
                        {inpoProgress.error && (
                          <p className="text-xs text-red-600 bg-red-100 rounded px-3 py-2">{inpoProgress.error}</p>
                        )}
                      </div>
                    )}

                    {inpoCollectMsg && (
                      <div className={cn('text-sm px-4 py-3 rounded-lg border',
                        inpoCollectMsg.type === 'success'
                          ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                          : 'text-red-700 bg-red-50 border-red-200'
                      )}>
                        {inpoCollectMsg.text}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* 수집 로그 테이블 */}
                <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
                  <CardHeader className="border-b border-slate-100 pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                        <Database className="h-4 w-4 text-blue-600" />수집 이력
                      </CardTitle>
                      <span className="text-xs text-slate-400 flex items-center gap-1">
                        <Info className="h-3 w-3" />행 클릭 시 상세 정보
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-slate-50 border-b border-slate-200">
                          <TableHead className="text-slate-600 font-semibold">수집 일시</TableHead>
                          <TableHead className="text-slate-600 font-semibold">유형</TableHead>
                          <TableHead className="text-center text-slate-600 font-semibold">성공</TableHead>
                          <TableHead className="text-center text-slate-600 font-semibold">실패</TableHead>
                          <TableHead className="text-right text-slate-600 font-semibold">소요시간(초)</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {collectionLogs.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={5} className="text-center py-12 text-slate-500">
                              수집 이력이 없습니다.
                            </TableCell>
                          </TableRow>
                        ) : collectionLogs.map((log) => {
                          const m = COLLECT_TYPE_META[log.collect_type] ?? { label: log.collect_type, color: 'bg-slate-100 text-slate-600 border-slate-200' }
                          return (
                          <TableRow key={log.id} onClick={() => setSelectedLog(log)} className="hover:bg-blue-50/40 border-b border-slate-100 cursor-pointer">
                            <TableCell className="text-sm text-slate-500 whitespace-nowrap">
                              {new Date(log.collected_at).toLocaleString('ko-KR')}
                            </TableCell>
                            <TableCell>
                              <span className={cn('text-xs font-semibold px-2.5 py-0.5 rounded-full border', m.color)}>{m.label}</span>
                            </TableCell>
                            <TableCell className={cn('text-center font-bold text-sm', log.success_count > 0 ? 'text-emerald-600' : 'text-slate-500')}>
                              {log.success_count}
                            </TableCell>
                            <TableCell className={cn('text-center font-bold text-sm', log.fail_count > 0 ? 'text-red-600' : 'text-slate-400')}>
                              {log.fail_count}
                            </TableCell>
                            <TableCell className="text-right text-sm text-slate-500">
                              {log.duration_sec?.toFixed(1) ?? '-'}
                            </TableCell>
                          </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>

          {/* 사용자 관리 탭 */}
          <TabsContent value="users" className="space-y-4 mt-4">
            <div className="flex justify-end">
              <Button onClick={() => { resetForm(); setShowForm(true) }} className="gap-2 bg-blue-600 hover:bg-blue-700">
                <Plus className="h-4 w-4" />사용자 추가
              </Button>
            </div>

            {showForm && (
              <Card className="bg-white border-slate-200 shadow-sm">
                <CardHeader className="border-b border-slate-100 pb-4">
                  <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                    <Users className="h-4 w-4 text-blue-600" />{editId !== null ? '사용자 수정' : '새 사용자 추가'}
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5">
                  <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {editId === null && (
                      <div className="space-y-1.5">
                        <Label className="text-sm font-medium text-slate-600">이메일 *</Label>
                        <Input type="email" value={form.email} required onChange={(e) => setForm({ ...form, email: e.target.value })} className="border-slate-200" />
                      </div>
                    )}
                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium text-slate-600">이름 *</Label>
                      <Input type="text" value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} className="border-slate-200" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium text-slate-600">{editId ? '비밀번호 (변경 시만)' : '비밀번호 *'}</Label>
                      <Input type="password" value={form.password} required={editId === null} onChange={(e) => setForm({ ...form, password: e.target.value })} className="border-slate-200" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium text-slate-600">역할</Label>
                      <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                        <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="viewer">뷰어</SelectItem>
                          <SelectItem value="analyst">분석가</SelectItem>
                          <SelectItem value="admin">관리자</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium text-slate-600">부서</Label>
                      <Input type="text" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} className="border-slate-200" />
                    </div>
                    <div className="md:col-span-3 flex justify-end gap-2 pt-1">
                      <Button type="button" variant="outline" onClick={resetForm} className="border-slate-200 text-slate-600">취소</Button>
                      <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending} className="bg-blue-600 hover:bg-blue-700 gap-2">
                        {(createMutation.isPending || updateMutation.isPending) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        {editId !== null ? '수정' : '추가'}
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            )}

            <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
              {usersLoading ? (
                <div className="p-6 space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 border-b border-slate-200">
                      <TableHead className="text-slate-600 font-semibold">이름</TableHead>
                      <TableHead className="text-slate-600 font-semibold">이메일</TableHead>
                      <TableHead className="text-slate-600 font-semibold">역할</TableHead>
                      <TableHead className="text-slate-600 font-semibold">부서</TableHead>
                      <TableHead className="text-slate-600 font-semibold">마지막 로그인</TableHead>
                      <TableHead className="text-slate-600 font-semibold">상태</TableHead>
                      <TableHead className="text-slate-600 font-semibold">관리</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((u) => {
                      const roleConf = ROLE_CONFIG[u.role] ?? ROLE_CONFIG.viewer
                      return (
                        <TableRow key={u.id} className={cn('hover:bg-slate-50/50 border-b border-slate-100 transition-colors', !u.is_active && 'opacity-50')}>
                          <TableCell className="font-semibold text-slate-800">{u.name || '-'}</TableCell>
                          <TableCell className="text-slate-500 text-sm">{u.email}</TableCell>
                          <TableCell>
                            <span className={cn('text-xs font-semibold px-2.5 py-1 rounded-full', roleConf.cls)}>
                              {roleConf.label}
                            </span>
                          </TableCell>
                          <TableCell className="text-slate-500 text-sm">{u.department || '-'}</TableCell>
                          <TableCell className="text-slate-500 text-xs">{u.last_login ? new Date(u.last_login).toLocaleString('ko-KR') : '없음'}</TableCell>
                          <TableCell>
                            <Button
                              size="sm"
                              variant="outline"
                              className={cn('h-6 text-xs px-2.5 border font-medium', u.is_active ? 'border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100' : 'border-slate-200 text-slate-500 hover:bg-slate-100')}
                              onClick={() => updateMutation.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                            >
                              {u.is_active ? '활성' : '비활성'}
                            </Button>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-blue-600 hover:bg-blue-50" onClick={() => handleEdit(u)}>
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-red-600 hover:bg-red-50" onClick={() => setDeleteConfirm(u.id)}>
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              )}
            </Card>
          </TabsContent>

          {/* 공종 관리 탭 */}
          <TabsContent value="industries" className="space-y-4 mt-4">
            <div className="flex items-start gap-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-700">
              <Layers className="h-4 w-4 shrink-0 mt-0.5 text-blue-500" />
              <span><strong>공종 필터 설정</strong> — 체크된 공종의 입찰만 시스템 전체에서 활용됩니다.</span>
            </div>
            {indLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                      <Input
                        value={indSearch}
                        onChange={(e) => setIndSearch(e.target.value)}
                        placeholder="공종 검색..."
                        className="pl-9 w-64 border-slate-200 bg-white"
                      />
                    </div>
                    <Button variant="outline" size="sm" onClick={() => { setCheckedIds(new Set(industryFilters.map((i) => i.industry_id))); setIndSaved(false) }} className="border-slate-200 text-slate-600 gap-1">
                      <CheckSquare className="h-3.5 w-3.5" />전체 선택
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => { setCheckedIds(new Set()); setIndSaved(false) }} className="border-slate-200 text-slate-600 gap-1">
                      <Square className="h-3.5 w-3.5" />전체 해제
                    </Button>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-500">
                      <strong className="text-blue-600">{activeCount}</strong> / {totalCount}개 선택됨
                      {activeCount === totalCount && <span className="ml-1 text-xs text-emerald-600">(전체 = 필터 없음)</span>}
                    </span>
                    <Button
                      size="sm"
                      onClick={() => saveIndMutation.mutate(Array.from(currentChecked))}
                      disabled={saveIndMutation.isPending}
                      className="gap-2 bg-blue-600 hover:bg-blue-700"
                    >
                      {saveIndMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      {saveIndMutation.isPending ? '저장 중...' : '저장'}
                    </Button>
                    {indSaved && <span className="text-xs text-emerald-600 font-medium">저장 완료!</span>}
                    {saveIndMutation.isError && <span className="text-xs text-red-600">저장 실패</span>}
                  </div>
                </div>

                <Card className="bg-white border-slate-200 shadow-sm overflow-hidden">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 divide-y divide-slate-100 md:divide-y-0 md:[&>*:nth-child(n)]:border-b md:[&>*:nth-child(n)]:border-slate-100">
                    {filteredIndustries.length === 0 ? (
                      <div className="col-span-3 p-10 text-center text-slate-500">
                        <Search className="h-8 w-8 mx-auto mb-2 text-slate-200" />
                        <p className="text-sm">검색 결과 없음</p>
                      </div>
                    ) : filteredIndustries.map((ind) => {
                      const checked = currentChecked.has(ind.industry_id)
                      return (
                        <label
                          key={ind.industry_id}
                          className={cn('flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors hover:bg-slate-50 border-b border-slate-100', checked && 'bg-blue-50/50')}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleIndustry(ind.industry_id)}
                            className="w-4 h-4 rounded accent-blue-600 cursor-pointer shrink-0"
                          />
                          <div className="min-w-0 flex-1">
                            <div className={cn('text-sm font-medium truncate', checked ? 'text-blue-700' : 'text-slate-700')}>{ind.name}</div>
                            <div className="text-xs text-slate-500 font-mono">{ind.code}</div>
                          </div>
                          {checked && (
                            <span className="text-xs font-semibold px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-600 border border-blue-200 ml-auto shrink-0">
                              활성
                            </span>
                          )}
                        </label>
                      )
                    })}
                  </div>
                </Card>
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* 사용자 삭제 다이얼로그 */}
      <Dialog open={deleteConfirm !== null} onOpenChange={(o) => { if (!o) setDeleteConfirm(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-slate-900 font-semibold">사용자 삭제</DialogTitle>
            <DialogDescription className="text-slate-500">이 사용자를 삭제하시겠습니까?</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteConfirm(null)} className="border-slate-200">취소</Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirm !== null && deleteMutation.mutate(deleteConfirm)}
              disabled={deleteMutation.isPending}
              className="gap-2"
            >
              {deleteMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}삭제
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
