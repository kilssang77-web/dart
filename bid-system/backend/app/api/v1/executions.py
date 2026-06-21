"""
투찰 실행 관리 API
- 6단계 수명주기: 검토중→참여결정→투찰완료→개찰대기→낙찰/패찰/포기
- SUCVIEW 엑셀 업로드 파싱
- 패찰 원인 자동 분류
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import io

from ...database import get_db
from ...services import ExecutionService
from ...schemas import (
    BidExecutionCreate, BidExecutionUpdate, BidExecutionOut,
    DefeatAnalysisOut, SucviewImportResult,
)
from ...common.security import get_current_user
from ...models import User

router = APIRouter(prefix="/executions", tags=["executions"])


# ── 목록 / 요약 (static paths first) ────────────────────────

@router.get("", response_model=dict)
def list_executions(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """투찰 실행 목록 (상태별 필터)"""
    svc = ExecutionService(db)
    return svc.list_executions(user_id=current_user.id, status=status, page=page, size=size)


@router.get("/summary", response_model=dict)
def execution_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """상태별 건수 요약 + 오늘 마감 공고"""
    svc = ExecutionService(db)
    return svc.get_summary(user_id=current_user.id)


@router.get("/defeat-summary", response_model=dict)
def defeat_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """패찰 원인 집계 분석 — 원인별 건수/비율/평균 gap"""
    svc = ExecutionService(db)
    return svc.defeat_summary(user_id=current_user.id)


# ── 발주기관 빈도표 (static path — must be before /{exec_id}) ──

@router.get("/agency-freq/{agency_id}", response_model=dict)
def agency_frequency(
    agency_id: int,
    industry_code: str = "ALL",
    period: str = Query("48M", regex="^(6M|12M|24M|48M)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """발주기관 낙찰률 빈도표 조회"""
    from ...services import FrequencyService
    svc = FrequencyService(db)
    return svc.get_agency_freq(agency_id=agency_id, industry_code=industry_code, period=period)


@router.post("/agency-freq/rebuild")
def rebuild_freq_tables(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """발주기관 빈도표 전체 재생성 (bid_results 45,849건 활용)"""
    if current_user.role not in ("admin", "analyst"):
        raise HTTPException(403, "권한 없음")
    from ...services import FrequencyService
    svc = FrequencyService(db)
    result = svc.rebuild_all()
    return result


# ── 자사 경쟁사 (static path — must be before /{exec_id}) ─────

@router.get("/our-competitors", response_model=List[dict])
def our_competitors(
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """자사 전용 경쟁사 목록 (동반 출현 빈도순)"""
    from ...services import OurCompetitorService
    svc = OurCompetitorService(db)
    return svc.list_competitors(limit=limit)


# ── 엑셀 업로드 (static path — must be before /{exec_id}) ─────

@router.post("/import/sucview", response_model=SucviewImportResult)
async def import_sucview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SUCVIEW 엑셀 파일 업로드 → bid_executions + our_competitors 자동 생성"""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "xlsx/xls 파일만 지원합니다")
    content = await file.read()
    svc = ExecutionService(db)
    return svc.import_sucview(file_bytes=content, user_id=current_user.id)


@router.post("/import/inpo-history", response_model=SucviewImportResult)
async def import_inpo_history(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """인포나의투찰성향목록 엑셀 → my_bid_records + bid_executions 연동"""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "xlsx/xls 파일만 지원합니다")
    content = await file.read()
    svc = ExecutionService(db)
    return svc.import_inpo_history(file_bytes=content, user_id=current_user.id)


# ── CRUD (dynamic /{exec_id} routes LAST) ────────────────────

@router.post("", response_model=BidExecutionOut)
def create_execution(
    body: BidExecutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """투찰 실행 등록 (검토중으로 시작)"""
    svc = ExecutionService(db)
    return svc.create(user_id=current_user.id, data=body)


@router.get("/{exec_id}", response_model=BidExecutionOut)
def get_execution(
    exec_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ExecutionService(db)
    obj = svc.get(exec_id)
    if not obj:
        raise HTTPException(404, "Not found")
    return obj


@router.patch("/{exec_id}", response_model=BidExecutionOut)
def update_execution(
    exec_id: int,
    body: BidExecutionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """상태 변경 + 투찰금액/결과 입력"""
    svc = ExecutionService(db)
    return svc.update(exec_id=exec_id, user_id=current_user.id, data=body)


@router.delete("/{exec_id}")
def delete_execution(
    exec_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ExecutionService(db)
    svc.delete(exec_id, current_user.id)
    return {"success": True}


@router.get("/{exec_id}/defeat-analysis", response_model=Optional[DefeatAnalysisOut])
def get_defeat_analysis(
    exec_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """패찰 원인 분석 조회"""
    svc = ExecutionService(db)
    return svc.get_defeat_analysis(exec_id)
