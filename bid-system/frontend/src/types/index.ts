export interface User {
  id: number
  email: string
  name: string | null
  role: 'admin' | 'analyst' | 'viewer'
  department: string | null
  is_active: boolean
  last_login: string | null
  created_at: string
}

export interface Bid {
  id: number
  announcement_no: string
  title: string
  agency_name: string
  industry_name: string | null
  region_name: string | null
  base_amount: number
  notice_date: string | null
  bid_open_date: string | null
  status: string
  source: string | null
  winner_rate: number | null
  competitor_count: number
}

export interface BidDetail extends Bid {
  min_bid_rate: number | null
  estimated_price: number | null
  a_value: number | null
  construction_period: number | null
  region_restriction: boolean
  ntce_url: string | null
  // new fields
  construction_site: string | null
  contract_method: string | null
  bid_method: string | null
  eligible_regions: string | null
  industry_limit: string | null
  bid_close_date: string | null
  contact_name: string | null
  contact_tel: string | null
  results: BidResultItem[]
}

export interface BidResultItem {
  id: number
  competitor_id: number
  competitor_name: string
  bid_amount: number
  bid_rate: number
  rank: number
  is_winner: boolean
  assessment_rate: number | null
}

export interface MetaData {
  agencies:   { id: number; name: string }[]
  industries: { id: number; name: string }[]
  regions:    { id: number; name: string }[]
}

export interface RateRange {
  safe_lower: number
  lower: number
  center: number
  upper: number
  safe_upper: number
}

export interface WinProbabilities {
  at_lower: number
  at_center: number
  at_upper: number
}

export interface ExplanationFactor {
  feature: string
  label: string
  value: unknown
  shap_value: number
  direction: 'positive' | 'negative'
}

export interface Explanation {
  top_factors: ExplanationFactor[]
  narrative_ko: string
  base_rate: number
  model_version: string
  data_count: number
}

export interface RiskInfo {
  level: 'LOW' | 'MEDIUM' | 'HIGH'
  factors: string[]
  score: number
}

export interface SimilarCase {
  bid_id: number
  title: string
  agency_name: string
  base_amount: number
  bid_open_date: string | null
  winner_rate: number | null
  competitor_count: number
  similarity_score: number
}

export interface RecommendResult {
  rate_range: RateRange
  win_probabilities: WinProbabilities
  risk: RiskInfo
  explanation: Explanation
  similar_cases: SimilarCase[]
}

export interface Competitor {
  id: number
  name: string
  total_bids: number
  win_count: number
  win_rate: number
  avg_bid_rate: number
  std_bid_rate: number
  p25_rate: number
  p75_rate: number
  aggression_score: number
  consistency_score: number
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN'
  frequent_rivals?: { competitor_id: number; name: string; co_occurrence: number }[]
  monthly_trend?: { year: number; month: number; bid_count: number; win_count: number; avg_rate: number | null }[]
}

export interface OverviewStats {
  total_bids: number
  total_competitors: number
  avg_win_rate: number
  avg_bid_rate: number
  avg_competitor_count: number
  monthly_trend: { year: number; month: number; bid_count: number; avg_rate: number | null }[]
}

export interface WatchKeyword {
  id: number
  keyword: string
  kw_type: string
  is_active: boolean
  note: string | null
  created_at: string
}

export interface AdminUser {
  id: number
  email: string
  name: string | null
  role: string
  department: string | null
  is_active: boolean
  last_login: string | null
  created_at: string
}

export interface SystemStatus {
  db_stats: {
    total_bids: number
    g2b_bids: number
    new_bids_7d: number
    total_results: number
    total_competitors: number
    total_users: number
    active_keywords: number
  }
  collector: {
    enabled: boolean
    last_g2b_collect: string | null
  }
  ml_stats: {
    predictions_30d: number
  }
  daily_collection: { date: string; count: number }[]
}

export interface RegionStat {
  region_id: number
  region_name: string
  bid_count: number
  avg_rate: number | null
  total_amount: number
}

export interface IndustryStat {
  industry_id: number
  industry_name: string
  bid_count: number
  avg_rate: number | null
  avg_competitor_count: number | null
  total_amount: number
}

export interface ClusterResult {
  clusters: {
    cluster_id: number
    count: number
    avg_amount: number
    avg_rate: number | null
    avg_comp: number
    top_industry: string
    amount_range: [number, number]
  }[]
  total_count: number
  error?: string
}

export interface ModelInfo {
  model: {
    version: string
    train_size: number
    winner_size: number
  }
  data_availability: {
    total_results: number
    winner_results: number
    ready_for_ml: boolean
  }
  period_data?: {
    results: number
    winners: number
    months: number
  }
  usage: {
    predictions_30d: number
    predictions_period?: number
  }
}
// ── 하이브리드 추천 v2 타입 ──────────────────────────

export interface SrateRange {
  p10:    number
  lower:  number
  center: number
  upper:  number
  p90:    number
}

export interface EstimatedPriceInfo {
  srate_range: SrateRange
  estimated_price_range: { lower: number; center: number; upper: number }
  confidence: number
  used_model: boolean
  sample_count: number
}

export interface StrategyOption {
  rate:   number
  target: string
  risk:   string
  note:   string
}

export interface StrategySet {
  aggressive:   StrategyOption
  balanced:     StrategyOption
  conservative: StrategyOption
}

export interface CompetitorProfile {
  competitor_id: number
  name:          string
  avg_rate:      number
  bid_count:     number
  win_count:     number
  win_rate:      number
  aggression:    number
  risk_level:    string
}

export interface CompetitionInfo {
  score:                number
  pressure:             number
  hhi:                  number
  expected_competitors: number
  floor_rate:           number
  aggressive_ratio:     number
  recent_winner_min:    number
  profiles:             CompetitorProfile[]
}

export interface MarketTrend {
  srate_4w_change:  number
  rate_4w_change:   number
  volume_4w_change: number
  volatility_index: number
  trend_adjustment: number
  has_recent_data:  boolean
}

export interface RecommendV2Result {
  rate_range:        RateRange
  strategies:        StrategySet
  estimated_price:   EstimatedPriceInfo
  win_probabilities: { at_aggressive: number; at_balanced: number; at_conservative: number; at_avoid_competition?: number }
  risk:              { level: string; score: number; factors: string[] }
  competition:       CompetitionInfo
  ensemble_weights:  { engine_a: number; engine_b: number }
  explanation:       { top_factors: ExplanationFactor[]; narrative_ko: string; model_version: string; data_count: number; base_rate: number }
  similar_cases:     SimilarCase[]
  market_trend:      MarketTrend
}
export interface IndustryFilterItem {
  industry_id: number
  name: string
  code: string
  is_active: boolean
  is_configured: boolean
}

export interface MyBidRecord {
  id: number
  bid_id: number | null
  title: string
  agency_name: string | null
  bid_date: string | null
  base_amount: number
  submitted_rate: number
  recommendation_rate: number | null
  result: 'pending' | 'won' | 'lost'
  actual_winner_rate: number | null
  note: string | null
  created_at: string
}

export interface MyBidStats {
  total: number
  won: number
  lost: number
  pending: number
  win_rate: number
  avg_submitted_rate: number | null
  avg_recommendation_rate: number | null
  avg_winner_rate: number | null
  avg_rate_diff_from_rec: number | null
}

export interface BookmarkItem {
  id: number
  bid_id: number
  user_id: number
  note: string | null
  created_at: string
}

export interface MyBidScatterPoint {
  submitted_rate: number
  recommendation_rate: number | null
  result: string
  bid_date: string
}

export interface MyBidMonthlyAccuracy {
  year_month: string
  mae: number | null
  win_count: number
  total: number
}

export interface MyBidAccuracyStats {
  avg_error: number | null
  median_error: number | null
  accuracy_1pct: number | null
  accuracy_3pct: number | null
  total_records: number
}

export interface MyBidAnalysis {
  accuracy_stats: MyBidAccuracyStats
  rate_scatter: MyBidScatterPoint[]
  monthly_accuracy: MyBidMonthlyAccuracy[]
}

export interface SrateStatSummary {
  mean: number
  std: number
  sample_count: number
  p25?: number
  p50?: number
  p75?: number
  p10?: number
  p90?: number
}

export interface SrateDistributionResult {
  bins: { rate_pct: number; count: number }[]
  mode: number | null
  mean: number | null
  std: number | null
  p25: number | null
  p50: number | null
  p75: number | null
  sample_count: number
  agency_stats:   SrateStatSummary | null
  industry_stats: SrateStatSummary | null
  global_stats:   SrateStatSummary | null
}

export interface OverviewStatsWithChange {
  total_bids: number
  total_competitors: number
  avg_win_rate: number | null
  avg_bid_rate: number | null
  avg_competitor_count: number | null
  monthly_trend: { year: number; month: number; bid_count: number; avg_rate: number | null }[]
  win_rate_change_pct: number | null
  bid_count_change_pct: number | null
  avg_competitors_change: number | null
}

