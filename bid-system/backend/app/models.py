from sqlalchemy import (
    Column, Integer, BigInteger, SmallInteger, String, Text,
    Boolean, Numeric, Float, Date, DateTime, ARRAY, JSON, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Region(Base):
    __tablename__ = "regions"
    id        = Column(Integer, primary_key=True)
    code      = Column(String(10), unique=True, nullable=False)
    name      = Column(String(50), nullable=False)
    parent_id = Column(Integer, ForeignKey("regions.id"))


class Industry(Base):
    __tablename__ = "industries"
    id        = Column(Integer, primary_key=True)
    code      = Column(String(20), unique=True, nullable=False)
    name      = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("industries.id"))


class Agency(Base):
    __tablename__ = "agencies"
    id         = Column(Integer, primary_key=True)
    code       = Column(String(20), unique=True)
    name       = Column(String(200), nullable=False)
    type       = Column(String(50))
    region_id  = Column(Integer, ForeignKey("regions.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    bids       = relationship("Bid", back_populates="agency")


class Competitor(Base):
    __tablename__ = "competitors"
    id             = Column(Integer, primary_key=True)
    name           = Column(String(200), nullable=False)
    biz_reg_no     = Column(String(20), unique=True)
    region_id      = Column(Integer, ForeignKey("regions.id"))
    industry_codes = Column(ARRAY(Text))
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    results        = relationship("BidResult", back_populates="competitor")
    stats          = relationship("CompetitorStat", back_populates="competitor")


class Bid(Base):
    __tablename__ = "bids"
    id                  = Column(BigInteger, primary_key=True)
    announcement_no     = Column(String(60), unique=True, nullable=False)
    title               = Column(String(500), nullable=False)
    agency_id           = Column(Integer, ForeignKey("agencies.id"), nullable=False)
    industry_id         = Column(Integer, ForeignKey("industries.id"))
    region_id           = Column(Integer, ForeignKey("regions.id"))
    base_amount         = Column(BigInteger, nullable=False, default=0)
    estimated_price     = Column(BigInteger)
    a_value             = Column(BigInteger)
    min_bid_rate        = Column(Numeric(7, 4))
    notice_date         = Column(Date)
    bid_open_date       = Column(DateTime(timezone=True))
    construction_period = Column(Integer)
    region_restriction  = Column(Boolean, default=False)
    license_codes       = Column(ARRAY(Text))
    status              = Column(String(20), default="closed")
    source              = Column(String(20), default="api")
    ntce_url            = Column(String(500))
    # 신규 컬럼
    construction_site   = Column(String(500))
    contract_method     = Column(String(100))
    bid_method          = Column(String(100))
    eligible_regions    = Column(String(500))
    industry_limit      = Column(String(500))
    bid_close_date      = Column(DateTime(timezone=True))
    contact_name        = Column(String(100))
    contact_tel         = Column(String(50))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agency     = relationship("Agency", back_populates="bids")
    industry   = relationship("Industry")
    region     = relationship("Region")
    results    = relationship("BidResult", back_populates="bid", cascade="all,delete-orphan")
    features   = relationship("FeatureStore", back_populates="bid", uselist=False)


class BidResult(Base):
    __tablename__ = "bid_results"
    __table_args__ = (UniqueConstraint("bid_id", "competitor_id"),)
    id              = Column(BigInteger, primary_key=True)
    bid_id          = Column(BigInteger, ForeignKey("bids.id", ondelete="CASCADE"), nullable=False)
    competitor_id   = Column(Integer, ForeignKey("competitors.id"), nullable=False)
    bid_amount      = Column(BigInteger, nullable=False)
    bid_rate        = Column(Numeric(7, 4), nullable=False)
    rank            = Column(SmallInteger, nullable=False)
    is_winner       = Column(Boolean, default=False)
    assessment_rate = Column(Numeric(7, 4))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    bid        = relationship("Bid", back_populates="results")
    competitor = relationship("Competitor", back_populates="results")


class FeatureStore(Base):
    __tablename__ = "feature_store"
    id                        = Column(BigInteger, primary_key=True)
    bid_id                    = Column(BigInteger, ForeignKey("bids.id"), unique=True, nullable=False)
    agency_avg_rate_12m       = Column(Numeric(7, 4))
    agency_win_rate_12m       = Column(Numeric(5, 4))
    agency_bid_count_12m      = Column(Integer)
    region_avg_rate_12m       = Column(Numeric(7, 4))
    industry_avg_rate_12m     = Column(Numeric(7, 4))
    expected_competitor_count = Column(SmallInteger)
    competitor_strength_score = Column(Numeric(5, 2))
    season_index              = Column(SmallInteger)
    amount_log10              = Column(Numeric(10, 4))
    amount_bucket             = Column(SmallInteger)
    similar_bid_count         = Column(SmallInteger)
    similar_avg_rate          = Column(Numeric(7, 4))
    similar_std_rate          = Column(Numeric(7, 4))
    computed_at               = Column(DateTime(timezone=True), server_default=func.now())
    bid                       = relationship("Bid", back_populates="features")


class PredictionLog(Base):
    __tablename__ = "prediction_logs"
    id               = Column(BigInteger, primary_key=True)
    bid_id           = Column(BigInteger, ForeignKey("bids.id"))
    user_id          = Column(Integer)
    model_version    = Column(String(50))
    input_features   = Column(JSON)
    rate_safe_lower  = Column(Numeric(7, 4))
    rate_lower       = Column(Numeric(7, 4))
    rate_center      = Column(Numeric(7, 4))
    rate_upper       = Column(Numeric(7, 4))
    rate_safe_upper  = Column(Numeric(7, 4))
    win_prob_center  = Column(Numeric(5, 4))
    risk_level       = Column(String(10))
    shap_values      = Column(JSON)
    explanation_text = Column(Text)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True)
    email           = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    name            = Column(String(100))
    role            = Column(String(20), default="viewer")
    department      = Column(String(100))
    is_active       = Column(Boolean, default=True)
    last_login      = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class CompetitorStat(Base):
    __tablename__ = "competitor_stats"
    __table_args__ = (UniqueConstraint("competitor_id", "period_year", "period_month"),)
    id                = Column(BigInteger, primary_key=True)
    competitor_id     = Column(Integer, ForeignKey("competitors.id"), nullable=False)
    period_year       = Column(SmallInteger, nullable=False)
    period_month      = Column(SmallInteger)
    total_bid_count   = Column(Integer, default=0)
    win_count         = Column(Integer, default=0)
    win_rate          = Column(Numeric(5, 4))
    avg_bid_rate      = Column(Numeric(7, 4))
    std_bid_rate      = Column(Numeric(7, 4))
    aggression_score  = Column(Numeric(5, 2))
    consistency_score = Column(Numeric(5, 2))
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    competitor        = relationship("Competitor", back_populates="stats")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id          = Column(BigInteger, primary_key=True)
    user_id     = Column(Integer)
    action      = Column(String(50))
    entity_type = Column(String(50))
    entity_id   = Column(String(50))
    ip_address  = Column(String(50))
    detail      = Column(JSON)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class WatchKeyword(Base):
    __tablename__ = "watch_keywords"
    id         = Column(Integer, primary_key=True)
    keyword    = Column(String(200), nullable=False)
    kw_type    = Column(String(20), default="general")  # agency, title, general
    is_active  = Column(Boolean, default=True)
    user_id    = Column(Integer, ForeignKey("users.id"))
    note       = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AssessmentRateStat(Base):
    """사정율(예정가격/기초금액) 기관/공종/지역별 집계 통계"""
    __tablename__ = "assessment_rate_stats"
    __table_args__ = (
        UniqueConstraint(
            "group_type",
            "group_id_safe",
            "period_year",
            "period_month_safe",
        ),
    )
    id              = Column(BigInteger, primary_key=True)
    group_type      = Column(String(20),  nullable=False)   # agency/industry/region/global
    group_id        = Column(Integer)                        # NULL=global
    group_id_safe   = Column(Integer,     nullable=False, default=-1)  # -1 when NULL
    period_year     = Column(SmallInteger, nullable=False)
    period_month    = Column(SmallInteger)                   # NULL=연간 집계
    period_month_safe = Column(SmallInteger, nullable=False, default=-1)
    sample_count    = Column(Integer, nullable=False, default=0)
    srate_mean      = Column(Numeric(7, 4), nullable=False)
    srate_std       = Column(Numeric(7, 4))
    srate_p10       = Column(Numeric(7, 4))
    srate_p25       = Column(Numeric(7, 4))
    srate_p50       = Column(Numeric(7, 4))
    srate_p75       = Column(Numeric(7, 4))
    srate_p90       = Column(Numeric(7, 4))
    srate_trend     = Column(Numeric(10, 7), default=0.0)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now())


class MarketSnapshot(Base):
    """주간 시장 변동성 스냅샷 (Engine D 사전 계산 캐시)"""
    __tablename__ = "market_snapshots"
    __table_args__ = (UniqueConstraint("agency_id", "industry_id", "snapshot_date"),)
    id              = Column(BigInteger, primary_key=True)
    agency_id       = Column(Integer, ForeignKey("agencies.id"))
    industry_id     = Column(Integer, ForeignKey("industries.id"))
    snapshot_date   = Column(Date, nullable=False)
    srate_mean_4w   = Column(Numeric(7, 4))
    srate_std_4w    = Column(Numeric(7, 4))
    rate_mean_4w    = Column(Numeric(7, 4))
    volume_4w       = Column(Integer)
    srate_chg_pct   = Column(Numeric(10, 6))
    rate_chg_pct    = Column(Numeric(10, 6))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class PredictionLogV2(Base):
    """하이브리드 추천 v2 로그"""
    __tablename__ = "prediction_logs_v2"
    id                  = Column(BigInteger, primary_key=True)
    bid_id              = Column(BigInteger, ForeignKey("bids.id"))
    user_id             = Column(Integer)
    model_version       = Column(String(50))
    engine_weights      = Column(JSON)
    input_features      = Column(JSON)
    srate_pred_center   = Column(Numeric(7, 4))
    ep_confidence       = Column(Numeric(5, 3))
    rate_aggressive     = Column(Numeric(7, 4))
    rate_balanced       = Column(Numeric(7, 4))
    rate_conservative   = Column(Numeric(7, 4))
    rate_center         = Column(Numeric(7, 4))
    win_prob_center     = Column(Numeric(5, 4))
    risk_level          = Column(String(10))
    risk_score          = Column(Numeric(5, 2))
    competition_score   = Column(Numeric(5, 2))
    hhi_score           = Column(Numeric(5, 4))
    shap_values         = Column(JSON)
    explanation_text    = Column(Text)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())

class IndustryFilter(Base):
    """활성화할 공종 설정 — 빈 테이블 = 전체 허용."""
    __tablename__ = "industry_filters"
    id          = Column(Integer, primary_key=True)
    industry_id = Column(Integer, ForeignKey("industries.id"), unique=True, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    industry    = relationship("Industry")


class MyBidRecord(Base):
    """자사 투찰 이력 — 투찰률 추천 정확도 추적용"""
    __tablename__ = "my_bid_records"
    id                  = Column(BigInteger, primary_key=True)
    bid_id              = Column(BigInteger, ForeignKey("bids.id"), nullable=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    title               = Column(String(500), nullable=False)
    agency_name         = Column(String(200))
    bid_date            = Column(Date)
    base_amount         = Column(BigInteger, default=0)
    submitted_rate      = Column(Numeric(7, 4), nullable=False)
    recommendation_rate = Column(Numeric(7, 4))
    result              = Column(String(10), default="pending")  # pending/won/lost
    actual_winner_rate  = Column(Numeric(7, 4))
    note                = Column(Text)
    announcement_no     = Column(String(50),  nullable=True, index=True)
    floor_rate          = Column(Float,        nullable=True)
    a_value             = Column(BigInteger,   nullable=True)
    rate_diff           = Column(Float,        nullable=True)
    winner_biz_no       = Column(String(20),   nullable=True)
    winner_name         = Column(String(200),  nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CollectionLog(Base):
    __tablename__ = "collection_logs"
    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    collect_type  = Column(String(30), nullable=False)  # notice_cnstwk / notice_servc / notice_thng / result
    collected_at  = Column(DateTime(timezone=True), nullable=False)
    success_count = Column(Integer, default=0)
    fail_count    = Column(Integer, default=0)
    duration_sec  = Column(Numeric(8, 2))
    error_summary = Column(Text)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class BidBookmark(Base):
    __tablename__ = "bid_bookmarks"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bid_id     = Column(BigInteger, ForeignKey("bids.id", ondelete="CASCADE"), nullable=False)
    note       = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "bid_id"),)


class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    ntype      = Column(String(32), nullable=False)
    title      = Column(String(200), nullable=False)
    body       = Column(Text, nullable=True)
    link       = Column(String(500), nullable=True)
    is_read    = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BidParticipant(Base):
    """inpo21c_participants ORM 매핑 — 읽기 전용 (기존 테이블 참조, 마이그레이션 없음)."""
    __tablename__ = "inpo21c_participants"

    id              = Column(Integer, primary_key=True)
    inpo21c_bid_id  = Column(String(60), nullable=False, index=True)
    rank            = Column(Integer)
    biz_reg_no      = Column(String(20))
    company_name    = Column(String(200))
    bid_amount      = Column(BigInteger)
    bid_rate        = Column(Numeric(8, 6))
    base_ratio      = Column(Numeric(8, 6))
    assessment_rate = Column(Numeric(8, 6))
    is_winner       = Column(Boolean)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 수주율 최적화 시스템 — 신규 테이블 (8대 엔진 지원)
# ============================================================

class CompanyProfile(Base):
    """자사 프로파일 — 수주 역량 정의 (E1/E2/E7 엔진 기반 데이터)"""
    __tablename__ = "company_profile"

    id                   = Column(Integer, primary_key=True)
    company_name         = Column(String(200), nullable=False)
    biz_reg_no           = Column(String(20), unique=True)

    # 면허 및 등록
    license_codes        = Column(ARRAY(Text), default=[])
    region_codes         = Column(ARRAY(Text), default=[])

    # 재무/보증
    bond_limit_total     = Column(BigInteger, default=0)
    bond_limit_used      = Column(BigInteger, default=0)
    annual_revenue       = Column(BigInteger, default=0)

    # 공사 역량
    max_concurrent_bids  = Column(Integer, default=5)
    target_min_margin    = Column(Numeric(5, 4), default=0.05)
    target_regions       = Column(ARRAY(Text), default=[])
    target_industries    = Column(ARRAY(Integer), default=[])

    # 시공실적 (적격심사용) — {업종코드: [{amount, period, agency}]}
    performance_records  = Column(JSON, default={})
    workforce_count      = Column(Integer, default=0)

    # 월 수주 목표
    monthly_win_target   = Column(Integer, default=3)

    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class QualificationCheck(Base):
    """적격심사 체크 이력 (E2 엔진 출력 저장)"""
    __tablename__ = "qualification_checks"

    id               = Column(BigInteger, primary_key=True)
    bid_id           = Column(BigInteger, ForeignKey("bids.id"), nullable=False, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)

    our_share_rate   = Column(Numeric(5, 4), default=1.0)
    our_experience   = Column(BigInteger, default=0)

    pass_prob        = Column(Numeric(5, 4))
    min_pass_amount  = Column(BigInteger)
    max_pass_amount  = Column(BigInteger)
    score_breakdown  = Column(JSON, default={})
    verdict          = Column(String(20))   # PASS / FAIL / UNCERTAIN
    fail_reason      = Column(Text)

    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    bid  = relationship("Bid")
    user = relationship("User")


class BidDecision(Base):
    """공고 선별 의사결정 로그 (E1 엔진 출력 저장)"""
    __tablename__ = "bid_decisions"

    id                   = Column(BigInteger, primary_key=True)
    bid_id               = Column(BigInteger, ForeignKey("bids.id"), nullable=False, index=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=False)

    selection_score      = Column(Numeric(6, 4))
    ev_score             = Column(BigInteger)
    qualify_prob         = Column(Numeric(5, 4))
    win_prob_best        = Column(Numeric(5, 4))
    expected_margin      = Column(Numeric(5, 4))
    competitor_risk      = Column(String(10))   # LOW / MEDIUM / HIGH

    verdict              = Column(String(10), nullable=False)  # GO / NO_GO / WATCH
    no_go_reasons        = Column(ARRAY(Text), default=[])

    recommended_strategy = Column(String(20))
    recommended_rate     = Column(Numeric(7, 4))

    actual_action        = Column(String(10))   # BID / SKIP / PENDING
    actual_rate          = Column(Numeric(7, 4))

    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    bid  = relationship("Bid")
    user = relationship("User")


class ActualBidOutcome(Base):
    """실제 투찰 결과 — 피드백 루프 핵심 데이터 (E6 엔진 입력)"""
    __tablename__ = "actual_bid_outcomes"

    id                  = Column(BigInteger, primary_key=True)
    bid_decision_id     = Column(BigInteger, ForeignKey("bid_decisions.id"), nullable=True)
    bid_id              = Column(BigInteger, ForeignKey("bids.id"), nullable=False, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)

    submitted_rate      = Column(Numeric(7, 4), nullable=False)
    result              = Column(String(15), nullable=False)   # WON / LOST / DISQUALIFIED
    disqualify_reason   = Column(Text)

    actual_srate        = Column(Numeric(7, 4))
    winner_rate         = Column(Numeric(7, 4))
    winner_biz_no       = Column(String(20))
    our_rank            = Column(SmallInteger)
    total_bidders       = Column(SmallInteger)

    predicted_win_prob  = Column(Numeric(5, 4))
    predicted_srate     = Column(Numeric(7, 4))
    srate_error         = Column(Numeric(7, 4))

    collected_at        = Column(DateTime(timezone=True))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())

    bid          = relationship("Bid")
    user         = relationship("User")
    bid_decision = relationship("BidDecision")


class PortfolioState(Base):
    """현재 진행중 입찰 포트폴리오 상태 (E7 엔진 제약 입력)"""
    __tablename__ = "portfolio_state"
    __table_args__ = (UniqueConstraint("user_id", "bid_id"),)

    id               = Column(Integer, primary_key=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    bid_id           = Column(BigInteger, ForeignKey("bids.id"), nullable=False)

    status           = Column(String(20), default="ACTIVE")  # ACTIVE / CLOSED / WON / LOST
    submitted_rate   = Column(Numeric(7, 4))
    submitted_amount = Column(BigInteger)
    bond_exposure    = Column(BigInteger, default=0)
    bid_date         = Column(Date)
    result_date      = Column(Date)

    bid  = relationship("Bid")
    user = relationship("User")


class KpiSnapshot(Base):
    """수주율 KPI 일별/주별/월별 스냅샷 (E8 경영진 대시보드 기반)"""
    __tablename__ = "kpi_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_date", "user_id", "period_type"),)

    id                    = Column(BigInteger, primary_key=True)
    snapshot_date         = Column(Date, nullable=False)
    user_id               = Column(Integer, ForeignKey("users.id"), nullable=True)
    period_type           = Column(String(10), nullable=False)  # DAILY / WEEKLY / MONTHLY

    total_bids            = Column(Integer, default=0)
    total_wins            = Column(Integer, default=0)
    win_rate              = Column(Numeric(5, 4))
    total_bid_amount      = Column(BigInteger, default=0)
    total_won_amount      = Column(BigInteger, default=0)
    total_expected_profit = Column(BigInteger, default=0)

    qualify_pass_rate     = Column(Numeric(5, 4))
    avg_rank_at_loss      = Column(Numeric(5, 2))
    srate_mae             = Column(Numeric(7, 4))
    win_prob_calibration  = Column(Numeric(5, 4))

    go_rate               = Column(Numeric(5, 4))
    go_win_rate           = Column(Numeric(5, 4))
    no_go_saved           = Column(Integer, default=0)

    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


class ModelPerformanceLog(Base):
    """ML 모델 성능 추적 — 수주율 기여도 측정 (E6 피드백 출력)"""
    __tablename__ = "model_performance_log"

    id                      = Column(BigInteger, primary_key=True)
    model_name              = Column(String(50), nullable=False)
    model_version           = Column(String(50))
    eval_date               = Column(Date, nullable=False)

    sample_count            = Column(Integer)
    mae                     = Column(Numeric(8, 6))
    rmse                    = Column(Numeric(8, 6))
    calibration_ece         = Column(Numeric(8, 6))

    win_rate_with_model     = Column(Numeric(5, 4))
    win_rate_without_model  = Column(Numeric(5, 4))
    lift                    = Column(Numeric(5, 4))

    created_at              = Column(DateTime(timezone=True), server_default=func.now())


class CompetitorStrategyPattern(Base):
    """경쟁사 전략 패턴 — 기관/공종/금액대별 세분화 (E4 엔진 강화)"""
    __tablename__ = "competitor_strategy_patterns"
    __table_args__ = (UniqueConstraint("competitor_id", "agency_id", "industry_id", "amount_bucket"),)

    id                 = Column(BigInteger, primary_key=True)
    competitor_id      = Column(Integer, ForeignKey("competitors.id"), nullable=False)
    agency_id          = Column(Integer, ForeignKey("agencies.id"), nullable=True)
    industry_id        = Column(Integer, ForeignKey("industries.id"), nullable=True)
    amount_bucket      = Column(SmallInteger, nullable=False, default=0)

    bid_rate_p10       = Column(Numeric(7, 4))
    bid_rate_p25       = Column(Numeric(7, 4))
    bid_rate_p50       = Column(Numeric(7, 4))
    bid_rate_p75       = Column(Numeric(7, 4))
    bid_rate_p90       = Column(Numeric(7, 4))
    participation_rate = Column(Numeric(5, 4))
    win_rate           = Column(Numeric(5, 4))

    sample_count       = Column(Integer, default=0)
    updated_at         = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    competitor = relationship("Competitor")
    agency     = relationship("Agency")
    industry   = relationship("Industry")


class BidSelectionFeature(Base):
    """공고 선별 피처 캐시 (E1 엔진 전용 사전 계산 결과)"""
    __tablename__ = "bid_selection_features"

    bid_id                  = Column(BigInteger, ForeignKey("bids.id"), primary_key=True)
    historical_win_rate     = Column(Numeric(5, 4))
    avg_competitor_count    = Column(Numeric(5, 2))
    strong_competitor_count = Column(SmallInteger, default=0)
    qualify_prob            = Column(Numeric(5, 4))
    license_match           = Column(Boolean, default=False)
    region_match            = Column(Boolean, default=False)
    estimated_margin        = Column(Numeric(5, 4))
    ev_score                = Column(BigInteger, default=0)
    in_target_region        = Column(Boolean, default=False)
    in_target_industry      = Column(Boolean, default=False)
    computed_at             = Column(DateTime(timezone=True), server_default=func.now())

    bid = relationship("Bid")


# ============================================================
# 수주율 최적화 운영체계 — Phase 1 신규 테이블
# ============================================================

class BidExecution(Base):
    """투찰 수명주기 관리 — 검토→결정→투찰→개찰→결과 전 단계 추적"""
    __tablename__ = "bid_executions"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    bid_id           = Column(BigInteger, ForeignKey("bids.id"), nullable=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 공고 기본 정보 (bid_id 없는 외부 공고 대비)
    announcement_no  = Column(String(60), index=True)
    title            = Column(String(500), nullable=False)
    agency_name      = Column(String(200))
    industry_name    = Column(String(100))
    base_amount      = Column(BigInteger, default=0)
    bid_open_date    = Column(DateTime(timezone=True))

    # 투찰 상태 (6단계)
    status           = Column(String(20), nullable=False, default="검토중")
    # 검토중 | 참여결정 | 투찰완료 | 개찰대기 | 낙찰 | 패찰 | 포기

    # 결정 정보
    decision_reason  = Column(Text)          # 참여/포기 결정 사유
    decided_at       = Column(DateTime(timezone=True))

    # 투찰 정보
    submitted_rate   = Column(Numeric(8, 6))  # 실제 투찰률
    submitted_amount = Column(BigInteger)      # 실제 투찰금액
    floor_rate       = Column(Numeric(8, 6))   # 낙찰하한율
    a_value          = Column(BigInteger)      # A값
    recommended_rate = Column(Numeric(8, 6))   # 시스템 추천 투찰률
    submitted_at     = Column(DateTime(timezone=True))

    # 개찰 결과
    result_rank      = Column(Integer)         # 최종 순위
    total_bidders    = Column(Integer)         # 총 참여 업체 수
    winner_rate      = Column(Numeric(8, 6))   # 1순위 낙찰률
    winner_amount    = Column(BigInteger)      # 1순위 낙찰금액
    winner_name      = Column(String(200))     # 1순위 업체명
    winner_biz_no    = Column(String(20))      # 1순위 사업자번호
    winner_gap       = Column(Numeric(8, 6))   # 낙찰률 - 우리 투찰률 (음수=우리가 높게 씀)
    opened_at        = Column(DateTime(timezone=True))

    # SUCVIEW 원본 데이터
    sucview_raw      = Column(JSON)            # 원본 참여업체 리스트

    note             = Column(Text)
    source           = Column(String(20), default="manual")  # manual | excel_import
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    bid  = relationship("Bid")
    user = relationship("User")
    defeat_analysis = relationship("DefeatAnalysis", back_populates="execution", uselist=False)


class DefeatAnalysis(Base):
    """패찰 원인 자동 분류 — 개찰 결과 입력 시 자동 생성"""
    __tablename__ = "defeat_analyses"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    execution_id    = Column(BigInteger, ForeignKey("bid_executions.id"), nullable=False, unique=True)

    # 원인 분류 (복수 가능)
    cause_primary   = Column(String(30), nullable=False)
    # 투찰률과도 | 경쟁사과다 | 적격부족 | 시장변동 | 정보부족 | 기타
    cause_secondary = Column(String(30))
    cause_detail    = Column(Text)

    # 수치 근거
    winner_gap_pct  = Column(Numeric(6, 3))   # 낙찰자 대비 차이(%) — 양수=우리가 더 높음
    competitor_cnt  = Column(Integer)
    our_rank        = Column(Integer)
    floor_rate      = Column(Numeric(8, 6))

    # 개선 방향
    improvement     = Column(Text)            # "다음 유사 공고에서 -X% 하향 추천"
    next_rate_adj   = Column(Numeric(6, 4))   # 추천 보정값 (예: -0.012)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    execution = relationship("BidExecution", back_populates="defeat_analysis")


class AgencyStrategy(Base):
    """발주기관 전략 DB — 48개월 집계, 빈도표, 공격성 지수"""
    __tablename__ = "agency_strategies"
    __table_args__ = (UniqueConstraint("agency_id", "industry_code", "period_months"),)

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)
    agency_id            = Column(Integer, ForeignKey("agencies.id"), nullable=False)
    industry_code        = Column(String(50), default="ALL")
    period_months        = Column(Integer, default=48)

    # 낙찰률 통계
    total_bid_count      = Column(Integer, default=0)
    avg_win_rate         = Column(Numeric(8, 6))
    std_win_rate         = Column(Numeric(8, 6))
    min_win_rate         = Column(Numeric(8, 6))
    max_win_rate         = Column(Numeric(8, 6))
    win_rate_p10         = Column(Numeric(8, 6))
    win_rate_p25         = Column(Numeric(8, 6))
    win_rate_p50         = Column(Numeric(8, 6))
    win_rate_p75         = Column(Numeric(8, 6))
    win_rate_p90         = Column(Numeric(8, 6))

    # 경쟁 통계
    avg_competitor_cnt   = Column(Numeric(6, 2))
    aggression_index     = Column(Numeric(5, 3))   # 하한율 이하 투찰 비율
    qual_difficulty      = Column(String(10))       # 易/中/難

    # 빈도표 JSON: [{"from": 0.87, "to": 0.875, "count": 12, "win_count": 3}]
    freq_table           = Column(JSON, default=[])
    # 히스토그램: [[rate, count], ...]
    histogram_data       = Column(JSON, default=[])

    # 최근 변동성
    volatility_30d       = Column(Numeric(5, 3))
    trend_direction      = Column(String(10))       # up | down | stable

    # 추천 구간
    recommended_range_lo = Column(Numeric(8, 6))
    recommended_range_hi = Column(Numeric(8, 6))

    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agency = relationship("Agency")


class RateFrequencyTable(Base):
    """낙찰률 구간별 빈도표 — info21c 수준 통계 (기관×업종×기간)"""
    __tablename__ = "rate_frequency_tables"
    __table_args__ = (UniqueConstraint("agency_id", "industry_code", "period_type", "bucket_from"),)

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    agency_id     = Column(Integer, ForeignKey("agencies.id"), nullable=False)
    industry_code = Column(String(50), default="ALL")
    period_type   = Column(String(10), nullable=False)   # 6M | 12M | 24M | 48M
    bucket_from   = Column(Numeric(8, 6), nullable=False)
    bucket_to     = Column(Numeric(8, 6), nullable=False)
    bucket_width  = Column(Numeric(6, 4), default=0.005)

    count         = Column(Integer, default=0)
    win_count     = Column(Integer, default=0)
    win_rate      = Column(Numeric(5, 3))           # 이 구간의 낙찰률(%)

    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agency = relationship("Agency")


class OurCompetitor(Base):
    """자사 전용 경쟁사 추적 — 우리 회사가 자주 만나는 상위 경쟁사"""
    __tablename__ = "our_competitors"
    __table_args__ = (UniqueConstraint("competitor_id"),)

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)
    competitor_id        = Column(Integer, ForeignKey("competitors.id"), nullable=True)

    # 기본 정보 (competitors 테이블에 없는 경우 직접 저장)
    company_name         = Column(String(200), nullable=False)
    biz_reg_no           = Column(String(20))

    # 동반 출현 통계
    co_participation_cnt = Column(Integer, default=0)   # 같이 참여한 건수
    co_win_cnt           = Column(Integer, default=0)   # 상대가 이긴 건수 (우리 vs 상대)
    our_win_when_meet    = Column(Integer, default=0)   # 우리가 이긴 건수 (상대 만났을 때)

    # 투찰 패턴
    avg_bid_rate         = Column(Numeric(8, 6))        # 평균 투찰률
    std_bid_rate         = Column(Numeric(8, 6))
    avg_rate_vs_us       = Column(Numeric(8, 6))        # 우리 대비 평균 (음수=우리보다 낮게)
    aggression           = Column(Numeric(5, 3))        # 공격성 0-1

    # 최근 활동
    last_seen_at         = Column(Date)
    last_seen_agency     = Column(String(200))
    is_primary_rival     = Column(Boolean, default=False)

    # SUCVIEW 데이터로 자동 생성된 경우
    source               = Column(String(20), default="sucview")

    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    competitor = relationship("Competitor")

