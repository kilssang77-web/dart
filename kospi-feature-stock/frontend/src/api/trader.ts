import { http } from './client'

// ── 타입 정의 ────────────────────────────────────────────────────────────────

export interface TraderSettings {
  is_active: boolean
  mode: 'paper' | 'live'
  sizing_method: 'kelly' | 'fixed_fraction' | 'fixed_ratio'
  max_invest_per_trade: number
  max_total_invest: number
  max_positions: number
  daily_loss_limit: number
  min_prob: number
  kelly_fraction: number
  fixed_fraction_pct: number
  auto_sell: boolean
  allow_manual_order: boolean
}

export interface HoldingItem {
  code: string
  name: string
  qty: number
  avg_price: number
  current_price: number
  eval_amount: number
  pnl_pct: number
  pnl_amount: number
}

export interface BalanceInfo {
  success: boolean
  deposit: number
  total_eval: number
  total_buy: number
  holdings: HoldingItem[]
  error_msg?: string
}

export interface Position {
  id: number
  code: string
  name?: string
  qty: number
  avg_price: number
  current_price?: number
  target_price?: number
  stop_loss_price?: number
  unrealized_pct?: number
  unrealized_amount?: number
  invest_amount: number
  entry_date: string
  mode: string
  rec_id?: number
  status?: string
  close_reason?: string
  closed_at?: string
  closed_price?: number
  pnl_pct?: number
  pnl_amount?: number
  created_at?: string
}

export interface Order {
  id: number
  order_no?: string
  rec_id?: number
  code: string
  name?: string
  side: 'BUY' | 'SELL'
  order_type: string
  order_price: number
  order_qty: number
  filled_qty: number
  avg_filled_price?: number
  status: string
  mode: string
  error_msg?: string
  created_at: string
  rec_action?: string
  rec_prob?: number
}

export interface DailyPnl {
  trade_date: string
  mode: string
  realized_pnl: number
  unrealized_pnl: number
  total_trades: number
  win_trades: number
  loss_trades: number
  buy_amount: number
  sell_amount: number
  is_limit_hit: boolean
  win_rate?: number
}

export interface TraderSummary {
  active_positions: number
  today?: DailyPnl
  all_time?: { cnt: number; avg_pnl: number; wins: number }
}

export interface ManualOrderRequest {
  code: string
  side: 'BUY' | 'SELL'
  qty: number
  price?: number
  order_type?: 'MARKET' | 'LIMIT'
  rec_id?: number
}

// ── API 클라이언트 ────────────────────────────────────────────────────────────

export const traderApi = {
  // 설정
  getSettings: () =>
    http.get<TraderSettings>('/trader/settings').then(r => r.data),

  updateSettings: (data: Partial<TraderSettings>) =>
    http.put<TraderSettings>('/trader/settings', data).then(r => r.data),

  // 잔고
  getBalance: () =>
    http.get<BalanceInfo>('/trader/balance').then(r => r.data),

  // 포지션
  getPositions: (status = 'HOLDING') =>
    http.get<Position[]>('/trader/positions', { params: { status } }).then(r => r.data),

  sellPosition: (positionId: number) =>
    http.post<{ success: boolean; pnl_pct: number; pnl_amount: number }>(
      `/trader/positions/${positionId}/sell`
    ).then(r => r.data),

  // 주문
  getOrders: (params?: { status?: string; limit?: number }) =>
    http.get<Order[]>('/trader/orders', { params }).then(r => r.data),

  placeOrder: (data: ManualOrderRequest) =>
    http.post<Order>('/trader/orders', data).then(r => r.data),

  cancelOrder: (orderId: number) =>
    http.delete<{ success: boolean }>(`/trader/orders/${orderId}`).then(r => r.data),

  // 일일 손익
  getDailyPnl: (days = 30) =>
    http.get<DailyPnl[]>('/trader/daily-pnl', { params: { days } }).then(r => r.data),

  // 요약
  getSummary: () =>
    http.get<TraderSummary>('/trader/summary').then(r => r.data),

  // 손실 가드
  resetLossGuard: () =>
    http.post('/trader/loss-guard/reset').then(r => r.data),

  // 자동 실행 로그
  getExecutionLog: (limit = 50) =>
    http.get<Order[]>('/trader/execution-log', { params: { limit } }).then(r => r.data),

  // 헬스
  health: () =>
    http.get<{ trader_service: string }>('/trader/health').then(r => r.data),
}
