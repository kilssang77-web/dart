"""회사 프로파일 API — 수주 역량 정의 (E1/E2/E7 기반 데이터)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import CompanyProfileRequest, CompanyProfileResponse
from ...services import CompanyProfileService
from .auth import get_current_user

router = APIRouter(prefix="/company", tags=["회사 프로파일"])
_svc = CompanyProfileService()


def _profile_dict(profile, bond: dict) -> dict:
    caps = profile.construction_capabilities or []
    if caps and isinstance(caps[0], dict):
        pass  # already list of dicts
    return {
        "id":                           profile.id,
        # 기본정보
        "company_name":                 profile.company_name,
        "biz_reg_no":                   profile.biz_reg_no,
        "phone":                        profile.phone,
        "address":                      profile.address,
        "ceo_name":                     profile.ceo_name,
        "is_women_company":             profile.is_women_company or False,
        # 경영상태
        "credit_grade":                 profile.credit_grade,
        "credit_valid_date":            str(profile.credit_valid_date) if profile.credit_valid_date else None,
        "ppsq_rating":                  float(profile.ppsq_rating) if profile.ppsq_rating is not None else None,
        "moi_rating":                   float(profile.moi_rating) if profile.moi_rating is not None else None,
        "debt_ratio":                   float(profile.debt_ratio) if profile.debt_ratio is not None else None,
        "total_debt":                   profile.total_debt,
        "equity":                       profile.equity,
        "current_ratio":                float(profile.current_ratio) if profile.current_ratio is not None else None,
        "current_assets":               profile.current_assets,
        "current_liabilities":          profile.current_liabilities,
        "region":                       profile.region,
        "general_operation_period":     profile.general_operation_period,
        "specialty_operation_period":   profile.specialty_operation_period,
        "disclosure_year":              profile.disclosure_year,
        # 시공능력
        "construction_capabilities":    caps,
        # 면허/등록
        "license_codes":                profile.license_codes or [],
        "region_codes":                 profile.region_codes or [],
        # 재무/보증
        "bond_limit_total":             profile.bond_limit_total or 0,
        "bond_limit_used":              bond["used"],
        "annual_revenue":               profile.annual_revenue or 0,
        # 수주 목표
        "max_concurrent_bids":          profile.max_concurrent_bids,
        "target_min_margin":            float(profile.target_min_margin or 0.05),
        "target_regions":               profile.target_regions or [],
        "target_industries":            profile.target_industries or [],
        # 공사 역량
        "performance_records":          profile.performance_records or {},
        "workforce_count":              profile.workforce_count or 0,
        "monthly_win_target":           profile.monthly_win_target or 3,
        # 계산값
        "bond_usage_rate":              bond["usage_rate"],
        "remaining_bond":               bond["remaining"],
        "updated_at":                   profile.updated_at,
    }


@router.get("/profile", response_model=CompanyProfileResponse)
def get_profile(db: Session = Depends(get_db), user=Depends(get_current_user)):
    profile = _svc.get_profile(db, user.id)
    if not profile:
        raise HTTPException(404, "회사 프로파일이 아직 설정되지 않았습니다")
    bond = _svc.get_remaining_bond(db)
    return _profile_dict(profile, bond)


@router.put("/profile", response_model=CompanyProfileResponse)
def upsert_profile(
    body: CompanyProfileRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    data = body.model_dump()
    # construction_capabilities: Pydantic 모델 → dict 변환
    data["construction_capabilities"] = [
        c if isinstance(c, dict) else c.model_dump()
        for c in data.get("construction_capabilities", [])
    ]
    profile = _svc.upsert_profile(db, data)
    bond = _svc.get_remaining_bond(db)
    return _profile_dict(profile, bond)


@router.get("/bond-status")
def get_bond_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _svc.get_remaining_bond(db)
