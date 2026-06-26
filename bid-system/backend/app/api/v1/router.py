from fastapi import APIRouter
from .auth import router as auth_router
from .bids import router as bids_router
from .recommend import router as recommend_router
from .competitors import router as competitors_router
from .statistics import router as statistics_router
from .keywords import router as keywords_router
from .admin import router as admin_router
from .my_bids import router as my_bids_router
from .agencies import router as agencies_router
from .notifications import router as notifications_router
from .market_intel import router as market_intel_router
# 수주율 최적화 시스템 — 신규 라우터
from .company   import router as company_router
from .selection import router as selection_router
from .strategy  import router as strategy_router
from .outcomes  import router as outcomes_router
from .kpi       import router as kpi_router
from .portfolio import router as portfolio_router
from .executions import router as executions_router
from .backtest   import router as backtest_router
from .decision   import router as decision_router
from .journal    import router as journal_router
# Phase 2/3 — 사전규격·계약정보
from .pre_spec   import router as pre_spec_router
from .contracts  import router as contracts_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(bids_router)
api_router.include_router(recommend_router)
api_router.include_router(competitors_router)
api_router.include_router(statistics_router)
api_router.include_router(keywords_router)
api_router.include_router(admin_router)
api_router.include_router(my_bids_router)
api_router.include_router(agencies_router)
api_router.include_router(notifications_router)
api_router.include_router(market_intel_router)
# 수주율 최적화 시스템
api_router.include_router(company_router)
api_router.include_router(selection_router)
api_router.include_router(strategy_router)
api_router.include_router(outcomes_router)
api_router.include_router(kpi_router)
api_router.include_router(portfolio_router)
api_router.include_router(executions_router)
api_router.include_router(backtest_router)
api_router.include_router(decision_router)
api_router.include_router(journal_router)
api_router.include_router(pre_spec_router)
api_router.include_router(contracts_router)