import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, Wallet, Settings, ShoppingCart,
  XCircle, Play, Pause, AlertTriangle, CheckCircle2, Clock,
  Target, ShieldOff, BarChart3, RefreshCw, ArrowUpRight, ArrowDownLeft,
  Activity, Zap, DollarSign, PieChart,
} from 'lucide-react'
import { clsx } from 'clsx'
import { traderApi, TraderSettings, ManualOrderRequest } from '@/api/trader'
import { fmt, pctColor } from '@/lib/utils'

// ── 공통 유틸 ────────────────────────────────────────────────────────────────
function pct(v?: number | null) {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}
function krw(v?: number | null) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : v > 0 ? '+' : ''
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(1)}억`
  if (abs >= 10_000) return `${sign}${(abs / 10_000).toFixed(0)}만`
  return `${sign}${abs.toLocaleString()}원`
}
function statusBadge(status: string) {
  const map: Record<string, string> = {
    FILLED:    'bg-green-500/10 text-green-400',
    PENDING:   'bg-yellow-500/10 text-yellow-400',
    PARTIAL:   'bg-cyan-500/10 text-cyan-400',
    CANCELLED: 'bg-gray-500/10 text-gray-400',
    FAILED:    'bg-red-500/10 text-red-400',
    REJECTED:  'bg-red-500/10 text-red-400',
  }
  return map[status] ?? 'bg-gray-500/10 text-gray-400'
}

// ── 요약 카드 ────────────────────────────────────────────────────────────────
function SummaryCard({
  icon: Icon, label, value, sub, positive, color,
}: {
  icon: any; label: string; value: string; sub?: string
  positive?: boolean; color?: string
}) {
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
      <div className="flex items-center gap-2 text-xs text-[var(--muted)] mb-1">
        <Icon size={12} />
        {label}
      </div>
      <div className={clsx(
        'text-lg font-bold',
        color ?? (positive === true ? 'text-green-400' : positive === false ? 'text-red-400' : 'text-[var(--fg)]')
      )}>
        {value}
      </div>
      {sub && <div className="text-xs text-[var(--muted)] mt-0.5">{sub}</div>}
    </div>
  )
}

// ── 트레이더 설정 패널 ────────────────────────────────────────────────────────
function SettingsPanel({ settings, onClose }: { settings: TraderSettings; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<Partial<TraderSettings>>(settings)
  const mut = useMutation({
    mutationFn: (data: Partial<TraderSettings>) => traderApi.updateSettings(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trader-settings'] })
      onClose()
    },
  })

  const f = (key: keyof TraderSettings, val: unknown) =>
    setForm(p => ({ ...p, [key]: val }))

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-2xl w-full max-w-xl p-6 space-y-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-base flex items-center gap-2">
            <Settings size={16} className="text-cyan-400" /> 트레이더 설정
          </h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--fg)]">✕</button>
        </div>

        {/* 모드 & 활성화 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">운영 모드</label>
            <select
              value={form.mode}
              onChange={e => f('mode', e.target.value)}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            >
              <option value="paper">모의투자 (Paper)</option>
              <option value="live">실전투자 (Live)</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">자동매매 활성</label>
            <button
              onClick={() => f('is_active', !form.is_active)}
              className={clsx(
                'w-full flex items-center justify-center gap-2 py-2 rounded-lg border text-sm font-medium transition-colors',
                form.is_active
                  ? 'border-green-500/40 bg-green-500/10 text-green-400'
                  : 'border-[var(--border)] text-[var(--muted)]'
              )}
            >
              {form.is_active ? <><Play size={12} /> 활성</>  : <><Pause size={12} /> 비활성</>}
            </button>
          </div>
        </div>

        {/* 포지션 사이징 */}
        <div className="space-y-1">
          <label className="text-xs text-[var(--muted)]">포지션 사이징 방법</label>
          <div className="grid grid-cols-3 gap-2">
            {(['fixed_fraction', 'kelly', 'fixed_ratio'] as const).map(m => (
              <button
                key={m}
                onClick={() => f('sizing_method', m)}
                className={clsx(
                  'py-2 rounded-lg border text-xs font-medium transition-colors',
                  form.sizing_method === m
                    ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-400'
                    : 'border-[var(--border)] text-[var(--muted)] hover:border-cyan-500/20'
                )}
              >
                {m === 'fixed_fraction' ? '고정비율(%)' : m === 'kelly' ? 'Kelly' : '고정금액'}
              </button>
            ))}
          </div>
        </div>

        {/* 금액 파라미터 */}
        <div className="grid grid-cols-2 gap-4">
          {[
            { key: 'max_invest_per_trade', label: '종목당 최대 투자금 (원)' },
            { key: 'max_total_invest',     label: '총 최대 투자금 (원)' },
            { key: 'daily_loss_limit',     label: '일일 손실 한도 (원)' },
          ].map(({ key, label }) => (
            <div key={key} className="space-y-1">
              <label className="text-xs text-[var(--muted)]">{label}</label>
              <input
                type="number"
                value={(form as any)[key] ?? ''}
                onChange={e => f(key as keyof TraderSettings, Number(e.target.value))}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              />
            </div>
          ))}
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">최대 동시 보유 종목</label>
            <input
              type="number"
              min={1} max={20}
              value={form.max_positions ?? ''}
              onChange={e => f('max_positions', Number(e.target.value))}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        {/* ML 확률 파라미터 */}
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">최소 성공 확률</label>
            <input
              type="number" step="0.01" min="0.1" max="0.95"
              value={form.min_prob ?? ''}
              onChange={e => f('min_prob', Number(e.target.value))}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            />
          </div>
          {form.sizing_method === 'kelly' && (
            <div className="space-y-1">
              <label className="text-xs text-[var(--muted)]">Kelly 비율 (0.25=Quarter)</label>
              <input
                type="number" step="0.05" min="0.05" max="1"
                value={form.kelly_fraction ?? ''}
                onChange={e => f('kelly_fraction', Number(e.target.value))}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              />
            </div>
          )}
          {form.sizing_method === 'fixed_fraction' && (
            <div className="space-y-1">
              <label className="text-xs text-[var(--muted)]">자본 대비 비율 (%)</label>
              <input
                type="number" step="1" min="1" max="50"
                value={form.fixed_fraction_pct ?? ''}
                onChange={e => f('fixed_fraction_pct', Number(e.target.value))}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              />
            </div>
          )}
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">자동 매도</label>
            <button
              onClick={() => f('auto_sell', !form.auto_sell)}
              className={clsx(
                'w-full py-2 rounded-lg border text-sm font-medium transition-colors',
                form.auto_sell
                  ? 'border-green-500/40 bg-green-500/10 text-green-400'
                  : 'border-[var(--border)] text-[var(--muted)]'
              )}
            >
              {form.auto_sell ? '✓ 활성' : '비활성'}
            </button>
          </div>
        </div>

        {form.mode === 'live' && (
          <div className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs text-amber-400 flex items-start gap-2">
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            실전 모드에서는 실제 KIS 계좌로 주문이 체결됩니다. 충분한 Paper 검증 후 전환하세요.
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-[var(--border)] text-sm text-[var(--muted)] hover:border-cyan-500/20">
            취소
          </button>
          <button
            onClick={() => mut.mutate(form)}
            disabled={mut.isPending}
            className="flex-1 py-2 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 text-sm font-medium hover:bg-cyan-500/25 disabled:opacity-40 transition-colors"
          >
            {mut.isPending ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 수동 주문 모달 ────────────────────────────────────────────────────────────
function ManualOrderModal({ onClose, recId, recCode }: { onClose: () => void; recId?: number; recCode?: string }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<ManualOrderRequest>({
    code: recCode ?? '',
    side: 'BUY',
    qty: 1,
    price: 0,
    order_type: 'MARKET',
    rec_id: recId,
  })
  const [result, setResult] = useState<{ success: boolean; msg: string } | null>(null)

  const mut = useMutation({
    mutationFn: traderApi.placeOrder,
    onSuccess: (data) => {
      setResult({ success: true, msg: `주문 완료 — ${data.order_no ?? data.id}` })
      qc.invalidateQueries({ queryKey: ['trader-orders'] })
      qc.invalidateQueries({ queryKey: ['trader-positions'] })
      qc.invalidateQueries({ queryKey: ['trader-balance'] })
    },
    onError: (e: any) => {
      setResult({ success: false, msg: e?.response?.data?.detail ?? '주문 실패' })
    },
  })

  const f = (k: keyof ManualOrderRequest, v: unknown) => setForm(p => ({ ...p, [k]: v }))

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-2xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-base flex items-center gap-2">
            <ShoppingCart size={16} className="text-cyan-400" /> 수동 주문
          </h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--fg)]">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">종목 코드</label>
            <input value={form.code} onChange={e => f('code', e.target.value.toUpperCase())}
              placeholder="005930" maxLength={10}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">매수/매도</label>
            <div className="grid grid-cols-2 gap-1">
              {(['BUY', 'SELL'] as const).map(s => (
                <button key={s} onClick={() => f('side', s)}
                  className={clsx(
                    'py-2 rounded-lg border text-sm font-medium transition-colors',
                    form.side === s
                      ? s === 'BUY'
                        ? 'border-green-500/40 bg-green-500/10 text-green-400'
                        : 'border-red-500/40 bg-red-500/10 text-red-400'
                      : 'border-[var(--border)] text-[var(--muted)]'
                  )}
                >{s === 'BUY' ? '매수' : '매도'}</button>
              ))}
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">수량 (주)</label>
            <input type="number" min={1} value={form.qty} onChange={e => f('qty', Number(e.target.value))}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-[var(--muted)]">주문 유형</label>
            <select value={form.order_type} onChange={e => f('order_type', e.target.value)}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            >
              <option value="MARKET">시장가</option>
              <option value="LIMIT">지정가</option>
            </select>
          </div>
          {form.order_type === 'LIMIT' && (
            <div className="col-span-2 space-y-1">
              <label className="text-xs text-[var(--muted)]">지정가 (원)</label>
              <input type="number" min={0} value={form.price} onChange={e => f('price', Number(e.target.value))}
                className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              />
            </div>
          )}
        </div>

        {result && (
          <div className={clsx(
            'p-3 rounded-xl text-xs flex items-center gap-2',
            result.success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
          )}>
            {result.success ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
            {result.msg}
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-[var(--border)] text-sm text-[var(--muted)]">취소</button>
          <button
            onClick={() => mut.mutate(form)}
            disabled={mut.isPending || !form.code || form.qty < 1}
            className={clsx(
              'flex-1 py-2 rounded-lg border text-sm font-medium transition-colors disabled:opacity-40',
              form.side === 'BUY'
                ? 'border-green-500/30 bg-green-500/10 text-green-400 hover:bg-green-500/20'
                : 'border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20'
            )}
          >
            {mut.isPending ? '처리 중...' : form.side === 'BUY' ? '매수 주문' : '매도 주문'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export function TraderPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<'positions' | 'orders' | 'pnl' | 'log'>('positions')
  const [showSettings, setShowSettings] = useState(false)
  const [showManualOrder, setShowManualOrder] = useState(false)
  const [sellConfirm, setSellConfirm] = useState<number | null>(null)

  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['trader-settings'],
    queryFn: traderApi.getSettings,
    refetchInterval: 30_000,
  })
  const { data: balance, isLoading: balanceLoading } = useQuery({
    queryKey: ['trader-balance'],
    queryFn: traderApi.getBalance,
    refetchInterval: 60_000,
  })
  const { data: positions = [], isLoading: posLoading } = useQuery({
    queryKey: ['trader-positions'],
    queryFn: () => traderApi.getPositions('HOLDING'),
    refetchInterval: 30_000,
  })
  const { data: closedPositions = [] } = useQuery({
    queryKey: ['trader-positions-closed'],
    queryFn: () => traderApi.getPositions('CLOSED'),
    refetchInterval: 60_000,
  })
  const { data: orders = [], isLoading: ordersLoading } = useQuery({
    queryKey: ['trader-orders'],
    queryFn: () => traderApi.getOrders({ limit: 100 }),
    refetchInterval: 30_000,
    enabled: tab === 'orders',
  })
  const { data: pnlData = [], isLoading: pnlLoading } = useQuery({
    queryKey: ['trader-daily-pnl'],
    queryFn: () => traderApi.getDailyPnl(30),
    refetchInterval: 300_000,
    enabled: tab === 'pnl',
  })
  const { data: execLog = [] } = useQuery({
    queryKey: ['trader-exec-log'],
    queryFn: () => traderApi.getExecutionLog(50),
    refetchInterval: 60_000,
    enabled: tab === 'log',
  })
  const { data: summary } = useQuery({
    queryKey: ['trader-summary'],
    queryFn: traderApi.getSummary,
    refetchInterval: 60_000,
  })

  const sellMut = useMutation({
    mutationFn: traderApi.sellPosition,
    onSuccess: () => {
      setSellConfirm(null)
      qc.invalidateQueries({ queryKey: ['trader-positions'] })
      qc.invalidateQueries({ queryKey: ['trader-balance'] })
    },
  })

  const toggleActiveMut = useMutation({
    mutationFn: (active: boolean) => traderApi.updateSettings({ is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trader-settings'] }),
  })

  const isActive = settings?.is_active ?? false
  const mode     = settings?.mode ?? 'paper'
  const todayPnl = summary?.today

  return (
    <div className="p-5 space-y-5 max-w-[1400px]">

      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold flex items-center gap-2">
            <Activity size={18} className="text-cyan-400" />
            자동 매매 트레이더
          </h1>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-[var(--muted)]">
            <span className={clsx(
              'px-2 py-0.5 rounded-full border font-medium',
              mode === 'live'
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
                : 'border-cyan-500/40 bg-cyan-500/10 text-cyan-400'
            )}>
              {mode === 'live' ? '실전' : '모의'}
            </span>
            <span className={clsx(
              'px-2 py-0.5 rounded-full border font-medium',
              isActive ? 'border-green-500/40 bg-green-500/10 text-green-400' : 'border-[var(--border)] text-[var(--muted)]'
            )}>
              {isActive ? '자동매매 ON' : '자동매매 OFF'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowManualOrder(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-[var(--card)] border border-[var(--border)] hover:border-cyan-500/30 text-[var(--fg)] transition-colors"
          >
            <ShoppingCart size={13} /> 수동 주문
          </button>
          <button
            onClick={() => toggleActiveMut.mutate(!isActive)}
            disabled={toggleActiveMut.isPending}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border transition-colors disabled:opacity-40',
              isActive
                ? 'border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20'
                : 'border-green-500/30 bg-green-500/10 text-green-400 hover:bg-green-500/20'
            )}
          >
            {isActive ? <><Pause size={13} /> 중지</> : <><Play size={13} /> 시작</>}
          </button>
          <button onClick={() => setShowSettings(true)} className="p-2 rounded-lg border border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)] hover:border-cyan-500/30 transition-colors">
            <Settings size={14} />
          </button>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <SummaryCard
          icon={Wallet} label="예수금 (가용)"
          value={balance?.deposit != null ? `${(balance.deposit / 10000).toFixed(0)}만원` : '—'}
          sub={`총평가 ${balance?.total_eval != null ? (balance.total_eval / 10_000).toFixed(0) + '만' : '—'}`}
        />
        <SummaryCard
          icon={PieChart} label="투입 자본"
          value={balance?.total_buy != null ? `${(balance.total_buy / 10000).toFixed(0)}만원` : '—'}
          sub={`${positions.length}종목 보유`}
        />
        <SummaryCard
          icon={TrendingUp} label="오늘 실현 손익"
          value={krw(todayPnl?.realized_pnl)}
          sub={todayPnl ? `${todayPnl.total_trades}건` : '거래 없음'}
          positive={todayPnl && todayPnl.realized_pnl > 0}
        />
        <SummaryCard
          icon={BarChart3} label="오늘 승률"
          value={todayPnl?.win_rate != null ? `${todayPnl.win_rate.toFixed(1)}%` : '—'}
          sub={todayPnl ? `승${todayPnl.win_trades}/패${todayPnl.loss_trades}` : ''}
          positive={todayPnl && (todayPnl.win_rate ?? 0) >= 50}
        />
        <SummaryCard
          icon={Target} label="전체 완료 포지션"
          value={summary?.all_time ? `${summary.all_time.cnt}건` : '—'}
          sub={summary?.all_time ? `평균 ${pct(summary.all_time.avg_pnl)}` : ''}
          positive={summary?.all_time && summary.all_time.avg_pnl > 0}
        />
        <SummaryCard
          icon={ShieldOff} label="손실 한도"
          value={settings ? `${(settings.daily_loss_limit / 10000).toFixed(0)}만` : '—'}
          sub={`잔여: ${todayPnl ? krw(settings!.daily_loss_limit - Math.abs(Math.min(0, todayPnl.realized_pnl))) : '—'}`}
          positive={!todayPnl?.is_limit_hit}
        />
      </div>

      {/* 손실 한도 경고 */}
      {todayPnl?.is_limit_hit && (
        <div className="flex items-center gap-3 p-3 bg-red-500/5 border border-red-500/20 rounded-xl text-sm text-red-400">
          <AlertTriangle size={16} />
          일일 손실 한도를 초과했습니다. 자동매매가 금일 중단되었습니다.
          <button
            onClick={() => traderApi.resetLossGuard().then(() => qc.invalidateQueries())}
            className="ml-auto text-xs px-2 py-1 rounded border border-red-500/30 hover:bg-red-500/10"
          >
            수동 리셋
          </button>
        </div>
      )}

      {/* 탭 */}
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="flex border-b border-[var(--border)]">
          {([
            ['positions', `보유 포지션 (${positions.length})`],
            ['orders',    '주문 내역'],
            ['pnl',       '일일 손익'],
            ['log',       '자동실행 로그'],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={clsx(
                'px-5 py-3 text-sm font-medium transition-colors border-b-2',
                tab === id
                  ? 'border-cyan-400 text-cyan-400'
                  : 'border-transparent text-[var(--muted)] hover:text-[var(--fg)]'
              )}
            >
              {label}
            </button>
          ))}
          <div className="flex-1" />
          <button
            onClick={() => qc.invalidateQueries({ queryKey: ['trader-positions'] })}
            className="px-4 text-[var(--muted)] hover:text-[var(--fg)]"
          >
            <RefreshCw size={13} />
          </button>
        </div>

        {/* 보유 포지션 탭 */}
        {tab === 'positions' && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
                  <th className="px-4 py-3 text-left">종목</th>
                  <th className="px-4 py-3 text-right">수량</th>
                  <th className="px-4 py-3 text-right">평균매수가</th>
                  <th className="px-4 py-3 text-right">현재가</th>
                  <th className="px-4 py-3 text-right">평가금액</th>
                  <th className="px-4 py-3 text-right">평가손익</th>
                  <th className="px-4 py-3 text-right">목표가</th>
                  <th className="px-4 py-3 text-right">손절가</th>
                  <th className="px-4 py-3 text-center">진입일</th>
                  <th className="px-4 py-3 text-center">모드</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {posLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i} className="border-b border-[var(--border)]">
                      {Array.from({ length: 11 }).map((_, j) => (
                        <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded w-16 ml-auto" /></td>
                      ))}
                    </tr>
                  ))
                ) : positions.length === 0 ? (
                  <tr><td colSpan={11} className="text-center py-12 text-[var(--muted)] text-sm">보유 포지션 없음</td></tr>
                ) : positions.map(pos => {
                  const pnlPct = pos.unrealized_pct
                  const pnlAmt = pos.unrealized_amount
                  return (
                    <tr key={pos.id} className="border-b border-[var(--border)] hover:bg-[var(--border)]/20 transition-colors">
                      <td className="px-4 py-3 cursor-pointer" onClick={() => nav(`/search?code=${pos.code}`)}>
                        <div className="font-semibold">{pos.code}</div>
                        <div className="text-xs text-[var(--muted)]">{pos.name}</div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono">{pos.qty.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-mono">{pos.avg_price.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right font-mono">{pos.current_price?.toLocaleString() ?? '—'}</td>
                      <td className="px-4 py-3 text-right font-mono">{pos.invest_amount.toLocaleString()}</td>
                      <td className={clsx('px-4 py-3 text-right font-bold', pctColor(pnlPct ?? 0))}>
                        <div>{pct(pnlPct)}</div>
                        <div className="text-xs">{pnlAmt != null ? krw(pnlAmt) : '—'}</div>
                      </td>
                      <td className="px-4 py-3 text-right text-green-400/70 font-mono text-xs">
                        {pos.target_price?.toLocaleString() ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-right text-red-400/70 font-mono text-xs">
                        {pos.stop_loss_price?.toLocaleString() ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-center text-xs text-[var(--muted)]">{pos.entry_date}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={clsx(
                          'text-xs px-2 py-0.5 rounded-full border',
                          pos.mode === 'live' ? 'border-amber-500/30 text-amber-400' : 'border-cyan-500/30 text-cyan-400'
                        )}>{pos.mode}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {sellConfirm === pos.id ? (
                          <div className="flex gap-1">
                            <button
                              onClick={() => sellMut.mutate(pos.id)}
                              disabled={sellMut.isPending}
                              className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20"
                            >
                              {sellMut.isPending ? '...' : '확인'}
                            </button>
                            <button onClick={() => setSellConfirm(null)} className="text-xs px-2 py-1 rounded border border-[var(--border)] text-[var(--muted)]">취소</button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setSellConfirm(pos.id)}
                            className="text-xs px-2 py-1 rounded border border-[var(--border)] text-[var(--muted)] hover:border-red-500/30 hover:text-red-400 transition-colors"
                          >
                            매도
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {/* 완료 포지션 */}
            {closedPositions.length > 0 && (
              <div className="border-t border-[var(--border)]">
                <div className="px-5 py-3 text-xs text-[var(--muted)] font-semibold uppercase tracking-wider">완료 포지션 (최근 {closedPositions.length}건)</div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-[var(--muted)]">
                      <th className="px-4 py-2 text-left">종목</th>
                      <th className="px-4 py-2 text-right">수량</th>
                      <th className="px-4 py-2 text-right">매수가</th>
                      <th className="px-4 py-2 text-right">매도가</th>
                      <th className="px-4 py-2 text-right">손익</th>
                      <th className="px-4 py-2 text-center">사유</th>
                      <th className="px-4 py-2 text-center">날짜</th>
                    </tr>
                  </thead>
                  <tbody>
                    {closedPositions.slice(0, 20).map(pos => (
                      <tr key={pos.id} className="border-t border-[var(--border)]/50 text-xs hover:bg-[var(--border)]/10">
                        <td className="px-4 py-2"><span className="font-semibold">{pos.code}</span> <span className="text-[var(--muted)]">{pos.name}</span></td>
                        <td className="px-4 py-2 text-right font-mono">{pos.qty}</td>
                        <td className="px-4 py-2 text-right font-mono">{pos.avg_price.toLocaleString()}</td>
                        <td className="px-4 py-2 text-right font-mono">{pos.closed_price?.toLocaleString() ?? '—'}</td>
                        <td className={clsx('px-4 py-2 text-right font-bold', pctColor(pos.pnl_pct ?? 0))}>
                          {pct(pos.pnl_pct)} / {krw(pos.pnl_amount)}
                        </td>
                        <td className="px-4 py-2 text-center text-[var(--muted)]">
                          {pos.close_reason === 'TARGET_HIT' ? <span className="text-green-400">목표도달</span>
                          : pos.close_reason === 'STOP_HIT'  ? <span className="text-red-400">손절</span>
                          : pos.close_reason === 'MANUAL'    ? '수동'
                          : pos.close_reason}
                        </td>
                        <td className="px-4 py-2 text-center text-[var(--muted)]">{pos.closed_at?.slice(0, 10)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* 주문 내역 탭 */}
        {tab === 'orders' && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
                  <th className="px-4 py-3 text-left">시각</th>
                  <th className="px-4 py-3 text-left">종목</th>
                  <th className="px-4 py-3 text-center">구분</th>
                  <th className="px-4 py-3 text-right">가격</th>
                  <th className="px-4 py-3 text-right">수량</th>
                  <th className="px-4 py-3 text-right">체결수량</th>
                  <th className="px-4 py-3 text-right">체결가</th>
                  <th className="px-4 py-3 text-center">상태</th>
                  <th className="px-4 py-3 text-center">모드</th>
                  <th className="px-4 py-3 text-left">주문번호</th>
                </tr>
              </thead>
              <tbody>
                {ordersLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b border-[var(--border)]">
                      {Array.from({ length: 10 }).map((_, j) => (
                        <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded w-16" /></td>
                      ))}
                    </tr>
                  ))
                ) : orders.length === 0 ? (
                  <tr><td colSpan={10} className="text-center py-12 text-[var(--muted)] text-sm">주문 내역 없음</td></tr>
                ) : orders.map(o => (
                  <tr key={o.id} className="border-b border-[var(--border)] hover:bg-[var(--border)]/20 text-xs">
                    <td className="px-4 py-3 text-[var(--muted)]">{o.created_at.slice(0, 16).replace('T', ' ')}</td>
                    <td className="px-4 py-3">
                      <div className="font-semibold">{o.code}</div>
                      <div className="text-[var(--muted)]">{o.name}</div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx(
                        'px-2 py-0.5 rounded-full border font-semibold',
                        o.side === 'BUY' ? 'border-green-500/30 text-green-400' : 'border-red-500/30 text-red-400'
                      )}>
                        {o.side === 'BUY' ? '매수' : '매도'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{o.order_price > 0 ? o.order_price.toLocaleString() : '시장가'}</td>
                    <td className="px-4 py-3 text-right font-mono">{o.order_qty.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono">{o.filled_qty.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono">{o.avg_filled_price?.toLocaleString() ?? '—'}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx('px-2 py-0.5 rounded-full border', statusBadge(o.status))}>{o.status}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx(
                        'text-xs px-1.5 py-0.5 rounded',
                        o.mode === 'live' ? 'text-amber-400' : 'text-cyan-400/70'
                      )}>{o.mode}</span>
                    </td>
                    <td className="px-4 py-3 text-[var(--muted)] font-mono">{o.order_no ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 일일 손익 탭 */}
        {tab === 'pnl' && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
                  <th className="px-4 py-3 text-left">날짜</th>
                  <th className="px-4 py-3 text-right">실현 손익</th>
                  <th className="px-4 py-3 text-right">매수금액</th>
                  <th className="px-4 py-3 text-right">매도금액</th>
                  <th className="px-4 py-3 text-center">거래수</th>
                  <th className="px-4 py-3 text-center">승/패</th>
                  <th className="px-4 py-3 text-right">승률</th>
                  <th className="px-4 py-3 text-center">한도초과</th>
                  <th className="px-4 py-3 text-center">모드</th>
                </tr>
              </thead>
              <tbody>
                {pnlLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b border-[var(--border)]">
                      {Array.from({ length: 9 }).map((_, j) => (
                        <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded w-14 mx-auto" /></td>
                      ))}
                    </tr>
                  ))
                ) : pnlData.length === 0 ? (
                  <tr><td colSpan={9} className="text-center py-12 text-[var(--muted)] text-sm">손익 데이터 없음</td></tr>
                ) : pnlData.map(d => (
                  <tr key={d.trade_date} className="border-b border-[var(--border)] hover:bg-[var(--border)]/20 text-xs">
                    <td className="px-4 py-3 font-semibold">{d.trade_date}</td>
                    <td className={clsx('px-4 py-3 text-right font-bold', d.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                      {krw(d.realized_pnl)}
                    </td>
                    <td className="px-4 py-3 text-right text-[var(--muted)]">{krw(d.buy_amount)}</td>
                    <td className="px-4 py-3 text-right text-[var(--muted)]">{krw(d.sell_amount)}</td>
                    <td className="px-4 py-3 text-center">{d.total_trades}</td>
                    <td className="px-4 py-3 text-center">
                      <span className="text-green-400">{d.win_trades}승</span> / <span className="text-red-400">{d.loss_trades}패</span>
                    </td>
                    <td className={clsx('px-4 py-3 text-right font-semibold', (d.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400')}>
                      {d.win_rate != null ? `${d.win_rate.toFixed(1)}%` : '—'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {d.is_limit_hit
                        ? <span className="text-red-400">⚠ 초과</span>
                        : <span className="text-[var(--muted)]">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={d.mode === 'live' ? 'text-amber-400' : 'text-cyan-400/70'}>{d.mode}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 자동실행 로그 탭 */}
        {tab === 'log' && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
                  <th className="px-4 py-3 text-left">시각</th>
                  <th className="px-4 py-3 text-left">종목</th>
                  <th className="px-4 py-3 text-center">구분</th>
                  <th className="px-4 py-3 text-right">가격</th>
                  <th className="px-4 py-3 text-right">수량</th>
                  <th className="px-4 py-3 text-right">ML 확률</th>
                  <th className="px-4 py-3 text-right">목표가</th>
                  <th className="px-4 py-3 text-right">손절가</th>
                  <th className="px-4 py-3 text-center">상태</th>
                </tr>
              </thead>
              <tbody>
                {execLog.length === 0 ? (
                  <tr><td colSpan={9} className="text-center py-12 text-[var(--muted)] text-sm">자동 실행 내역 없음</td></tr>
                ) : execLog.map(o => (
                  <tr key={o.id} className="border-b border-[var(--border)] hover:bg-[var(--border)]/20 text-xs">
                    <td className="px-4 py-3 text-[var(--muted)]">{o.created_at.slice(0, 16).replace('T', ' ')}</td>
                    <td className="px-4 py-3">
                      <div className="font-semibold cursor-pointer hover:text-cyan-400" onClick={() => nav(`/search?code=${o.code}`)}>{o.code}</div>
                      <div className="text-[var(--muted)]">{o.name}</div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx('px-2 py-0.5 rounded-full border text-xs',
                        o.side === 'BUY' ? 'border-green-500/30 text-green-400' : 'border-red-500/30 text-red-400'
                      )}>{o.side === 'BUY' ? '자동매수' : '자동매도'}</span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{o.avg_filled_price?.toLocaleString() ?? o.order_price.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono">{o.filled_qty || o.order_qty}</td>
                    <td className="px-4 py-3 text-right">
                      {o.rec_prob != null ? (
                        <span className={clsx('font-semibold', o.rec_prob >= 0.5 ? 'text-green-400' : 'text-[var(--muted)]')}>
                          {(o.rec_prob * 100).toFixed(1)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-green-400/70 font-mono">{(o as any).rec_target?.toLocaleString() ?? '—'}</td>
                    <td className="px-4 py-3 text-right text-red-400/70 font-mono">{(o as any).rec_stop?.toLocaleString() ?? '—'}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx('px-2 py-0.5 rounded-full border', statusBadge(o.status))}>{o.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 잔고 보유 종목 (KIS 실계좌 기준) */}
      {balance?.holdings && balance.holdings.length > 0 && (
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between">
            <h2 className="font-semibold flex items-center gap-2 text-sm">
              <Wallet size={14} className="text-cyan-400" />
              {mode === 'live' ? 'KIS 실계좌' : 'Paper'} 보유 종목
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400">{balance.holdings.length}종목</span>
            </h2>
            <div className="text-xs text-[var(--muted)]">
              총평가: {(balance.total_eval / 10_000).toFixed(0)}만 / 투입: {(balance.total_buy / 10_000).toFixed(0)}만
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-[var(--muted)]">
                  <th className="px-4 py-2 text-left">종목</th>
                  <th className="px-4 py-2 text-right">수량</th>
                  <th className="px-4 py-2 text-right">평균매수가</th>
                  <th className="px-4 py-2 text-right">현재가</th>
                  <th className="px-4 py-2 text-right">평가금액</th>
                  <th className="px-4 py-2 text-right">평가손익</th>
                </tr>
              </thead>
              <tbody>
                {balance.holdings.map(h => (
                  <tr key={h.code} className="border-t border-[var(--border)]/50 hover:bg-[var(--border)]/20 text-xs cursor-pointer" onClick={() => nav(`/search?code=${h.code}`)}>
                    <td className="px-4 py-2 font-semibold">{h.code} <span className="text-[var(--muted)]">{h.name}</span></td>
                    <td className="px-4 py-2 text-right font-mono">{h.qty.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-mono">{h.avg_price.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-mono">{h.current_price.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-mono">{h.eval_amount.toLocaleString()}</td>
                    <td className={clsx('px-4 py-2 text-right font-bold', pctColor(h.pnl_pct))}>
                      {pct(h.pnl_pct)} / {krw(h.pnl_amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showSettings && settings && (
        <SettingsPanel settings={settings} onClose={() => setShowSettings(false)} />
      )}
      {showManualOrder && (
        <ManualOrderModal onClose={() => setShowManualOrder(false)} />
      )}
    </div>
  )
}
