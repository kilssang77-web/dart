from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date


# -- ?? --------------------------------------------------

class ApiResponse(BaseModel):
    success: bool = True
    data: Optional[object] = None
    message: str = "OK"


# -- ?? --------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str
    role: str


class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str = "viewer"
    department: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str]
    role: str
    department: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# -- ?? --------------------------------------------------

class BidResultOut(BaseModel):
    id: int
    competitor_id: int
    competitor_name: str
    bid_amount: int
    bid_rate: float
    rank: int
    is_winner: bool
    assessment_rate: Optional[float]

    class Config:
        from_attributes = True


class BidSummary(BaseModel):
    id: int
    announcement_no: str
    title: str
    agency_name: str
    industry_name: Optional[str]
    region_name: Optional[str]
    base_amount: int
    notice_date: Optional[date] = None
    bid_open_date: Optional[datetime]
    status: str
    winner_rate: Optional[float] = None
    competitor_count: Optional[int] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class BidDetail(BidSummary):
    min_bid_rate: Optional[float]
    estimated_price: Optional[int] = None
    a_value: Optional[int]
    construction_period: Optional[int]
    region_restriction: bool
    ntce_url: Optional[str] = None
    # ?? ??
    construction_site: Optional[str] = None
    contract_method: Optional[str] = None
    bid_method: Optional[str] = None
    eligible_regions: Optional[str] = None
    industry_limit: Optional[str] = None
    bid_close_date: Optional[datetime] = None
    contact_name: Optional[str] = None
    contact_tel: Optional[str] = None
    results: List[BidResultOut] = []

    class Config:
        from_attributes = True


class BidCreate(BaseModel):
    announcement_no: str
    title: str
    agency_id: int
    industry_id: Optional[int] = None
    region_id: Optional[int] = None
    base_amount: int
    min_bid_rate: Optional[float] = None
    a_value: Optional[int] = None
    bid_open_date: Optional[datetime] = None
    construction_period: Optional[int] = None
    region_restriction: bool = False


class BidResultCreate(BaseModel):
    competitor_name: str
    bid_amount: int
    bid_rate: float
    rank: int
    is_winner: bool = False


class BidListParams(BaseModel):
    agency_id: Optional[int] = None
    industry_id: Optional[int] = None
    region_id: Optional[int] = None
    status: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    keyword: Optional[str] = None
    page: int = 1
    size: int = 20


# -- ?? --------------------------------------------------

class RecommendRequest(BaseModel):
    industry_id: int
    region_id: int
    agency_id: int
    base_amount: int
    a_value: Optional[int] = None
    construction_period: Optional[int] = None
    known_competitor_ids: List[int] = []
    our_planned_rate: Optional[float] = None


class RateRange(BaseModel):
    safe_lower: float
    lower: float
    center: float
    upper: float
    safe_upper: float


class WinProbabilities(BaseModel):
    at_lower: float
    at_center: float
    at_upper: float


class ExplanationFactor(BaseModel):
    feature: str
    label: str
    value: object
    shap_value: float
    direction: str  # "positive" | "negative"


class Explanation(BaseModel):
    top_factors: List[ExplanationFactor]
    narrative_ko: str
    base_rate: float
    model_version: str
    data_count: int


class RiskInfo(BaseModel):
    level: str   # LOW | MEDIUM | HIGH
    factors: List[str]
    score: float


class SimilarCase(BaseModel):
    bid_id: int
    title: str
    agency_name: str
    base_amount: int
    bid_open_date: Optional[datetime]
    winner_rate: Optional[float]
    competitor_count: int
    similarity_score: float


class RecommendResponse(BaseModel):
    rate_range: RateRange
    win_probabilities: WinProbabilities
    risk: RiskInfo
    explanation: Explanation
    similar_cases: List[SimilarCase]


# -- ??? --------------------------------------------------

class CompetitorSummary(BaseModel):
    id: int
    name: str
    total_bids: int
    win_count: int
    win_rate: float
    avg_bid_rate: float
    aggression_score: float
    risk_level: str

    class Config:
        from_attributes = True


class CompetitorDetail(CompetitorSummary):
    std_bid_rate: float
    p25_rate: float
    p75_rate: float
    consistency_score: float
    frequent_rivals: List[dict] = []
    monthly_trend: List[dict] = []


class CompetitorTimelinePoint(BaseModel):
    year: int
    month: int
    bid_count: int
    win_count: int
    avg_rate: float


# -- ?? --------------------------------------------------

class OverviewStats(BaseModel):
    total_bids: int
    total_competitors: int
    avg_win_rate: float
    avg_bid_rate: float
    avg_competitor_count: float
    monthly_trend: List[dict]


class AgencyStats(BaseModel):
    agency_id: int
    agency_name: str
    bid_count: int
    avg_rate: float
    avg_competitor_count: float
    our_win_rate: Optional[float]


class IndustryStats(BaseModel):
    industry_id: int
    industry_name: str
    bid_count: int
    avg_rate: float
    avg_competitor_count: float


class HeatmapCell(BaseModel):
    x_label: str
    y_label: str
    value: float
    count: int


# -- ??? --------------------------------------------------

class WatchKeywordCreate(BaseModel):
    keyword: str
    kw_type: str = "general"
    note: Optional[str] = None


class WatchKeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    kw_type: Optional[str] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


class WatchKeywordOut(BaseModel):
    id: int
    keyword: str
    kw_type: str
    is_active: bool
    note: Optional[str]
    announcement_no: Optional[str]
    floor_rate: Optional[float]
    a_value: Optional[int]
    rate_diff: Optional[float]
    winner_biz_no: Optional[str]
    winner_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
# -- ????? ?? v2 --------------------------------------------------

class RecommendV2Request(BaseModel):
    agency_id:             int
    industry_id:           int
    region_id:             int
    base_amount:           int
    min_bid_rate:          float = 0.87745
    bid_open_date:         Optional[datetime] = None
    a_value:               Optional[int] = None
    construction_period:   Optional[int] = None
    known_competitor_ids:  List[int] = []


class StrategyOption(BaseModel):
    rate:     float
    target:   str
    risk:     str
    note:     str
    win_prob: Optional[float] = None
    avg_rank: Optional[float] = None


class StrategySet(BaseModel):
    aggressive:        StrategyOption
    balanced:          StrategyOption
    conservative:      StrategyOption
    avoid_competition: StrategyOption


class SrateRange(BaseModel):
    p10:    float
    lower:  float
    center: float
    upper:  float
    p90:    float


class EstimatedPriceInfo(BaseModel):
    srate_range:            SrateRange
    estimated_price_range:  dict
    confidence:             float
    used_model:             bool
    sample_count:           int


class WinProbV2(BaseModel):
    at_aggressive:        float
    at_balanced:          float = 0.0
    at_conservative:      float
    at_avoid_competition: float = 0.0


class CompetitionInfo(BaseModel):
    score:                float
    pressure:             float
    hhi:                  float
    expected_competitors: int
    floor_rate:           float
    aggressive_ratio:     float
    recent_winner_min:    float


class RiskV2(BaseModel):
    level:   str
    score:   float
    factors: List[str]


class ExplanationV2(BaseModel):
    top_factors:   List[ExplanationFactor]
    narrative_ko:  str
    model_version: str
    data_count:    int
    base_rate:     float



class SimulationResult(BaseModel):
    n_sim:          int
    floor_rate_pct: float
    srate_p10:      float
    srate_p25:      float
    srate_median:   float
    srate_p75:      float
    srate_p90:      float
    floor_abs_p50:  float

class RecommendV2Response(BaseModel):
    rate_range:       RateRange
    strategies:       StrategySet
    estimated_price:  EstimatedPriceInfo
    win_probabilities: WinProbV2
    risk:             RiskV2
    competition:      CompetitionInfo
    ensemble_weights: dict
    explanation:      ExplanationV2
    similar_cases:    List[SimilarCase]
    market_trend:     dict
    simulation:            Optional[SimulationResult] = None
    personal_correction:   Optional[dict] = None


# -- A값·낙찰하한가 --------------------------------------------------

class BidRangeResponse(BaseModel):
    a_value:       int
    floor_price:   int
    floor_rate:    float
    srate_center:  float
    srate_range:   dict
    industry_name: Optional[str] = None


# -- ?? ?? --------------------------------------------------

class MyBidRecordCreate(BaseModel):
    title: str
    agency_name: Optional[str] = None
    bid_date: Optional[date] = None
    base_amount: Optional[int] = 0
    submitted_rate: float
    recommendation_rate: Optional[float] = None
    bid_id: Optional[int] = None
    note: Optional[str] = None
    announcement_no: Optional[str] = None
    actual_winner_rate: Optional[float] = None
    result: Optional[str] = "pending"

class MyBidRecordUpdate(BaseModel):
    result: Optional[str] = None        # pending/won/lost
    actual_winner_rate: Optional[float] = None
    note: Optional[str] = None
    submitted_rate: Optional[float] = None

class MyBidRecordOut(BaseModel):
    id: int
    bid_id: Optional[int]
    title: str
    agency_name: Optional[str]
    bid_date: Optional[date]
    base_amount: int
    submitted_rate: float
    recommendation_rate: Optional[float]
    result: str
    actual_winner_rate: Optional[float]
    note: Optional[str]
    announcement_no: Optional[str]
    floor_rate: Optional[float]
    a_value: Optional[int]
    rate_diff: Optional[float]
    winner_biz_no: Optional[str]
    winner_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ?? ??? ?? ??????????????????????????
# -- 사정율 트렌드 --------------------------------------------------

class SrateTrendResponse(BaseModel):
    direction: str               # "up" | "down" | "stable"
    delta: float
    recent_mean: float
    prev_mean: Optional[float]
    sample_count: int
    signal: str


class TopSrateTrend(SrateTrendResponse):
    agency_id: int
    agency_name: str


class SrateDistributionBin(BaseModel):
    rate_pct: float
    count: int

class SrateDistributionResponse(BaseModel):
    bins: list[SrateDistributionBin]
    mode: Optional[float]
    p25: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    mean: Optional[float]
    std: Optional[float]
    sample_count: int

# ?? ?? ?? ????????????????????????????
class AgencySummary(BaseModel):
    id: int
    name: str
    type: Optional[str]
    region_name: Optional[str]
    bid_count: int

class AgencyListResponse(BaseModel):
    items: list[AgencySummary]
    total: int

class AgencyMonthlyTrend(BaseModel):
    year_month: str
    bid_count: int
    win_rate: Optional[float]
    avg_srate: Optional[float]

class AgencySrateDistribution(BaseModel):
    bins: list[SrateDistributionBin]
    mode: Optional[float]
    p25: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    mean: Optional[float]

class AgencyTopWinner(BaseModel):
    competitor_name: str
    win_count: int
    avg_bid_rate: Optional[float]

class AgencyAmountBucket(BaseModel):
    bucket_label: str
    count: int
    avg_win_rate: Optional[float]

class AgencyAnalysisSummary(BaseModel):
    name: str
    total_bids: int
    avg_win_rate: Optional[float]
    avg_srate: Optional[float]
    dominant_industry: Optional[str]

class AgencyAnalysisResponse(BaseModel):
    summary: AgencyAnalysisSummary
    monthly_trend: list[AgencyMonthlyTrend]
    srate_distribution: AgencySrateDistribution
    top_winners: list[AgencyTopWinner]
    amount_distribution: list[AgencyAmountBucket]

# 발주처 심층분석 스키마
class SrateHistogramBin(BaseModel):
    range_lo: float
    range_hi: float
    count: int
    pct: float

class SrateHistogramResponse(BaseModel):
    agency_id: int
    agency_name: str
    months: int
    sample_count: int
    mean: Optional[float]
    std: Optional[float]
    bins: list[SrateHistogramBin]
    percentiles: dict

class AgencyRecentResult(BaseModel):
    bid_id: int
    title: str
    base_amount: float
    bid_open_date: Optional[str]
    assessment_rate: Optional[float]
    competitor_count: int

class AgencyRecentResultsResponse(BaseModel):
    items: list[AgencyRecentResult]
    total: int

# ?? ??? ???? ??????????????????????
class CompetitorRadar(BaseModel):
    aggression: float
    consistency: float
    concentration: float
    risk: float
    activity: float

class CompetitorAmountPattern(BaseModel):
    bucket: str
    bid_count: int
    win_count: int
    avg_rate: Optional[float]
    win_rate: Optional[float]

class CompetitorRecentTrend(BaseModel):
    direction: str  # aggressive | stable | defensive
    change_pct: Optional[float]

class CompetitorPatternResponse(BaseModel):
    radar: CompetitorRadar
    amount_pattern: list[CompetitorAmountPattern]
    recent_trend: CompetitorRecentTrend

class CompetitorCompareItem(BaseModel):
    id: int
    name: str
    radar: CompetitorRadar
    monthly_trend: list[dict]

class CompetitorCompareResponse(BaseModel):
    competitors: list[CompetitorCompareItem]

# ?? ?? ?? ????????????????????????????
class CollectionLogOut(BaseModel):
    id: int
    collect_type: str
    collected_at: datetime
    success_count: int
    fail_count: int
    duration_sec: Optional[float]
    error_summary: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ?? ??? ???????????????????????????????
class BookmarkResponse(BaseModel):
    bid_id: int
    user_id: int
    note: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ?? My?? ?? ??????????????????????????
class MyBidScatterPoint(BaseModel):
    submitted_rate: float
    recommendation_rate: Optional[float]
    result: str
    bid_date: str

class MyBidMonthlyAccuracy(BaseModel):
    year_month: str
    mae: Optional[float]
    win_count: int
    total: int

class MyBidAccuracyStats(BaseModel):
    avg_error: Optional[float]
    median_error: Optional[float]
    accuracy_1pct: Optional[float]  # ?1% ???
    accuracy_3pct: Optional[float]  # ?3% ???
    total_records: int

class MyBidAnalysisResponse(BaseModel):
    accuracy_stats: MyBidAccuracyStats
    rate_scatter: list[MyBidScatterPoint]
    monthly_accuracy: list[MyBidMonthlyAccuracy]

# ?? ???? KPI ??? ???????????????????
class OverviewStatsWithChange(BaseModel):
    # ?? OverviewStats ??? + ???
    total_bids: int
    total_competitors: int
    avg_win_rate: Optional[float]
    avg_bid_rate: Optional[float]
    avg_competitor_count: Optional[float]
    monthly_trend: list[dict]
    win_rate_change_pct: Optional[float]
    bid_count_change_pct: Optional[float]
    avg_competitors_change: Optional[float]



# ── ② 패찰 원인 분석 스키마 ──────────────────────────────

class MissStatsSummary(BaseModel):
    avg_diff_pct:    Optional[float] = None
    median_diff_pct: Optional[float] = None
    std_diff_pct:    Optional[float] = None
    pct_too_low:     Optional[float] = None
    pct_too_high:    Optional[float] = None
    pct_balanced:    Optional[float] = None
    direction:       Optional[str]   = None
    within_0_5pct:   Optional[float] = None
    within_1pct:     Optional[float] = None

class DefeatDistBin(BaseModel):
    from_: float = Field(..., alias="from")
    to: float
    count: int
    model_config = ConfigDict(populate_by_name=True)

class AgencyDefeatStat(BaseModel):
    agency_name: str
    count: int
    avg_diff: float
    direction: str

class MonthlyTrendPoint(BaseModel):
    year_month: str
    avg_diff: float
    count: int

class DefeatAnalysisResponse(BaseModel):
    miss_stats:       MissStatsSummary
    distribution:     list[dict]
    agency_breakdown: list[AgencyDefeatStat]
    trend:            list[MonthlyTrendPoint]
    win_zone:         Optional[dict] = None
    total_analyzed:   int

# ── 역산 분석 (Gap Distribution) 스키마 ─────────────────────

class GapBucket(BaseModel):
    range_lo: float
    range_hi: float
    count: int

class GapAnalysisResponse(BaseModel):
    buckets:              list[GapBucket]
    mean_diff:            Optional[float] = None
    median_diff:          Optional[float] = None
    win_if_lower_by:      Optional[float] = None
    consistent_direction: str
    personal_bias:        dict
    total_analyzed:       int


# ── 프리즘 2.0 스키마 ────────────────────────────────────

class PrismZone(BaseModel):
    rate:     float
    win_prob: float
    floor_ok: bool
    amount:   int
    rank_est: float

class PrismResponse(BaseModel):
    zones:     List[PrismZone]
    top10:     List[PrismZone]
    scan_meta: dict


# ── 경쟁사 투찰 구간 분포 스키마 ────────────────────────────

class CompetitorZoneItem(BaseModel):
    range_lo: float
    range_hi: float
    count: int
    pct: float

class CompetitorZoneResponse(BaseModel):
    zones: List[CompetitorZoneItem]
    peak_zone: Optional[CompetitorZoneItem]
    total_count: int
    last_updated: Optional[datetime]

# ── ⑧ 공고 자동 평가 점수 스키마 ───────────────────────────

class ScoreComponent(BaseModel):
    pts:  float
    max:  int
    note: str

class OpportunityScoreResponse(BaseModel):
    bid_id:         int
    score:          Optional[float]
    grade:          Optional[str]   = None
    breakdown: Optional[dict]       = None
    recommendation: Optional[str]   = None
    error:          Optional[str]   = None

class BidRecommendItem(BaseModel):
    bid_id:          int
    title:           str
    agency_name:     str
    score:           Optional[float]
    grade:           Optional[str]
    open_date:       Optional[str]
    base_amount:     int
    score_breakdown: Optional[dict]


class YegaNumberPattern(BaseModel):
    number:   int
    freq_pct: float


class AgencyYegaPattern(BaseModel):
    pattern:       list[YegaNumberPattern]
    top3_numbers:  list[int]
    dominant_zone: Optional[str]
    sample_count:  int


# ── 공동도급 적격심사 AI 매칭 스키마 ────────────────────────────

class JointPartnerItem(BaseModel):
    competitor_id:    int
    name:             str
    biz_reg_no:       Optional[str]
    joint_min_rate:   float
    qualification_ok: bool
    win_rate:         float
    total_bids:       int
    avg_bid_rate:     Optional[float]
    compat_score:     float


class JointPartnersResponse(BaseModel):
    partners:       List[JointPartnerItem]
    bid_title:      str
    base_amount:    int
    threshold_note: str


# ── 공동도급 적격심사 시뮬레이터 스키마 ──────────────────────────

class JointSimPartner(BaseModel):
    competitor_id:      Optional[int]   = None  # 경쟁사 ID (DB 조회)
    user_track:         Optional[float] = None  # 귀사 실적금액(원)
    participation_rate: float                   # 지분율 (0.0~1.0)


class JointSimRequest(BaseModel):
    partners: List[JointSimPartner]


class JointSimPartnerResult(BaseModel):
    name:               str
    participation_rate: float
    track_amount:       int
    qual_score:         float
    passes:             bool


class JointSimJointResult(BaseModel):
    passes:           bool
    total_qual_score: float
    threshold:        float
    min_bid_amount:   int
    min_bid_rate:     float
    margin:           int


class JointSimResponse(BaseModel):
    bid_id:              int
    bid_amount_required: int
    partners:            List[JointSimPartnerResult]
    joint_result:        JointSimJointResult


# ── ⑨ 최종 투찰 추천 종합 스키마 ───────────────────────────

class FinalRecommendStrategy(BaseModel):
    rate:     float
    amount:   int
    win_prob: float


class FinalRecommendEvidence(BaseModel):
    srate_stats:   dict
    prism_top:     Optional[dict]
    yega_top:      Optional[dict]
    personal_bias: dict


class FinalRecommendResponse(BaseModel):
    bid_id:             int
    base_amount:        int
    recommended_rate:   float
    recommended_amount: int
    confidence:         str   # high / medium / low
    floor_rate:         float
    strategies:         dict  # balanced / aggressive / conservative / floor_safe
    evidence:           FinalRecommendEvidence
    signal:             str


# ── 자사 승률 패턴 진단 스키마 ─────────────────────────────

class WinPatternBias(BaseModel):
    rate_diff_mean: Optional[float] = None
    direction: str  # above / below / balanced
    signal: str

class WinPatternAgency(BaseModel):
    agency_name: str
    total: int
    won: int
    win_rate: float
    avg_rate_diff: Optional[float] = None

class WinPatternYear(BaseModel):
    year: int
    total: int
    won: int
    win_rate: float

class WinPatternLossReasons(BaseModel):
    above_winner: int
    below_floor: int
    below_winner: int

class WinPatternResponse(BaseModel):
    total: int
    won: int
    lost: int
    overall_win_rate: float
    bias: WinPatternBias
    by_agency: list[WinPatternAgency]
    by_industry: list[dict]
    by_year: list[WinPatternYear]
    loss_reasons: WinPatternLossReasons


# ── 경쟁사 행동 예측 스키마 ──────────────────────────────────

class ParticipationPrediction(BaseModel):
    probability: float
    basis: str
    confidence: str  # low / medium / high

class BidZonePredItem(BaseModel):
    range_lo: float
    range_hi: float
    pct: float

class BidZonePrediction(BaseModel):
    zones: List[BidZonePredItem]
    peak_zone: Optional[BidZonePredItem]
    sample_count: int

class CompetitorPredictResponse(BaseModel):
    competitor_id: int
    competitor_name: str
    bid_id: int
    participation: ParticipationPrediction
    bid_zone: BidZonePrediction

