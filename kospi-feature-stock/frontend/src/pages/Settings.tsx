import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  CheckCircle, XCircle, AlertCircle, Server, Activity, Send,
  Plus, Trash2, ToggleLeft, ToggleRight, Brain,
  ExternalLink, RotateCcw, Bell,
} from 'lucide-react'
import { systemApi } from '@/api/market'
import { settingsApi } from '@/api/settings'
import type { TelegramConfig, ModelStatus } from '@/api/settings'

import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card'
import { probToScore, scoreToProb, scoreBarColor } from '@/lib/utils'

// ── 탐지 임계값 파라미터 목록 ─────────────────────────────────────────────────
const THRESHOLDS = [
  { label: 'VOLUME_SURGE 배수',        env: 'VOLUME_SURGE_RATIO',  default: '3.0',  desc: '현재 거래량이 평균 대비 N배 이상일 때 탐지' },
  { label: 'AMOUNT_SURGE 배수',        env: 'AMOUNT_SURGE_RATIO',  default: '3.0',  desc: '거래대금 급증 기준 배수' },
  { label: '고점 돌파 최소 등락률 (%)', env: 'BREAKOUT_MIN_CHANGE', default: '1.0',  desc: '52주 고점 돌파 인정 최소 변동폭' },
  { label: '장대양봉 최소 몸통 (%)',    env: 'CANDLE_BODY_MIN_PCT', default: '5.0',  desc: '캔들 몸통 비율 최소 기준' },
  { label: 'VI 발동 임계값 (%)',        env: 'VI_THRESHOLD_PCT',    default: '10.0', desc: '변동성 완화장치 발동 기준 등락률' },
  { label: 'ML 매수 최소 확률',        env: 'ML_BUY_THRESHOLD',    default: '0.55', desc: 'LightGBM BUY 확률 최소 임계값' },
  { label: 'ATR 손절 배수',           env: 'ATR_STOP_MULT',       default: '1.5',  desc: 'ATR 기반 손절가 거리 배수' },
  { label: 'ATR 목표 배수',           env: 'ATR_TARGET_MULT',     default: '3.0',  desc: 'ATR 기반 목표가 거리 배수' },
  { label: '유사 사례 Top-K',         env: 'SIMILAR_TOP_K',       default: '10',   desc: 'pgvector 유사 사례 검색 상위 K' },
  { label: 'K-Means 테마 클러스터 수', env: 'N_CLUSTERS',          default: '30',   desc: '뉴스 K-Means 군집 수' },
]

// ── 마이크로서비스 포트 ───────────────────────────────────────────────────────
const SERVICES = [
  { name: 'API Server',  port: '8000', desc: 'FastAPI REST + WebSocket' },
  { name: 'Collector',   port: '8001', desc: 'KIS REST + DART 수집' },
  { name: 'Detector',    port: '8002', desc: 'Kafka 소비 · 이벤트 탐지' },
  { name: 'Analyzer',    port: '8003', desc: '뉴스/공시 감성 분석' },
  { name: 'Recommender', port: '8004', desc: 'ML 기반 매매 추천' },
  { name: 'ML Service',  port: '8005', desc: 'LightGBM 학습/추론' },
]

// ── 상태 아이콘 헬퍼 ─────────────────────────────────────────────────────────
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

interface HealthResponse {
  status: string
  components?: Record<string, string>
  version?: string
  uptime_seconds?: number
}

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
                {ms.metrics?.recall != null && (
                  <span className="text-[var(--muted)]"> / {ms.metrics.recall.toFixed(3)}</span>
                )}
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

// ── 시스템 상태 카드 ─────────────────────────────────────────────────────────
function SystemHealthCard() {
  const { data: health, isLoading, error } = useQuery<HealthResponse>({
    queryKey:        ['health'],
    queryFn:         systemApi.health,
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
  )
}

// 텔레그램 최소 확률 슬라이더 전용 변환 — 실제 ML 출력 범위 37.3%~62.7%
const TG_MIN = 0.373
const TG_MAX = 0.627
const TG_RANGE = TG_MAX - TG_MIN
function tgProbToScore(p: number): number {
  return Math.min(100, Math.max(1, Math.round(((Math.min(p, TG_MAX) - TG_MIN) / TG_RANGE) * 99 + 1)))
}
function tgScoreToProb(s: number): number {
  return parseFloat((TG_MIN + ((s - 1) / 99) * TG_RANGE).toFixed(3))
}

// ── 텔레그램 설정 ────────────────────────────────────────────────────────────
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

  const score     = tgProbToScore(draft.min_prob)
  const barCls    = scoreBarColor(probToScore(draft.min_prob))
  const textColor = barCls.replace('bg-', 'text-')

  return (
    <div className="space-y-5">
      {/* 활성화 토글 */}
      <div className="flex items-center justify-between p-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
        <div>
          <div className="text-sm font-semibold text-[var(--fg)]">텔레그램 알림</div>
          <div className="text-xs text-[var(--muted)] mt-0.5">매수 신호 및 공시 알림 발송 활성화</div>
        </div>
        <button
          onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
          className="text-[var(--muted)] hover:text-cyan-400 transition-colors"
        >
          {draft.enabled
            ? <ToggleRight size={28} className="text-cyan-400" />
            : <ToggleLeft size={28} />
          }
        </button>
      </div>

      {/* 최소 성공 점수 슬라이더 (1~100점) */}
      <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg)]">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-semibold text-[var(--fg)]">매수 신호 최소 성공 점수</div>
            <div className="text-xs text-[var(--muted)] mt-0.5">이 점수 이상인 신호만 텔레그램 발송</div>
          </div>
          <div className="text-right">
            <code className={clsx('text-2xl font-extrabold tabular', textColor)}>{score}점</code>
            <div className="text-[10px] text-[var(--muted)] tabular mt-0.5">
              ML확률 {(draft.min_prob * 100).toFixed(1)}%
            </div>
          </div>
        </div>
        <input
          type="range" min={1} max={100} step={1}
          value={score}
          onChange={(e) => {
            const s = Number(e.target.value)
            setDraft({ ...draft, min_prob: tgScoreToProb(s) })
          }}
          className="w-full accent-cyan-400"
        />
        <div className="flex justify-between text-[10px] text-[var(--muted)] mt-1">
          <span>1점 <span className="opacity-60">(37.3%)</span></span>
          <span className="text-yellow-400">25점</span>
          <span className="text-orange-400">50점</span>
          <span className="text-green-400">75점</span>
          <span>100점 <span className="opacity-60">(62.7%)</span></span>
        </div>
      </div>

      {/* 최대 리스크 / 최소 R:R */}
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

// ── 공시 알림 키워드 ─────────────────────────────────────────────────────────
function KeywordsSection() {
  const qc = useQueryClient()
  const [newKw, setNewKw] = useState('')

  const { data: cfg } = useQuery<TelegramConfig>({
    queryKey: ['settings', 'telegram'],
    queryFn:  settingsApi.getTelegram,
  })

  const addKwMut = useMutation({
    mutationFn: (kw: string) => settingsApi.addKeyword(kw),
    onSuccess: (d: TelegramConfig) => {
      qc.setQueryData<TelegramConfig>(['settings', 'telegram'], d)
      setNewKw('')
    },
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
            <button
              onClick={() => delKwMut.mutate(kw)}
              className="text-[var(--muted)] hover:text-red-400 transition-colors"
            >
              <Trash2 size={11} />
            </button>
          </div>
        ))}
        {keywords.length === 0 && (
          <div className="text-xs text-[var(--muted)]">등록된 키워드가 없습니다.</div>
        )}
      </div>
    </div>
  )
}

// ── 탐지 임계값 안내 카드 ────────────────────────────────────────────────────
function ThresholdGuideCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>탐지 임계값 파라미터</CardTitle>
        <div className="text-xs text-[var(--muted)] mt-0.5">
          .env 파일에서 환경변수로 설정 · 변경 후 서비스 재시작 필요
        </div>
      </CardHeader>
      <CardBody className="pt-3 px-0 pb-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] bg-[var(--bg)]/40">
                <th className="text-left py-2.5 pl-5 pr-3 text-xs font-semibold uppercase tracking-wider">파라미터</th>
                <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider">환경변수</th>
                <th className="text-left py-2.5 pr-3 text-xs font-semibold uppercase tracking-wider hidden md:table-cell">설명</th>
                <th className="text-right py-2.5 pr-5 text-xs font-semibold uppercase tracking-wider">기본값</th>
              </tr>
            </thead>
            <tbody>
              {THRESHOLDS.map((t) => (
                <tr key={t.env} className="border-b border-[var(--border)]/50 hover:bg-[var(--border)]/20 transition-colors">
                  <td className="py-2.5 pl-5 pr-3 text-[var(--fg)] text-sm">{t.label}</td>
                  <td className="py-2.5 pr-3">
                    <code className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)] text-cyan-400 font-mono">{t.env}</code>
                  </td>
                  <td className="py-2.5 pr-3 text-xs text-[var(--muted)] hidden md:table-cell">{t.desc}</td>
                  <td className="py-2.5 pr-5 text-right tabular text-[var(--muted)] font-medium text-sm">{t.default}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-5 py-3 border-t border-[var(--border)] bg-amber-500/5">
          <p className="text-xs text-amber-400/80 flex items-start gap-1.5">
            <AlertCircle size={12} className="mt-0.5 flex-shrink-0" />
            실제 값 변경은 서버의 <code className="font-mono bg-[var(--border)] px-1 rounded">.env</code> 파일을 직접 수정하고 해당 서비스를 재시작해야 합니다.
          </p>
        </div>
      </CardBody>
    </Card>
  )
}

// ── 시스템 초기화 + 빠른 링크 카드 ──────────────────────────────────────────
function QuickLinksCard() {
  const nav = useNavigate()
  const links = [
    {
      icon: <RotateCcw size={16} className="text-orange-400" />,
      title: '시스템 Bootstrap',
      desc: 'DB 초기화 · 종목 마스터 로드 · 서비스 재기동 안내',
      href: null,
      badge: 'infra',
      badgeColor: 'text-orange-400 bg-orange-500/10 border-orange-500/25',
      onClick: () => window.open(`${import.meta.env.VITE_API_BASE_URL ?? ''}/docs`, '_blank'),
    },
    {
      icon: <Bell size={16} className="text-purple-400" />,
      title: '알림 이력',
      desc: '텔레그램 발송 성공/실패 이력 전체 조회',
      href: '/notifications',
      badge: 'log',
      badgeColor: 'text-purple-400 bg-purple-500/10 border-purple-500/25',
      onClick: () => nav('/notifications'),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>빠른 이동</CardTitle>
      </CardHeader>
      <CardBody className="pt-3 space-y-3">
        {links.map((link) => (
          <button
            key={link.title}
            onClick={link.onClick}
            className="w-full flex items-center gap-3 p-4 rounded-xl border border-[var(--border)] hover:bg-[var(--border)]/30 transition-colors text-left group"
          >
            <div className="w-9 h-9 rounded-lg border border-[var(--border)] bg-[var(--bg)] flex items-center justify-center flex-shrink-0">
              {link.icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-[var(--fg)] group-hover:text-white transition-colors">{link.title}</div>
              <div className="text-xs text-[var(--muted)] mt-0.5 truncate">{link.desc}</div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border font-medium', link.badgeColor)}>
                {link.badge}
              </span>
              <ExternalLink size={13} className="text-[var(--muted)] group-hover:text-[var(--fg)] transition-colors" />
            </div>
          </button>
        ))}
      </CardBody>
    </Card>
  )
}

// ── 마이크로서비스 포트 카드 ─────────────────────────────────────────────────
function ServicePortsCard() {
  return (
    <Card>
      <CardHeader><CardTitle>마이크로서비스 포트</CardTitle></CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {SERVICES.map((svc) => (
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
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────
export function Settings() {
  return (
    <div className="p-6 space-y-5 max-w-5xl">

      {/* 섹션 1: 시스템 상태 */}
      <ModelStatusCard />
      <SystemHealthCard />

      {/* 섹션 2: API 연결 상태 — 텔레그램 설정 */}
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

      {/* 섹션 3: 탐지 임계값 (읽기 전용 안내) */}
      <ThresholdGuideCard />

      {/* 섹션 4: 빠른 이동 */}
      <QuickLinksCard />

      {/* 섹션 5: 마이크로서비스 포트 */}
      <ServicePortsCard />

    </div>
  )
}
