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

