// ── 특징주 이벤트 ──────────────────────────────────────────────────────────────
export interface FeatureEvent {
  id:              number
  detected_at:     string
  code:            string
  name:            string
  market:          string
  sector?:         string
  event_type:      string
  price?:          number
  change_rate?:    number
  volume?:         number
  volume_ratio?:   number
  amount?:         number
  signal_score?:   number
  risk_score?:     number
  result_1d?:      number
  result_3d?:      number
  result_5d?:      number
  all_event_types?: string[]
}

export interface TodaySummary {
  total:              number
  high_score:         number
  avg_score?:         number
  date:               string
  by_type:            Record<string, number>
}

// ── 매매 추천 ──────────────────────────────────────────────────────────────────
export interface Recommendation {
  id:                  number
  created_at:          string
  code:                string
  name:                string
  market:              string
  sector?:             string
  action:              'BUY' | 'WAIT' | 'SKIP'
  entry_price:         number
  entry_price_low?:    number
  entry_price_high?:   number
  target_price:        number
  stop_loss_price:     number
  expected_hold_days:  number
  success_prob:        number
  expected_return:     number
  risk_score:          number
  risk_reward_ratio:   number
  rationale:           RationaleDetail
  similar_cases:       SimilarCase[]
  actual_return?:      number
  is_success?:         boolean
}

export interface RationaleDetail {
  event_type?:       string
  ml_prob?:          number
  sim_prob?:         number
  sim_count?:        number
  sim_weight?:       number
  avg_sim_return?:   number
  stop_dist_pct?:    number
  target_dist_pct?:  number
  atr_based?:        boolean
  atr14?:            number
  risk_factors?:     string[]
}

export interface SimilarCase {
  code:        string
  date:        string
  similarity:  number
  return_5d?:  number
}

export interface PerformanceStats {
  total_count:    number
  buy_count:      number
  success_count:  number
  avg_return?:    number
  avg_pred_prob?: number
  success_rate:   number
}

// ── 공시 ───────────────────────────────────────────────────────────────────────
export interface Disclosure {
  id:               number
  rcept_no:         string
  code?:            string
  corp_name?:       string
  disclosed_at:     string
  title:            string
  category?:        'favorable' | 'unfavorable' | 'neutral'
  sentiment_score?: number
  amount?:          number
  keywords?:        string[]
  counterparty?:    string
  report_type?:     string
  disclosure_type?: string
  post_1h_change?:  number
  post_1d_change?:  number
}

// ── 종목 ───────────────────────────────────────────────────────────────────────
export interface Stock {
  code:              string
  name:              string
  market:            string
  sector?:           string
  industry?:         string
  is_active:         boolean
  is_trading_halt:   boolean
  shares_total?:     number
}

// ── 일봉/분봉 ──────────────────────────────────────────────────────────────────
export interface DailyBar {
  date:         string
  open:         number
  high:         number
  low:          number
  close:        number
  volume:       number
  amount:       number
  change_rate?: number
  ma5?:         number
  ma20?:        number
  ma60?:        number
  rsi14?:       number
  foreign_net_buy?: number
  inst_net_buy?:    number
}

// ── 테마 ───────────────────────────────────────────────────────────────────────
export interface Theme {
  cluster_id:  number
  keywords:    string[]
  news_count:  number
  stock_codes: string[]
  trend:       'rising' | 'falling' | 'stable'
  count_3d:    number
  count_7d:    number
}

// ── 시장 ───────────────────────────────────────────────────────────────────────
export interface MarketIndex {
  code:        string
  name:        string
  close:       number
  change:      number
  change_rate: number
  volume?:     number
  date:        string
}

// ── 백테스트 ──────────────────────────────────────────────────────────────────
export interface BacktestResult {
  error?: string
  params?: {
    event_type: string
    start:      string
    end:        string
    min_score:  number
  }
  result?: {
    total:          number
    win:            number
    loss:           number
    win_rate:       string
    avg_return:     string
    avg_win:        string
    avg_loss:       string
    profit_factor:  number
    max_drawdown:   string
    sharpe:         number
  }
  sample_trades?: Array<{
    code:   string
    entry:  string
    exit:   string
    pnl:    number
    status: string
  }>
}

export interface BacktestEventStats {
  count:      number
  win_rate:   number
  avg_return: number
}

// ── 유틸 타입 ─────────────────────────────────────────────────────────────────
export type Theme_Mode = 'dark' | 'light'

export interface ApiError {
  detail: string
  status: number
}
