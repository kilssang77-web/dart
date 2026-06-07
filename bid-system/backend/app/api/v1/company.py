"""회사 프로파일 API — 수주 역량 정의 (E1/E2/E7 기반 데이터)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import CompanyProfileRequest, CompanyProfileResponse
from ...services import CompanyProfileService
from .auth import get_current_user

router = APIRouter(prefix="/company", tags=["회사 프로파일"])
_svc = CompanyProfileService()


@router.get("/profile", response_model=CompanyProfileResponse)
def get_profile(db: Session = Depends(get_db), user=Depends(get_current_user)):
    profile = _svc.get_profile(db, user.id)
    if not profile:
        raise HTTPException(404, "회사 프로파일이 아직 설정되지 않았습니다")
    bond = _svc.get_remaining_bond(db)
    data = {
        "id":                  profile.id,
        "company_name":        profile.company_name,
        "biz_reg_no":          profile.biz_reg_no,
        "license_codes":       profile.license_codes or [],
        "region_codes":        profile.region_codes or [],
        "bond_limit_total":    profile.bond_limit_total or 0,
        "bond_limit_used":     bond["used"],
        "annual_revenue":      profile.annual_revenue or 0,
        "max_concurrent_bids": profile.max_concurrent_bids,
        "target_min_margin":   float(profile.target_min_margin or 0.05),
        "target_regions":      profile.target_regions or [],
        "target_industries":   profile.target_industries or [],
        "performance_records": profile.performance_records or {},
        "workforce_count":     profile.workforce_count or 0,
        "monthly_win_target":  profile.monthly_win_target or 3,
        "bond_usage_rate":     bond["usage_rate"],
        "remaining_bond":      bond["remaining"],
        "updated_at":          profile.updated_at,
    }
    return data


@router.put("/profile", response_model=CompanyProfileResponse)
def upsert_profile(
    body: CompanyProfileRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    profile = _svc.upsert_profile(db, body.model_dump())
    bond    = _svc.get_remaining_bond(db)
    return {
        "id":                  profile.id,
        "company_name":        profile.company_name,
        "biz_reg_no":          profile.biz_reg_no,
        "license_codes":       profile.license_codes or [],
        "region_codes":        profile.region_codes or [],
        "bond_limit_total":    profile.bond_limit_total or 0,
        "bond_limit_used":     bond["used"],
        "annual_revenue":      profile.annual_revenue or 0,
        "max_concurrent_bids": profile.max_concurrent_bids,
        "target_min_margin":   float(profile.target_min_margin or 0.05),
        "target_regions":      profile.target_regions or [],
        "target_industries":   profile.target_industries or [],
        "performance_records": profile.performance_records or {},
        "workforce_count":     profile.workforce_count or 0,
        "monthly_win_target":  profile.monthly_win_target or 3,
        "bond_usage_rate":     bond["usage_rate"],
        "remaining_bond":      bond["remaining"],
        "updated_at":          profile.updated_at,
    }


@router.get("/bond-status")
def get_bond_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _svc.get_remaining_bond(db)
