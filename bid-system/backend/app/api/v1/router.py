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