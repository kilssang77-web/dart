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

export interface CompetitorZoneItem {
  range_lo: number
  range_hi: number
  count: number
  pct: number
}

export interface BidZonePredItem {
  range_lo: number
  range_hi: number
  pct: number
}

export interface CompetitorPredictResponse {
  competitor_id: number
  competitor_name: string
  bid_id: number
  participation: {
    probability: number
    basis: string
    confidence: 'low' | 'medium' | 'high'
  }
  bid_zone: {
    zones: BidZonePredItem[]
    peak_zone: BidZonePredItem | null
    sample_count: number
  }
}

export interface CompetitorZoneResponse {
  zones: CompetitorZoneItem[]
  peak_zone: CompetitorZoneItem | null
  total_count: number
  last_updated: string | null
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
  rate_diff: number | null
  announcement_no: string | null
  note: string | null
  created_at: string
}

export interface CollectorStatus {
  today_notices: number
  today_results: number
  last_run_at: string | null
  next_run_at: string | null
}

export interface BidSearchItem {
  id: number
  announcement_no: string
  title: string
  agency_name: string | null
  base_amount: number
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

// ── 예가 빈도 분석 ──────────────────────────────────────────

export interface YegaCandidate {
  idx: number
  amount: number
  rate: number
}

export interface YegaFreqRow {
  amount: number
  rate: number
  rate_pct: number
  count: number
  probability: number
  cumulative_prob: number
}

export interface YegaChartBin {
  rate_pct: number
  count: number
}

export interface YegaNumberPattern {
  number: number
  freq_pct: number
}

export interface AgencyYegaPattern {
  pattern: YegaNumberPattern[]
  top3_numbers: number[]
  dominant_zone: string | null
  sample_count: number
}

export interface YegaFrequencyResult {
  base_amount: number
  a_value_used: number
  round_unit: number
  candidates: YegaCandidate[]
  frequency: YegaFreqRow[]
  top10: YegaFreqRow[]
  chart_bins: YegaChartBin[]
  total_combinations: number
  recommended_rate: number
  floor_rate: number
  agency_pattern?: AgencyYegaPattern
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

export interface CollectionLogOut {
  id: number
  collect_type: string
  collected_at: string
  success_count: number
  fail_count: number
  duration_sec: number | null
  error_summary: string | null
  created_at: string
}


// ── 패찰 원인 분석 타입 ──────────────────────────────────

export interface MissStatsSummary {
  avg_diff_pct:    number | null
  median_diff_pct: number | null
  std_diff_pct:    number | null
  pct_too_low:     number | null
  pct_too_high:    number | null
  pct_balanced:    number | null
  direction:       'too_low' | 'too_high' | 'balanced' | null
  within_0_5pct:   number | null
  within_1pct:     number | null
}

export interface DefeatDistBin {
  from: number
  to: number
  count: number
}

export interface AgencyDefeatStat {
  agency_name: string
  count: number
  avg_diff: number
  direction: 'too_low' | 'too_high' | 'balanced'
}

export interface MonthlyTrendPoint {
  year_month: string
  avg_diff: number
  count: number
}

export interface DefeatAnalysis {
  miss_stats:       MissStatsSummary
  distribution:     DefeatDistBin[]
  agency_breakdown: AgencyDefeatStat[]
  trend:            MonthlyTrendPoint[]
  win_zone:         { avg_diff: number; sample_count: number; note: string } | null
  total_analyzed:   number
}

// ── 역산 분석 (Gap Distribution) 타입 ───────────────────────

export interface GapBucket {
  range_lo: number
  range_hi: number
  count: number
}

export interface GapAnalysisResponse {
  buckets:              GapBucket[]
  mean_diff:            number | null
  median_diff:          number | null
  win_if_lower_by:      number | null
  consistent_direction: 'too_high' | 'too_low' | 'mixed'
  personal_bias:        PersonalCorrection
  total_analyzed:       number
}

// ── 자사 승률 패턴 진단 타입 ─────────────────────────────

export interface WinPatternBias {
  rate_diff_mean: number | null
  direction: 'above' | 'below' | 'balanced'
  signal: string
}

export interface WinPatternAgency {
  agency_name: string
  total: number
  won: number
  win_rate: number
  avg_rate_diff: number | null
}

export interface WinPatternYear {
  year: number
  total: number
  won: number
  win_rate: number
}

export interface WinPatternLossReasons {
  above_winner: number
  below_floor: number
  below_winner: number
}

export interface WinPattern {
  total: number
  won: number
  lost: number
  overall_win_rate: number
  bias: WinPatternBias
  by_agency: WinPatternAgency[]
  by_industry: Record<string, unknown>[]
  by_year: WinPatternYear[]
  loss_reasons: WinPatternLossReasons
}

// ── 공고 자동 평가 점수 타입 ─────────────────────────────

export interface ScoreComponent {
  pts:  number
  max:  number
  note: string
}

export interface OpportunityScore {
  bid_id:         number
  score:          number | null
  grade:          'A' | 'B' | 'C' | 'D' | null
  breakdown: {
    competition:    ScoreComponent
    personal_track: ScoreComponent
    market_trend:   ScoreComponent
    amount_fit:     ScoreComponent
  } | null
  recommendation: string | null
  error?:         string
}

// ── 공고 자동 추천 타입 ──────────────────────────────────

export interface BidRecommendItem {
  bid_id:          number
  title:           string
  agency_name:     string
  score:           number | null
  grade:           'A' | 'B' | 'C' | 'D' | null
  open_date:       string | null
  base_amount:     number
  score_breakdown: {
    competition:    ScoreComponent
    personal_track: ScoreComponent
    market_trend:   ScoreComponent
    amount_fit:     ScoreComponent
  } | null
}

// ── RecommendV2 개인화 보정 타입 ────────────────────────

export interface PersonalCorrection {
  correction:        number
  agency_correction: number | null
  confidence:        number
  direction:         'too_low' | 'too_high' | 'balanced'
  avg_bias_pct:      number
  sample_count:      number
  narrative:         string
}

// ── 사정율 트렌드 ─────────────────────────────────────────

export interface SrateTrendResponse {
  direction: 'up' | 'down' | 'stable'
  delta: number
  recent_mean: number
  prev_mean: number | null
  sample_count: number
  signal: string
}

export interface TopSrateTrend extends SrateTrendResponse {
  agency_id: number
  agency_name: string
}

// ── 프리즘 2.0 ────────────────────────────────────────────

export interface PrismZone {
  rate: number
  win_prob: number
  floor_ok: boolean
  amount: number
  rank_est: number
}

export interface PrismResponse {
  zones: PrismZone[]
  top10: PrismZone[]
  scan_meta: {
    scan_start: number
    scan_end: number
    scan_step: number
    total_zones: number
    floor_ok_count: number
    top_n: number
    industry_name: string
  }
}

// ── A값·낙찰하한가 ─────────────────────────────────────────

export interface BidRangeResponse {
  a_value:      number
  floor_price:  number
  floor_rate:   number
  srate_center: number
  srate_range: {
    p10: number
    p25: number
    p50: number
    p75: number
    p90: number
  }
  industry_name: string | null
  srate_source?: string | null   // 'inpo21c' | 'lgbm' | 'global'
  inpo21c_n?:    number | null
  confidence?:   number | null
}

// ── 발주처 예가 패턴 ────────────────────────────────────────────

export interface AgencyYegaPattern {
  agency_id:   number
  agency_name: string
  sample_n:    number
  spread_half: number
  pos_weights: number[] | null  // 15개 위치별 추첨 가중치 (합=1.0)
  has_data:    boolean
}

// ── 공동도급 적격심사 AI 매칭 ───────────────────────────────────

export interface JointPartnerItem {
  competitor_id:    number
  name:             string
  biz_reg_no:       string | null
  joint_min_rate:   number
  qualification_ok: boolean
  win_rate:         number
  total_bids:       number
  avg_bid_rate:     number | null
  compat_score:     number
}

export interface JointPartnersResponse {
  partners:       JointPartnerItem[]
  bid_title:      string
  base_amount:    number
  threshold_note: string
}

// ── 공동도급 적격심사 시뮬레이터 ─────────────────────────────────

export interface JointSimPartner {
  competitor_id?:     number
  user_track?:        number
  participation_rate: number
}

export interface JointSimRequest {
  partners: JointSimPartner[]
}

export interface JointSimPartnerResult {
  name:               string
  participation_rate: number
  track_amount:       number
  qual_score:         number
  passes:             boolean
}

export interface JointSimJointResult {
  passes:           boolean
  total_qual_score: number
  threshold:        number
  min_bid_amount:   number
  min_bid_rate:     number
  margin:           number
}

export interface JointSimResponse {
  bid_id:              number
  bid_amount_required: number
  partners:            JointSimPartnerResult[]
  joint_result:        JointSimJointResult
}

// ── 최종 투찰 추천 종합 ───────────────────────────────────────

export interface FinalRecommendStrategy {
  rate:     number
  amount:   number
  win_prob: number
}

export interface FinalRecommendEvidence {
  srate_stats:   { mean: number; sample_count: number; trend_direction: string }
  prism_top:     { rate: number; probability: number } | null
  yega_top:      { rate: number; probability: number } | null
  personal_bias: { rate_diff_mean: number; applied: boolean }
}

export interface FinalRecommendResult {
  bid_id:             number
  base_amount:        number
  recommended_rate:   number
  recommended_amount: number
  confidence:         'high' | 'medium' | 'low'
  floor_rate:         number
  strategies: {
    balanced:     FinalRecommendStrategy
    aggressive:   FinalRecommendStrategy
    conservative: FinalRecommendStrategy
    floor_safe:   FinalRecommendStrategy
  }
  evidence: FinalRecommendEvidence
  signal:   string
}

// ── 발주처 심층분석 ──────────────────────────────────────────

export interface SrateHistogramBin {
  range_lo: number
  range_hi: number
  count: number
  pct: number
}

export interface SrateHistogramResponse {
  agency_id: number
  agency_name: string
  months: number
  sample_count: number
  mean: number | null
  std: number | null
  bins: SrateHistogramBin[]
  percentiles: {
    p10: number | null
    p25: number | null
    p50: number | null
    p75: number | null
    p90: number | null
  }
}

export interface AgencyRecentResult {
  bid_id: number
  title: string
  base_amount: number
  bid_open_date: string | null
  assessment_rate: number | null
  competitor_count: number
}

export interface AgencyRecentResultsResponse {
  items: AgencyRecentResult[]
  total: number
}

