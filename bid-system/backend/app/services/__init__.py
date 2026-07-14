"""
services 패키지 — 비즈니스 로직 서비스 레이어.

기존 `from .services import XyzService` 임포트가 모두 동작하도록
모든 공개 서비스 클래스를 여기서 재-익스포트한다.
"""

# ── 입찰 ──────────────────────────────────────────────────────────
from .bid import BidService

# ── 추천 ──────────────────────────────────────────────────────────
from .recommend import (
    RecommendationService,
    HybridRecommendService,
    SingleRecommendService,
    BidSelectionService,
    FinalRecommendService,
    ActualOutcomeService,
)

# ── 통계 ──────────────────────────────────────────────────────────
from .statistics import (
    StatisticsService,
    SrateTrendService,
    KpiService,
    PortfolioService,
    BacktestService,
)

# ── 경쟁사 ────────────────────────────────────────────────────────
from .competitor import (
    CompetitorService,
    CompetitorPatternService,
    CompetitorZoneService,
    CompetitorPredictService,
    OurCompetitorService,
    RivalRadarService,
)

# ── 기관 분석 ─────────────────────────────────────────────────────
from .agency import (
    AgencyAnalysisService,
    CompanyProfileService,
    QualificationService,
    AgencyYegaService,
    JointQualService,
    JointSimulateService,
)

# ── ML 추론 래퍼 ──────────────────────────────────────────────────
from .ml_svc import (
    OpportunityScoreService,
    WinPatternService,
    ActualWinZoneService,
    PrismScanService,
    YegaFrequencyService,
    HotZoneService,
    BestRateService,
    FrequencyService,
    AgencyStrategyService,
    MarketIntelService,
)

# ── 투찰이력 ──────────────────────────────────────────────────────
from .user_bids import (
    MyBidFeedbackService,
    MyBidImportService,
    MyBidAnalysisService,
    DefeatAnalysisService,
)

# ── 투찰 실행 ─────────────────────────────────────────────────────
from .execution import ExecutionService

# ── 어드민 ────────────────────────────────────────────────────────
from .admin import (
    AdminService,
    G2BSyncService,
    InpoNoticesSyncService,
    InpoParticipantService,
    SekihaiService,
)

# ── 알림 ──────────────────────────────────────────────────────────
from .notifications import NotificationService

# ── 북마크 ────────────────────────────────────────────────────────
from .bookmarks import BookmarkService

# ── 공통 헬퍼 (하위 호환용 재-익스포트) ──────────────────────────
from ._common import get_active_industry_ids, _build_ind_sql, _compute_yega_ml_features

# ── 외부 서비스 모듈 재-익스포트 (기존 services.py 호환) ─────────
from ..decision_service import DecisionService  # noqa: F401
from ..journal_service  import JournalService   # noqa: F401

__all__ = [
    # bid
    "BidService",
    # recommend
    "RecommendationService",
    "HybridRecommendService",
    "SingleRecommendService",
    "BidSelectionService",
    "FinalRecommendService",
    "ActualOutcomeService",
    # statistics
    "StatisticsService",
    "SrateTrendService",
    "KpiService",
    "PortfolioService",
    "BacktestService",
    # competitor
    "CompetitorService",
    "CompetitorPatternService",
    "CompetitorZoneService",
    "CompetitorPredictService",
    "OurCompetitorService",
    "RivalRadarService",
    # agency
    "AgencyAnalysisService",
    "CompanyProfileService",
    "QualificationService",
    "AgencyYegaService",
    "JointQualService",
    "JointSimulateService",
    # ml_svc
    "OpportunityScoreService",
    "WinPatternService",
    "ActualWinZoneService",
    "PrismScanService",
    "YegaFrequencyService",
    "HotZoneService",
    "BestRateService",
    "FrequencyService",
    "AgencyStrategyService",
    "MarketIntelService",
    # user_bids
    "MyBidFeedbackService",
    "MyBidImportService",
    "MyBidAnalysisService",
    "DefeatAnalysisService",
    # execution
    "ExecutionService",
    # admin
    "AdminService",
    "G2BSyncService",
    "InpoNoticesSyncService",
    "InpoParticipantService",
    "SekihaiService",
    # notifications
    "NotificationService",
    # bookmarks
    "BookmarkService",
    # helpers
    "get_active_industry_ids",
    "_build_ind_sql",
    "_compute_yega_ml_features",
    # external
    "DecisionService",
    "JournalService",
]
