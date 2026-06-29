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
  fe_detected_at?:     string
  feature_event_id?:   number
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
  rec_count?:          number
  current_price?:      number
  current_change_rate?: number
  actual_return?:      number
  is_success?:         boolean
}

export interface RationaleDetail {
  event_type?:          string
  model_mode?:          'ml' | 'fallback'
  ml_prob?:             number
  sim_prob?:            number
  sim_count?:           number
  sim_weight?:          number
  avg_sim_return?:      number
  stop_dist_pct?:       number
  target_dist_pct?:     number
  atr_based?:           boolean
  atr14?:               number
  risk_factors?:        string[]
  confidence_grade?:    'A' | 'B' | 'C' | 'D'
  confidence_score?:    number
  confidence_warnings?: string[]
  rec_score?:           number
  gap_pct?:             number
  gap_filtered?:        boolean
  pullback_entry?:      number | null
  market_regime?:       { phase: string; kospi_price: number | null; ma20: number | null; pct_from_ma20: number | null } | null
  regime_note?:         string | null
  theme_boost?:         number
  active_themes?:       string[]
  theme_reversal?:      boolean
  theme_reversal_note?: string | null
  supply_score?:        number
}

export interface SimilarCase {
  code:        string
  name?:       string
  date:        string
  event_type?: string
  similarity:  number
  return_1d?:  number
  return_3d?:  number
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
  amount_text?:     string
  keywords?:        string[]
  counterparty?:    string
  contract_period?: string
  report_type?:     string
  disclosure_type?: string
  post_1h_change?:  number
  post_1d_change?:  number
  post_3d_change?:  number
  pre_close?:       number
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
  ma120?:       number
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
export interface BacktestTradeItem {
  code:         string
  name?:        string
  entry_date:   string
  exit_date:    string
  entry_price:  number
  exit_price:   number
  pnl_pct:      number
  status:       string   // win|loss|timeout
  signal_score: number
}

export interface BacktestEquityPoint {
  date:     string
  equity:   number
  drawdown: number
  pnl:      number
}

export interface BacktestSummary {
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
  sortino:        number
  calmar:         number
  win_streak:     number
  lose_streak:    number
}

export interface BacktestWindowResult {
  period:       string
  signals:      number
  result:       BacktestSummary | null
  equity_curve?: BacktestEquityPoint[]
}

export interface BacktestResult {
  error?: string
  params?: {
    event_type?:   string
    event_types?:  string[]
    start:         string
    end:           string
    min_score:     number
    ml_min_prob?:  number
    stop_loss_pct: number
    target_pct:    number
    market?:       string | null
    walkforward?:  boolean
  }
  result?:       BacktestSummary
  trade_log?:    BacktestTradeItem[]
  equity_curve?: BacktestEquityPoint[]
  walkforward?:  BacktestWindowResult[]
  sample_trades?: Array<{
    code:   string
    entry:  string
    exit:   string
    pnl:    number
    status: string
  }>
}

export interface SavedBacktestResult {
  id:          number
  name:        string
  params:      BacktestResult['params']
  result:      BacktestSummary
  equity_curve?: BacktestEquityPoint[]
  created_at:  string
}

export interface BacktestEventStats {
  count:      number
  win_rate:   number
  avg_return: number
}

// ── 수급 ───────────────────────────────────────────────────────────────────────
export interface SupplyDemand {
  date:               string
  foreign_net?:       number
  inst_net?:          number
  indiv_net?:         number
  prog_arbitrage_net?: number
  foreign_hold_rate?: number
}

// ── 종목 분석 ──────────────────────────────────────────────────────────────────
export interface StockAnalysisTechnical {
  trend:       string
  trend_dir:   string
  trend_score: number
  ma5?:        number
  ma20?:       number
  ma60?:       number
  rsi?:        number
  rsi_signal:  string
  bb_upper?:   number
  bb_lower?:   number
  bb_pct?:     number
  atr:         number
  vol_ratio:   number
  w52_high:    number
  w52_low:     number
  w52_pct:     number
  reasons:     string[]
}

export interface StockAnalysisPrediction {
  label:      string
  direction:  string
  low:        number
  mid:        number
  high:       number
  confidence: number
  reasons:    string[]
}

export interface StockAnalysisTarget {
  label:  string
  buy:    number
  target: number
  stop:   number
  rr:     number
  desc:   string
}

export interface StockAnalysisSellTarget {
  price:       number
  return_pct:  number
  desc:        string
  achieved?:   boolean
  breached?:   boolean
}

export interface StockAnalysisNewsItem {
  title:            string
  published_at:     string
  sentiment_score?: number
}

export interface StockAnalysisDisclosureItem {
  rcept_no?:        string
  title:            string
  disclosed_at:     string
  category?:        string
  sentiment_score?: number
}

export interface StockAnalysis {
  code:         string
  name:         string
  market?:      string
  sector?:      string
  industry?:    string
  current_price: number
  error?:       string
  technical:    StockAnalysisTechnical
  predictions:  {
    short: StockAnalysisPrediction
    mid:   StockAnalysisPrediction
    long:  StockAnalysisPrediction
  }
  targets: {
    aggressive:   StockAnalysisTarget
    conservative: StockAnalysisTarget
    safe:         StockAnalysisTarget
  }
  ml_signal?: {
    action:      string
    prob?:       number
    entry?:      number
    target?:     number
    stop?:       number
    created_at?: string
  }
  supply: {
    foreign_5d: number
    inst_5d:    number
    signal?:    string
    reasons:    string[]
  }
  purchase_analysis?: {
    purchase_price:  number
    current_price:   number
    current_return:  number
    pnl:             number
    sell_score:      number
    action:          'STOP_LOSS' | 'HOLD_TRAIL' | 'PARTIAL_EXIT' | 'PARTIAL_EXIT_LARGE' | 'FULL_EXIT'
    trailing_stop:   number
    atr_mult_ts:     number
    forward_targets: Array<{ label: string; price: number; ret_pct: number }>
  }
  news_recent?:        StockAnalysisNewsItem[]
  disclosures_recent?: StockAnalysisDisclosureItem[]
  opinion?:            string
}


// ── 호가·실시간 ──────────────────────────────────────────────────────────────
export interface Quote {
  code:         string
  price:        number
  prev_close:   number
  change:       number
  change_rate:  number
  open:         number
  high:         number
  low:          number
  volume:       number
  amount:       number
  source:       'realtime' | 'daily' | 'none'
}

// ── 유틸 타입 ─────────────────────────────────────────────────────────────────
export type Theme_Mode = 'dark' | 'light'

export interface ApiError {
  detail: string
  status: number
}

// ── 텔레그램 발송 이력 ──────────────────────────────────────────────────────────
export interface TelegramLog {
  id:        number
  msg_type:  'signal' | 'disclosure' | string
  code?:     string
  name?:     string
  title:     string
  message:   string
  success:   boolean
  error_msg?: string
  sent_at:   string
}

export interface TelegramLogList {
  total:  number
  offset: number
  limit:  number
  items:  TelegramLog[]
}

export interface TelegramLogStats {
  total:             number
  success_count:     number
  fail_count:        number
  signal_count:      number
  disclosure_count:  number
  today_count:       number
  last_sent_at?:     string
}
