import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  CheckCircle, XCircle, AlertCircle, Server, Activity, Send,
  Plus, Trash2, ToggleLeft, ToggleRight, Brain, Star, TrendingUp,
} from 'lucide-react'
import { systemApi } from '@/api/market'
import { settingsApi } from '@/api/settings'
import type { TelegramConfig, ModelStatus } from '@/api/settings'
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { ModelPerformance } from './ModelPerformance'
import { Tracking }        from './Tracking'
import { Watchlist }       from './Watchlist'
import { NotificationHistory } from './NotificationHistory'

// ── 탭 정의 ──────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'system',   label: '시스템',   icon: <Server size={13} /> },
  { id: 'model',    label: '모델 성능', icon: <Activity size={13} /> },
  { id: 'tracking', label: '성과 추적', icon: <TrendingUp size={13} /> },
  { id: 'watchlist',label: '관심종목', icon: <Star size={13} /> },
  { id: 'alerts',   label: '알림 이력', icon: <Send size={13} /> },
] as const
type TabId = typeof TABS[number]['id']

// ── ModelStatusCard ───────────────────────────────────────────────────────────
function ModelStatusCard() {
  const { data: ms, isLoading } = useQuery<ModelStatus>({
    queryKey: ['settings', 'model-status'],
    queryFn:  settingsApi.getModelStatus,
    retry: 1,
  })
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={15} className="text-purple-400" />
          <CardTitle>ML 모델 상태</CardTitle>
        </div>
        {ms && (
          <span className={clsx(
            'text-xs font-semibold px-2 py-0.5 rounded-full',
            ms.mode === 'lgbm'
              ? 'bg-green-500/15 text-green-400'
              : 'bg-yellow-500/15 text-yellow-400'
          )}>
            {ms.mode === 'lgbm' ? 'LightGBM 모드' : '규칙 기반 모드'}
          </span>
        )}
        {isLoading && <div className="h-5 skeleton rounded w-24" />}
      </CardHeader>
      <CardBody className="pt-3">
        {ms?.warning && (
          <div className="mb-3 p-3 rounded-xl bg-yellow-500/10 border border-yellow-500/25 flex items-start gap-2">
            <AlertCircle size={14} className="text-yellow-400 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-yellow-300">{ms.warning}</p>
          </div>
        )}
        {ms && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
              <div className="text-[10px] text-[var(--muted)] mb-1">학습일</div>
              <div className="text-sm font-semibold text-[var(--fg)] tabular">
                {ms.file_mtime ?? ms.trained_at ?? '비학습'}
              </div>
            </div>
            <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
              <div className="text-[10px] text-[var(--muted)] mb-1">피처 수</div>
              <div className="text-sm font-semibold text-[var(--fg)] tabular">
                {ms.feature_count != null ? `${ms.feature_count}개` : '—'}
              </div>
            </div>
            <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
              <div className="text-[10px] text-[var(--muted)] mb-1">AUC</div>
              <div className="text-sm font-semibold text-[var(--fg)] tabular">
                {ms.metrics?.auc != null ? ms.metrics.auc.toFixed(3) : '—'}
              </div>
            </div>
            <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
              <div className="text-[10px] text-[var(--muted)] mb-1">F1 / Recall</div>
              <div className="text-sm font-semibold text-[var(--fg)] tabular">
                {ms.metrics?.f1 != null ? ms.metrics.f1.toFixed(3) : '—'}
                {ms.metrics?.recall != null && <span className="text-[var(--muted)]"> / {ms.metrics.recall.toFixed(3)}</span>}
              </div>
            </div>
          </div>
        )}
        {!ms && !isLoading && (
          <div className="text-xs text-[var(--muted)] py-2">모델 상태 조회 실패</div>
        )}
      </CardBody>
    </Card>
  )
}

interface HealthResponse {
  status: string
  components?: Record<string, string>
  version?: string
  uptime_seconds?: number
}

const THRESHOLDS = [
  { label: 'VOLUME_SURGE 배수',        key: 'VOLUME_SURGE_RATIO',  env: 'VOLUME_SURGE_RATIO',   default: '3.0' },
  { label: 'AMOUNT_SURGE 배수',        key: 'AMOUNT_SURGE_RATIO',  env: 'AMOUNT_SURGE_RATIO',   default: '3.0' },
  { label: '고점 돌파 최소 등락률 (%)', key: 'BREAKOUT_MIN_CHANGE', env: 'BREAKOUT_MIN_CHANGE',  default: '1.0' },
  { label: '장대양봉 최소 몸통 (%)',    key: 'CANDLE_BODY_MIN',     env: 'CANDLE_BODY_MIN_PCT',  default: '5.0' },
  { label: 'VI 발동 임계값 (%)',        key: 'VI_THRESHOLD',        env: 'VI_THRESHOLD_PCT',     default: '10.0' },
  { label: 'ML 매수 최소 확률',        key: 'ML_BUY_THRESHOLD',    env: 'ML_BUY_THRESHOLD',     default: '0.55' },
  { label: 'ATR 손절 배수',           key: 'ATR_STOP_MULT',       env: 'ATR_STOP_MULT',        default: '1.5' },
  { label: 'ATR 목표 배수',           key: 'ATR_TARGET_MULT',     env: 'ATR_TARGET_MULT',      default: '3.0' },
  { label: '유사 사례 Top-K',         key: 'SIMILAR_TOP_K',       env: 'SIMILAR_TOP_K',        default: '10' },
  { label: 'K-Means 테마 클러스터 수', key: 'N_CLUSTERS',          env: 'N_CLUSTERS',           default: '30' },
]

function StatusIcon({ status }: { status: string }) {
  if (status === 'ok' || status === 'healthy' || status === 'connected')
    return <CheckCircle size={14} className="text-green-400" />
  if (status === 'degraded' || status === 'warning')
    return <AlertCircle size={14} className="text-yellow-400" />
  return <XCircle size={14} className="text-red-400" />
}

function statusColor(s: string) {
  if (s === 'ok' || s === 'healthy' || s === 'connected') return 'text-green-400'
  if (s === 'degraded' || s === 'warning') return 'text-yellow-400'
  return 'text-red-400'
}

function formatUptime(seconds?: number) {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function TelegramSection() {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<TelegramConfig | null>(null)
  const [saved, setSaved] = useState(false)

  const { data: cfg, isLoading } = useQuery<TelegramConfig>({
    queryKey: ['settings', 'telegram'],
    queryFn:  settingsApi.getTelegram,
  })

  useEffect(() => {
    if (cfg && !draft) setDraft(cfg)
  }, [cfg])

  const updateMut = useMutation({
    mutationFn: settingsApi.updateTelegram,
    onSuccess: (d: TelegramConfig) => {
      setDraft(d)
      qc.setQueryData<TelegramConfig>(['settings', 'telegram'], d)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const handleSave = () => { if (draft) updateMut.mutate(draft) }

  if (isLoading || !draft) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-10 skeleton rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between p-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
        <div>
          <div className="text-sm font-semibold text-[var(--fg)]">텔레그램 알림</div>
          <div className="text-xs text-[var(--muted)] mt-0.5">매수 신호 및 공시 알림 발송 활성화</div>
        </div>
        <button onClick={() => setDraft({ ...draft, enabled: !draft.enabled })} className="text-[var(--muted)] hover:text-cyan-400 transition-colors">
          {draft.enabled ? <ToggleRight size={28} className="text-cyan-400" /> : <ToggleLeft size={28} />}
        </button>
      </div>

      <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-semibold text-[var(--fg)]">매수 신호 최소 성공확률</div>
            <div className="text-xs text-[var(--muted)] mt-0.5">이 확률 이상인 신호만 텔레그램 발송</div>
          </div>
          <code className="text-lg font-bold text-cyan-400 tabular">{(draft.min_prob * 100).toFixed(0)}%</code>
        </div>
        <input
          type="range" min={0} max={100} step={1}
          value={Math.round(draft.min_prob * 100)}
          onChange={(e) => setDraft({ ...draft, min_prob: Number(e.target.value) / 100 })}
          className="w-full accent-cyan-400"
        />
        <div className="flex justify-between text-[10px] text-[var(--muted)] mt-1">
          <span>0%</span><span>50%</span><span>100%</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
          <div className="text-xs text-[var(--muted)] mb-1">최대 리스크 점수</div>
          <input
            type="number" min={0} max={1} step={0.05}
            value={draft.max_risk}
            onChange={(e) => setDraft({ ...draft, max_risk: Number(e.target.value) })}
            className="w-full bg-transparent text-sm font-semibold text-[var(--fg)] outline-none tabular"
          />
        </div>
        <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
          <div className="text-xs text-[var(--muted)] mb-1">최소 Risk/Reward</div>
          <input
            type="number" min={0} max={10} step={0.1}
            value={draft.min_risk_reward}
            onChange={(e) => setDraft({ ...draft, min_risk_reward: Number(e.target.value) })}
            className="w-full bg-transparent text-sm font-semibold text-[var(--fg)] outline-none tabular"
          />
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={updateMut.isPending}
        className={clsx(
          'w-full py-2.5 rounded-xl text-sm font-semibold transition-colors',
          saved
            ? 'bg-green-500/20 text-green-400 border border-green-500/30'
            : 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20',
        )}
      >
        {saved ? '저장됨 ✓' : updateMut.isPending ? '저장 중…' : '설정 저장'}
      </button>
    </div>
  )
}

function KeywordsSection() {
  const qc = useQueryClient()
  const [newKw, setNewKw] = useState('')

  const { data: cfg } = useQuery<TelegramConfig>({
    queryKey: ['settings', 'telegram'],
    queryFn:  settingsApi.getTelegram,
  })

  const addKwMut = useMutation({
    mutationFn: (kw: string) => settingsApi.addKeyword(kw),
    onSuccess: (d: TelegramConfig) => { qc.setQueryData<TelegramConfig>(['settings', 'telegram'], d); setNewKw('') },
  })
  const delKwMut = useMutation({
    mutationFn: (kw: string) => settingsApi.removeKeyword(kw),
    onSuccess: (d: TelegramConfig) => qc.setQueryData<TelegramConfig>(['settings', 'telegram'], d),
  })

  const keywords = cfg?.disclosure_keywords ?? []

  return (
    <div className="space-y-3">
      <div className="text-xs text-[var(--muted)]">키워드가 공시 제목에 포함된 경우 텔레그램 알림을 발송합니다.</div>
      <div className="flex gap-2">
        <input
          value={newKw}
          onChange={(e) => setNewKw(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && newKw.trim()) addKwMut.mutate(newKw.trim()) }}
          placeholder="키워드 입력 (예: 유상증자)"
          className="flex-1 bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-500"
        />
        <button
          onClick={() => { if (newKw.trim()) addKwMut.mutate(newKw.trim()) }}
          disabled={!newKw.trim() || addKwMut.isPending}
          className="px-3 py-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 transition-colors disabled:opacity-40"
        >
          <Plus size={14} />
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {keywords.map((kw) => (
          <div key={kw} className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--border)] text-sm text-[var(--fg)]">
            <span>#{kw}</span>
            <button onClick={() => delKwMut.mutate(kw)} className="text-[var(--muted)] hover:text-red-400 transition-colors">
              <Trash2 size={11} />
            </button>
          </div>
        ))}
        {keywords.length === 0 && <div className="text-xs text-[var(--muted)]">등록된 키워드가 없습니다.</div>}
      </div>
    </div>
  )
}

// ── 시스템 탭 콘텐츠 ──────────────────────────────────────────────────────────
function SystemTab() {
  const { data: health, isLoading, error } = useQuery<HealthResponse>({
    queryKey:       ['health'],
    queryFn:        systemApi.health,
    refetchInterval: 30_000,
    retry:           1,
  })

  const components = health?.components ?? {}
  const serviceEntries = Object.entries(components).length > 0
    ? Object.entries(components)
    : [
        ['db',      health?.status === 'ok' ? 'ok' : 'unknown'],
        ['kafka',   health?.status === 'ok' ? 'ok' : 'unknown'],
        ['redis',   health?.status === 'ok' ? 'ok' : 'unknown'],
        ['kis_api', health?.status === 'ok' ? 'ok' : 'unknown'],
      ] as [string, string][]

  return (
    <div className="space-y-5">
      <ModelStatusCard />

      <Card>
        <CardHeader className="flex items-center justify-between">
          <div>
            <CardTitle>시스템 상태</CardTitle>
            <div className="text-xs text-[var(--muted)] mt-0.5">30초마다 자동 갱신</div>
          </div>
          {health && (
            <div className={clsx('flex items-center gap-1.5 text-sm font-semibold', statusColor(health.status))}>
              <StatusIcon status={health.status} />
              {health.status.toUpperCase()}
            </div>
          )}
          {isLoading && <div className="h-5 skeleton rounded w-20" />}
          {error && <span className="text-xs text-red-400">연결 실패</span>}
        </CardHeader>
        <CardBody className="pt-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {serviceEntries.map(([name, status]) => (
              <div
                key={name}
                className={clsx(
                  'flex items-center gap-2.5 p-3.5 rounded-xl border',
                  status === 'ok' || status === 'connected'
                    ? 'border-green-500/25 bg-green-500/5'
                    : status === 'degraded'
                    ? 'border-yellow-500/25 bg-yellow-500/5'
                    : 'border-[var(--border)] bg-[var(--bg)]'
                )}
              >
                <StatusIcon status={status} />
                <div>
                  <div className="text-xs font-semibold text-[var(--fg)] capitalize">{name.replace(/_/g, ' ')}</div>
                  <div className={clsx('text-xs font-medium capitalize', statusColor(status))}>{status}</div>
                </div>
              </div>
            ))}
          </div>
          {health && (
            <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center gap-6 text-xs text-[var(--muted)]">
              {health.version && (
                <span className="flex items-center gap-1.5"><Server size={11} /> 버전 {health.version}</span>
              )}
              {health.uptime_seconds != null && (
                <span className="flex items-center gap-1.5"><Activity size={11} /> 업타임 {formatUptime(health.uptime_seconds)}</span>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Send size={15} className="text-cyan-400" />
            <CardTitle>텔레그램 알림 설정</CardTitle>
          </div>
          <div className="text-xs text-[var(--muted)] mt-0.5">매수 추천 신호 발송 조건 · 실시간 반영</div>
        </CardHeader>
        <CardBody className="pt-3"><TelegramSection /></CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>공시 알림 키워드</CardTitle>
          <div className="text-xs text-[var(--muted)] mt-0.5">해당 키워드 포함 공시 발생 시 텔레그램 알림 발송</div>
        </CardHeader>
        <CardBody className="pt-3"><KeywordsSection /></CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>시스템 파라미터</CardTitle>
          <div className="text-xs text-[var(--muted)] mt-0.5">.env 파일로 설정 · 변경 후 서비스 재시작 필요</div>
        </CardHeader>
        <CardBody className="pt-3 px-0 pb-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                  <th className="text-left py-2.5 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">파라미터</th>
                  <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">환경변수</th>
                  <th className="text-right py-2.5 pr-5 text-xs font-semibold uppercase tracking-wider">기본값</th>
                </tr>
              </thead>
              <tbody>
                {THRESHOLDS.map((t) => (
                  <tr key={t.key} className="border-b border-[var(--border)]/50">
                    <td className="py-2.5 pl-5 pr-3 text-[var(--fg)]">{t.label}</td>
                    <td className="py-2.5 pr-3">
                      <code className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-cyan-400 font-mono">{t.env}</code>
                    </td>
                    <td className="py-2.5 pr-5 text-right tabular text-[var(--muted)] font-medium">{t.default}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>마이크로서비스 포트</CardTitle></CardHeader>
        <CardBody>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { name: 'API Server',  port: '8000', desc: 'FastAPI REST + WebSocket' },
              { name: 'Collector',   port: '8001', desc: 'KIS REST + DART 수집' },
              { name: 'Detector',    port: '8002', desc: 'Kafka 소비 · 이벤트 탐지' },
              { name: 'Analyzer',    port: '8003', desc: '뉴스/공시 감성 분석' },
              { name: 'Recommender', port: '8004', desc: 'ML 기반 매매 추천' },
              { name: 'ML Service',  port: '8005', desc: 'LightGBM 학습/추론' },
            ].map((svc) => (
              <div key={svc.name} className="p-3 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-[var(--fg)]">{svc.name}</span>
                  <code className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-cyan-400 font-mono">:{svc.port}</code>
                </div>
                <div className="text-xs text-[var(--muted)]">{svc.desc}</div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────
export function Settings() {
  const [activeTab, setActiveTab] = useState<TabId>('system')

  return (
    <div className="flex flex-col h-full">
      {/* 탭 바 */}
      <div className="flex items-center gap-1 px-6 pt-4 pb-0 border-b border-[var(--border)] bg-[var(--bg)] flex-shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px',
              activeTab === tab.id
                ? 'text-cyan-400 border-cyan-400 bg-[var(--card)]'
                : 'text-[var(--muted)] border-transparent hover:text-[var(--fg)] hover:bg-[var(--border)]/30'
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'system'    && <div className="p-6"><SystemTab /></div>}
        {activeTab === 'model'     && <ModelPerformance />}
        {activeTab === 'tracking'  && <Tracking />}
        {activeTab === 'watchlist' && <Watchlist />}
        {activeTab === 'alerts'    && <NotificationHistory />}
      </div>
    </div>
  )
}
