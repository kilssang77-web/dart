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
  estimated_price: number | null
  notice_date: string | null
  bid_open_date: string | null
  bid_close_date: string | null
  status: string
  source: string | null
  winner_rate: number | null
  competitor_count: number
  min_bid_rate: number | null
  yega_method: string | null
  contract_method: string | null
}

export interface BidDetail extends Bid {
  min_bid_rate: number | null
  a_value: number | null
  construction_period: number | null
  region_restriction: boolean
  ntce_url: string | null
  construction_site: string | null
  contract_method: string | null
  bid_method: string | null
  eligible_regions: string | null
  industry_limit: string | null
  contact_name: string | null
  contact_tel: string | null
  yega_method: string | null
  registration_deadline: string | null
  preset_amount: number | null
  yega_ratio: number | null
  net_cost: number | null
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

export interface SchedulerJob {
  id: string
  name: string
  next_run_at: string | null
  last_run_at: string | null
}

export interface CollectionTypeStat {
  collect_type: string
  total_success: number
  total_fail: number
  avg_duration: number | null
  last_run_at: string | null
  run_count: number
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

export interface CollectionLogDetail {
  label?: string
  source?: string
  endpoint?: string
  api_base?: string
  date_from?: string
  date_to?: string
  days_back?: number
  total_processed?: number
  error_details?: string[]
}

export interface CollectionLogOut {
  id: number
  collect_type: string
  collected_at: string
  success_count: number
  fail_count: number
  duration_sec: number | null
  error_summary: string | null
  detail_json: string | null
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

export interface AgencyStrategyBucket {
  from: number
  to: number
  count: number
}

export interface AgencyStrategy {
  agency_id: number
  industry_code: string
  period_months: number
  total_bid_count: number
  avg_win_rate: number | null
  std_win_rate: number | null
  min_win_rate: number | null
  max_win_rate: number | null
  win_rate_p10: number | null
  win_rate_p25: number | null
  win_rate_p50: number | null
  win_rate_p75: number | null
  win_rate_p90: number | null
  avg_competitor_cnt: number | null
  aggression_index: number | null
  qual_difficulty: '易' | '中' | '難' | null
  freq_table: AgencyStrategyBucket[]
  histogram_data: [number, number][]
  volatility_30d: number | null
  trend_direction: 'up' | 'down' | 'stable' | null
  recommended_range_lo: number | null
  recommended_range_hi: number | null
  updated_at: string | null
}

export interface Notification {
  id: number
  ntype: string
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  created_at: string
}

export interface NotificationListResponse {
  items: Notification[]
  unread_count: number
}

export interface InpoParticipant {
  rank: number
  company_name: string
  biz_reg_no: string | null
  bid_rate: number | null
  base_ratio: number | null
  is_winner: boolean
}

export interface SekihaiInfo {
  found: boolean
  total_count?: number
  winner_rate?: number | null
  base_amount?: number | null
  participants?: { rank: number; company_name: string; bid_rate: number | null; is_winner: boolean }[]
}

export interface InpoYegaItem {
  yega_no: number
  amount: number | null
  base_ratio: number | null
  base_ratio_pct: number | null
  is_selected: boolean
}

export interface InpoYegaResponse {
  items: InpoYegaItem[]
}

export interface RivalItem {
  company_name: string
  co_bid_count: number
  avg_bid_rate: number | null
  win_count: number
  competitor_id: number | null
}

export interface RivalRadarResponse {
  bid_id: number
  announcement_no: string
  total_participants: number
  winner_company: string | null
  winner_rate: number | null
  rivals: RivalItem[]
  current_participants: { rank: number; company_name: string; bid_rate: number | null; is_winner: boolean }[]
}

export interface ActualWinZone {
  range_lo: number
  range_hi: number
  count: number
  probability: number
}

export interface ActualWinZonesResponse {
  sample_count: number
  mean_winner_rate: number
  peak_zone: ActualWinZone | null
  zones: ActualWinZone[]
  agency_name: string | null
}

export interface AgencyHeatmapItem {
  agency_name: string
  bid_count: number
  avg_rate: number | null
  p25: number | null
  p75: number | null
  min_rate: number | null
  max_rate: number | null
}

export interface MarketIntelHeatmap {
  months: number
  agencies: AgencyHeatmapItem[]
}

export interface WinnerTrendItem {
  year: number
  month: number
  bid_count: number
  avg_rate: number | null
}

export interface TopWinnerItem {
  company_name: string
  win_count: number
  avg_rate: number | null
  min_rate: number | null
  max_rate: number | null
}

// ── 투찰 실행 관리 ─────────────────────────────────────────

export type ExecutionStatus =
  | '검토중'
  | '참여결정'
  | '투찰완료'
  | '개찰대기'
  | '낙찰'
  | '패찰'
  | '포기'

export interface BidExecution {
  id: number
  bid_id: number | null
  user_id: number
  announcement_no: string | null
  title: string
  agency_name: string | null
  industry_name: string | null
  base_amount: number
  bid_open_date: string | null
  status: ExecutionStatus
  decision_reason: string | null
  decided_at: string | null
  submitted_rate: number | null
  submitted_amount: number | null
  floor_rate: number | null
  a_value: number | null
  recommended_rate: number | null
  submitted_at: string | null
  result_rank: number | null
  total_bidders: number | null
  winner_rate: number | null
  winner_amount: number | null
  winner_name: string | null
  winner_biz_no: string | null
  winner_gap: number | null
  opened_at: string | null
  note: string | null
  source: string
  created_at: string
  updated_at: string
}

export interface DefeatAnalysis {
  id: number
  execution_id: number
  cause_primary: string
  cause_secondary: string | null
  cause_detail: string | null
  winner_gap_pct: number | null
  competitor_cnt: number | null
  our_rank: number | null
  improvement: string | null
  next_rate_adj: number | null
  created_at: string
}

export interface ExecutionSummary {
  status_counts: Record<ExecutionStatus, number>
  today_closing: BidExecution[]
}

export interface ExecutionListResponse {
  total: number
  page: number
  size: number
  items: BidExecution[]
}

export interface SucviewImportResult {
  imported: number
  skipped: number
  competitors_added: number
  errors: string[]
  details: string[]
}

export interface OurCompetitor {
  id: number
  company_name: string
  biz_reg_no: string | null
  co_participation_cnt: number
  co_win_cnt: number
  our_win_when_meet: number
  avg_bid_rate: number | null
  aggression: number | null
  last_seen_at: string | null
  last_seen_agency: string | null
  is_primary_rival: boolean
}

export interface FreqBucket {
  from: number
  to: number
  count: number
  win_count: number
  win_rate: number
}

export interface AgencyFreqResponse {
  agency_id: number
  agency_name: string
  industry_code: string
  period: string
  total_bids: number
  buckets: FreqBucket[]
}

// ── 백테스트 ───────────────────────────────────────────────

export interface BacktestMonthly {
  month: string
  total: number
  actual_win: number
  actual_rate: number
}

export interface BacktestSample {
  title: string
  agency: string
  actual_rate: number
  recommended_rate: number
  winner_rate: number
  gap_improvement?: number
}

export interface BacktestResult {
  period_months: number
  total_bids: number
  actual_wins: number
  actual_win_rate: number
  simulated_wins: number
  simulated_win_rate: number
  improvement_pct: number
  cause_distribution: { cause: string; count: number }[]
  monthly_trend: BacktestMonthly[]
  sample_improvements: BacktestSample[]
  sample_regressions: BacktestSample[]
  data_source: string
  message?: string
}

// ── 포트폴리오 최적화 ────────────────────────────────────────

export interface PortfolioBidItem {
  bid_id:           number
  title:            string
  base_amount:      number
  bid_date:         string
  verdict:          string      // GO | WATCH | NO_GO
  selection_score:  number      // 0~10
  ev_score:         number
  qualify_prob:     number
  win_prob:         number
  recommended_rate: number
}

export interface PortfolioPlanResponse {
  selected:              PortfolioBidItem[]
  not_selected:          PortfolioBidItem[]
  no_go_list:            PortfolioBidItem[]
  expected_wins:         number
  expected_win_amount:   number
  total_ev:              number
  bond_usage:            number
  remaining_bond_after:  number
  alerts:                string[]
  schedule:              { date: string; bids: number[]; note?: string }[]
  stats:                 Record<string, number>
}

export interface ActivePortfolioItem {
  bid_id:         number
  title:          string
  base_amount:    number
  bid_date:       string | null
  submitted_rate: number | null
  bond_exposure:  number
  status:         string
}

export interface PrismBucket {
  srate:     number
  count:     number
  win_count: number
  win_rate:  number
}

export interface PrismZone extends PrismBucket {
  rank:      number
  bid_price: number | null
}

export interface PrismHistogramResponse {
  bid_id:       number
  agency_id:    number | null
  base_amount:  number
  a_ratio:      number
  data_source:  'agency' | 'national'
  period_type:  string
  total_bids:   number
  total_wins:   number
  histogram:    PrismBucket[]
  top_zones:    PrismZone[]
}

// ── Hot Zone + Best Rate ──────────────────────────────────
export interface HotZonePeak {
  srate:     number
  win_rate:  number
  win_count: number
  total:     number
  score:     number
  rank:      number
}

export interface HotZoneResponse {
  bid_id:          number
  agency_id:       number | null
  peaks:           HotZonePeak[]
  best_rate:       number | null
  kde_x:           number[]
  kde_y:           number[]
  data_source:     'agency' | 'national'
  period_type:     string
  collusion_alert: CollusionAlert | null
  total_wins:  number
  total_bids:  number
}

export interface WinnerPercentiles {
  p25: number | null
  p50: number | null
  p65: number | null
  p70: number | null
  p75: number | null
  p85: number | null
}

export interface BestRateResponse {
  bid_id:              number
  base_amount:         number | null
  recommended_srate:   number | null
  recommended_price:   number | null
  confidence:          number
  source:              'winner+hotzone' | 'winner' | 'assessment_based' | 'hotzone+prism' | 'hotzone' | 'prism' | 'fallback'
  a_ratio:             number
  hotzone_peaks:       HotZonePeak[]
  prism_top:           PrismZone[]
  data_source:         'agency' | 'national'
  period_type:         string
  // Option D 추가 필드
  winner_percentiles:  WinnerPercentiles
  winner_count:        number
  target_percentile:   number
  competition_intensity: 'high' | 'normal' | 'low'
  avg_competitors:     number
  assessment_rate_est: number | null
}

// ── 투찰 결정 전용 (TenderDecisionPage) ──────────────────
export interface AgencySrateProfile {
  blended_center: number | null
  seasonal_adj:   number | null
  trend_slope:    number | null
  confidence:     number | null
}

export interface PersonalBiasInfo {
  correction:        number
  agency_correction: number | null
  confidence:        number
  direction:         'too_low' | 'too_high' | 'balanced'
  avg_bias_pct:      number
  sample_count:      number
  narrative:         string
}

export interface CollusionAlert {
  flag:                  'clean' | 'suspicious' | 'collusion' | 'insufficient_data'
  score:                 number
  cv:                    number | null
  n:                     number
  mean_rate:             number
  std_rate:              number
  near_identical_pairs:  number
  cluster_density:       number
  reasons:               string[]
  dense_peaks?:          DensePeak[]
  avoidance_suggestion?: AvoidanceSuggestion | null
}

export interface BidContext {
  bid_id:               number
  announcement_no:      string
  title:                string
  base_amount:          number
  agency_id:            number | null
  agency_name:          string
  industry_id:          number | null
  industry_name:        string
  floor_rate:           number
  a_value:              number | null
  srate_center:         number
  srate_std:            number
  expected_competitors: number
  pos_weights:          number[] | null
  competitor_zones:     CompetitorZone[]
  notice_date:          string | null
  bid_open_date:        string | null
  status:               string | null
  agency_srate_profile: AgencySrateProfile | null
  personal_bias:        PersonalBiasInfo | null
}

export interface CompetitorZone {
  rate:  number
  prob:  number
  // legacy fields
  rate_center?: number
  rate_std?:    number
  count?:       number
}

export interface ZoneItem {
  rate:        number
  amount:      number
  win_prob:    number
  valid_ratio: number
  floor_ok:    boolean
}

export interface StrategyResult {
  rate:            number
  amount:          number
  win_prob:        number
  avg_rank:        number
  valid_ratio:     number
  label:           string
  expected_profit: number | null
  bid_score?:      BidScoreResult
}

export interface SimulateBidRequest {
  yega_values:      number[] | null
  our_bid_rate:     number | null
  competitor_rates: number[] | null
  n_sim:            number
}

export interface BidScoreBenchmark {
  sample_count: number
  avg_pct:      number
  p25_pct:      number
  p50_pct:      number
  p75_pct:      number
  scope:        'agency' | 'similar_agency' | 'national'
}

export interface BidScoreResult {
  score:       number
  max_score:   number
  pct:         number
  grade:       '우수' | '보통' | '불리'
  description: string
}

export interface SimulateBidResponse {
  bid_id:           number
  base_amount:      number
  floor_rate:       number
  srate_center:     number
  srate_std:        number
  mode:             'real' | 'estimated' | 'estimated_bimodal'
  pred_log_id:      number | null
  yega_candidates:  { idx: number; amount: number; rate: number }[]
  top_combinations: { combo: number[]; amount: number; rate: number; prob: number }[]
  all_zones:        ZoneItem[]
  top_zones:        ZoneItem[]
  strategies:       Record<string, StrategyResult>
  optimal:          { rate: number; amount: number; win_prob: number; srate: number; floor_ok: boolean }
  histogram:        { bin_center: number; count: number; prob: number }[]
  bid_score:           BidScoreResult | null
  bid_score_benchmark: BidScoreBenchmark | null
}

export interface PqFloorResponse {
  bid_id:          number
  applicable:      boolean
  pq_floor_rate:   number | null
  pq_floor_amount: number | null
  verdict:         'PASS' | 'FAIL' | 'UNCERTAIN' | 'NOT_APPLICABLE'
  pass_prob:       number
  score_breakdown: Record<string, unknown>
  criteria_type:   string
  warning:         string | null
}

export interface AgencyWinHistogramBin {
  rate:        number
  total_count: number
  win_count:   number
  win_rate:    number
  rank?:       number
}

export interface AgencyWinHistogram {
  bins:        AgencyWinHistogramBin[]
  top_zones:   AgencyWinHistogramBin[]
  total_wins:  number
  total_bids:  number
  data_source: 'agency' | 'national' | 'none'
  agency_id:   number | null
  agency_name: string
  inpo21c_n:   number
}

export interface WinProbPoint {
  bid_rate: number
  win_prob: number
}

export interface WinProbCurve {
  curve:         WinProbPoint[]
  srate:         number
  floor_rate:    number
  n_competitors: number
}

// ── 투찰 저널 ────────────────────────────────────────────────

export interface JournalCreateRequest {
  bid_id:             number
  pred_log_id?:       number | null
  recommended_rate?:  number | null
  recommended_amount?:number | null
  pred_win_prob?:     number | null
  pred_srate_center?: number | null
  strategy_chosen?:   string | null
  submitted_rate:     number
  submitted_amount?:  number | null
  floor_rate?:        number | null
  note?:              string | null
}

export interface JournalResultRequest {
  result:         '낙찰' | '패찰' | '무효' | '취소'
  actual_srate?:  number | null
  our_rank?:      number | null
  total_bidders?: number | null
  winner_rate?:   number | null
  winner_amount?: number | null
  winner_biz_no?: string | null
  winner_name?:   string | null
  note?:          string | null
}

export interface JournalOut {
  id:                 number
  bid_id:             number
  announcement_no:    string | null
  pred_log_id:        number | null
  recommended_rate:   number | null
  recommended_amount: number | null
  pred_win_prob:      number | null
  pred_srate_center:  number | null
  strategy_chosen:    string | null
  submitted_at:       string | null
  submitted_rate:     number | null
  submitted_amount:   number | null
  floor_rate:         number | null
  rate_delta:         number | null
  opened_at:          string | null
  result:             string | null
  our_rank:           number | null
  total_bidders:      number | null
  actual_srate:       number | null
  winner_rate:        number | null
  winner_amount:      number | null
  winner_biz_no:      string | null
  winner_name:        string | null
  rate_gap:           number | null
  srate_error:        number | null
  note:               string | null
  created_at:         string | null
}

export interface JournalMonthlyTrend {
  month:    string
  total:    number
  wins:     number
  losses:   number
  win_rate: number | null
}

export interface JournalStrategyStats {
  strategy:   string
  total:      number
  wins:       number
  win_rate:   number | null
}

export interface JournalStats {
  total:                number
  with_result:          number
  pending_result:       number
  wins:                 number
  losses:               number
  win_rate:             number | null
  avg_srate_mae:        number | null
  avg_rate_gap_loss:    number | null
  avg_rate_delta:       number | null
  feedback_completeness:number
  monthly_trend:        JournalMonthlyTrend[]
  strategy_stats:       JournalStrategyStats[]
}

export interface CalibrationBin {
  prob_bucket:      number
  n:                number
  actual_win_rate:  number
  avg_pred_prob:    number
  wins:             number
  calibration_gap:  number
}

export interface MlCalibration {
  ece:               number | null
  total_samples:     number
  calibration_bins:  CalibrationBin[]
  srate_mae:         number | null
  srate_std:         number | null
  srate_median_bias: number | null
  interpretation:    string
  message?:          string
}

export interface DensePeak {
  center:  number
  density: number
  count:   number
}

export interface AvoidanceSuggestion {
  suggested_rate:  number
  avoid_center:    number
  avoid_density:   number
  avoid_count:     number
  direction:       string
  delta:           number
  nearby_density:  number
  message:         string
}

export interface CollusionResult {
  flag:                 'clean' | 'suspicious' | 'collusion' | 'insufficient_data'
  score:                number
  cv:                   number | null
  n:                    number
  mean_rate?:           number
  std_rate?:            number
  near_identical_pairs: number
  cluster_density:      number
  reasons:              string[]
  announcement_no:      string
  dense_peaks?:         DensePeak[]
  avoidance_suggestion?: AvoidanceSuggestion | null
}

export interface CollusionScanResponse {
  days:          number
  flagged_count: number
  results:       CollusionResult[]
}

export interface ValidationResult {
  id:                 number
  run_at:             string | null
  total:              number
  wins:               number
  actual_win_rate:    number | null
  srate_mae:          number | null
  calibration:        Record<string, number | null> | null
  strategy_win_rates: Record<string, number> | null
}

export interface ValidationResultsResponse {
  results:  ValidationResult[]
  message?: string
}

export interface DefeatCauseStat {
  cause:        string
  count:        number
  pct:          number
  avg_gap_pct:  number | null
  avg_rate_adj: number | null
}

export interface DefeatSummaryRecentItem {
  id:             number
  title:          string
  bid_open_date:  string | null
  submitted_rate: number | null
  winner_rate:    number | null
  gap_pct:        number | null
}

export interface DefeatSummaryResponse {
  total_defeats:      number
  by_cause:           DefeatCauseStat[]
  avg_winner_gap_pct: number | null
  avg_rate_adj:       number | null
  recent:             DefeatSummaryRecentItem[]
}

export interface UpcomingOpening {
  id: number
  announcement_no: string
  title: string
  agency_name: string
  industry_name: string
  base_amount: number
  bid_open_date: string
  days_left: number
  hours_left: number
  urgency: 'today' | 'tomorrow' | 'soon' | 'normal' | 'past'
  source: string
}

export interface UpcomingOpeningsResponse {
  items: UpcomingOpening[]
  total: number
  days: number
}

export interface CompetitorPrediction {
  company_name: string
  biz_reg_no: string | null
  total_bids: number
  wins: number
  win_rate: number
  avg_rate_pct: number
  std_pct: number | null
  p10_pct: number | null
  p25_pct: number | null
  p50_pct: number | null
  p75_pct: number | null
  p90_pct: number | null
  typical_range: [number, number] | null
  aggression: 'aggressive' | 'conservative' | 'volatile' | 'balanced'
  last_seen: string | null
}

export interface CompetitorPredictionResponse {
  competitors: CompetitorPrediction[]
  match_type: 'agency' | 'industry' | 'national' | 'none'
  agency_name: string
  industry_name: string
  data_points: number
}

export interface JournalGapAnalysis {
  summary: {
    total: number
    wins: number
    win_rate: number
    avg_abs_gap_pct: number | null
    avg_signed_gap_pct: number | null
    within_0_5pct: number
    within_1pct: number
    within_2pct: number
  }
  monthly: { month: string; total: number; wins: number; avg_gap: number | null }[]
  histogram: { bucket_pct: number; count: number }[]
  by_strategy: { strategy: string; total: number; wins: number; avg_gap: number | null }[]
}

export interface RecommendationEffect {
  tolerance_pct: number
  followed: {
    n: number
    win_rate: number | null
    avg_abs_gap: number | null
    avg_pred_win_prob: number | null
  }
  deviated: {
    n: number
    win_rate: number | null
    avg_abs_gap: number | null
    avg_pred_win_prob: number | null
  }
  lift_pct: number | null
  message: string
  by_strategy: { strategy: string; followed_n: number; followed_wins: number; win_rate: number | null }[]
}

// ── A값 포지션 분석 (inpo21c_yega is_selected) ──────────────
export interface PositionItem {
  position: number
  freq_pct: number
}

export interface PositionAnalysisResponse {
  bid_id: number
  recommended_rate: number | null
  recommended_amount: number | null
  expected_srate: number | null
  top_positions: number[]           // 상위 포지션 번호 목록 e.g. [1, 8, 2, 3]
  position_pattern: PositionItem[]  // 15개 포지션 전체 빈도 [{position, freq_pct}]
  confidence: number
  sample_count: number
  data_source: 'agency' | 'national' | 'fallback'
  eff_floor: number | null
  has_data: boolean
}

export interface QuickDecisionResponse {
  bid_id: number
  title: string
  base_amount: number
  recommended_rate: number | null
  recommended_amount: number | null
  win_prob: number | null
  go_decision: 'go' | 'pass' | 'neutral'
  go_score: number
  confidence: number
  reasons: string[]
  risk_factors: string[]
  expected_competitors: number
  agency_win_rate: number | null
  best_rate_source: string | null
  position_top4: number[]   // 상위 포지션 번호 목록
  floor_rate: number
}

