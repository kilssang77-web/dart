"""
데모 데이터 시더 — 상용 AI 없이 시스템 즉시 체험 가능.
실제 통계 범위에 부합하는 현실적인 입찰 데이터 생성.
"""
import random
import logging
import math
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import Bid, BidResult, Competitor, Agency, Industry, Region, User
from .common.security import hash_password

logger = logging.getLogger(__name__)

random.seed(42)

COMPANY_NAMES = [
    "현대건설", "삼성물산건설", "GS건설", "대우건설", "포스코건설",
    "롯데건설", "SK에코플랜트", "한화건설", "HDC현대산업개발", "코오롱글로벌",
    "한라", "계룡건설", "태영건설", "서희건설", "금호건설",
    "동부건설", "신세계건설", "반도건설", "두산건설", "KCC건설",
    "호반건설", "우미건설", "대방건설", "제일건설", "한신공영",
    "보성그룹", "남광토건", "협성건설", "아이에스동서", "중흥건설",
    "한국종합기술", "코리아엔지니어링", "동양건설산업", "유창", "시티건설",
    "벽산건설", "신동아건설", "경남기업", "극동건설", "성원건설",
]


def seed_all(db: Session):
    if db.query(Bid).count() > 10:
        logger.info("데모 데이터 이미 존재 — 시더 건너뜀")
        return

    logger.info("데모 데이터 생성 시작...")
    _seed_competitors(db)
    _seed_bids(db)
    _seed_admin(db)
    _train_initial_model(db)
    logger.info("데모 데이터 생성 완료")


def _seed_competitors(db: Session):
    for name in COMPANY_NAMES:
        existing = db.query(Competitor).filter(Competitor.name == name).first()
        if not existing:
            db.add(Competitor(name=name))
    db.commit()


def _seed_bids(db: Session):
    agencies   = db.query(Agency).all()
    industries = db.query(Industry).all()
    regions    = db.query(Region).all()
    comps      = db.query(Competitor).all()

    if not agencies or not industries or not regions:
        logger.warning("기준 데이터 없음 — 시더 중단")
        return

    base_date = datetime.now() - timedelta(days=730)
    bid_count = 0

    for day_offset in range(0, 720, 3):
        bid_date = base_date + timedelta(days=day_offset)
        n_today = random.randint(1, 4)

        for _ in range(n_today):
            agency   = random.choice(agencies)
            industry = random.choice(industries)
            region   = random.choice(regions)

            amount_million = random.choice([
                random.randint(100, 500),
                random.randint(500, 2000),
                random.randint(2000, 10000),
            ])
            base_amount = amount_million * 1_000_000

            # 기관/공종별 고유 낙찰 패턴 시뮬레이션
            base_rate = _typical_rate(agency.id, industry.id, region.id)

            bid = Bid(
                announcement_no=f"2{bid_date.strftime('%Y%m%d')}{bid_count:05d}",
                title=_generate_title(industry.name, region.name, agency.name),
                agency_id=agency.id,
                industry_id=industry.id,
                region_id=region.id,
                base_amount=base_amount,
                min_bid_rate=0.8775,
                a_value=int(base_amount * 0.97),
                bid_open_date=bid_date,
                construction_period=random.randint(90, 720),
                region_restriction=random.random() < 0.3,
                status="closed",
                source="seed",
            )
            db.add(bid)
            db.flush()

            _add_results(db, bid, comps, base_rate)
            bid_count += 1

    db.commit()
    logger.info(f"입찰 {bid_count}건 생성 완료")


def _typical_rate(agency_id: int, industry_id: int, region_id: int) -> float:
    """기관/공종/지역 조합별 특성 반영."""
    base = 0.8793
    base += (agency_id % 5) * 0.0008
    base += (industry_id % 3) * 0.0005
    base += (region_id % 4) * 0.0004
    return round(base, 4)


def _generate_title(industry: str, region: str, agency: str) -> str:
    suffixes = ["조성공사", "신축공사", "설치공사", "개선공사", "보수공사",
                "확장공사", "정비공사", "개량공사", "건설공사", "정비사업"]
    prefixes = ["", "1단계 ", "2단계 ", "2024년도 ", "긴급 ", "추가 "]
    return f"{random.choice(prefixes)}{region} {industry} {random.choice(suffixes)}"


def _add_results(db: Session, bid: Bid, all_comps: list, base_rate: float):
    n_comps = random.randint(5, 25)
    participants = random.sample(all_comps, min(n_comps, len(all_comps)))

    entries = []
    for comp in participants:
        # 각 업체별 투찰률 생성 (기본 분포 + 개별 성향)
        comp_bias = _comp_bias(comp.id)
        rate = base_rate + comp_bias + random.gauss(0, 0.003)
        rate = round(max(0.8775, min(0.9999, rate)), 4)
        entries.append((comp, rate))

    # 낙찰하한율 이상인 것들 중 가장 낮은 게 낙찰
    valid = [(c, r) for c, r in entries if r >= 0.8775]
    if not valid:
        valid = entries

    valid.sort(key=lambda x: x[1])
    winner_comp, winner_rate = valid[0]

    for rank, (comp, rate) in enumerate(sorted(entries, key=lambda x: x[1]), 1):
        is_win = (comp.id == winner_comp.id)
        db.add(BidResult(
            bid_id=bid.id,
            competitor_id=comp.id,
            bid_amount=int(bid.base_amount * rate),
            bid_rate=rate,
            rank=rank,
            is_winner=is_win,
        ))


def _comp_bias(comp_id: int) -> float:
    """업체별 고유 투찰 성향 (-0.005 ~ +0.005)."""
    rng = random.Random(comp_id * 137)
    return round(rng.gauss(0, 0.003), 4)


def _seed_admin(db: Session):
    from .config import get_settings
    s = get_settings()
    existing = db.query(User).filter(User.email == s.first_admin_email).first()
    if not existing:
        db.add(User(
            email=s.first_admin_email,
            hashed_password=hash_password(s.first_admin_password),
            name="관리자",
            role="admin",
            department="IT",
        ))
        db.commit()
        logger.info(f"관리자 계정 생성: {s.first_admin_email}")


def ensure_admin_password(db: Session):
    """서버 시작마다 호출 — .env의 FIRST_ADMIN_PASSWORD를 DB에 항상 동기화.

    계정이 없으면 생성, 있으면 비밀번호를 .env 값으로 강제 업데이트.
    이렇게 해야 .env 수정 → 재시작만으로 비밀번호가 복구된다.
    """
    from .config import get_settings
    s = get_settings()
    new_hash = hash_password(s.first_admin_password)
    user = db.query(User).filter(User.email == s.first_admin_email).first()
    if not user:
        db.add(User(
            email=s.first_admin_email,
            hashed_password=new_hash,
            name="관리자",
            role="admin",
            department="IT",
            is_active=True,
        ))
        db.commit()
        logger.info(f"관리자 계정 생성: {s.first_admin_email}")
    else:
        user.hashed_password = new_hash
        user.is_active = True
        db.commit()
        logger.info(f"관리자 비밀번호 동기화 완료: {s.first_admin_email}")


def _train_initial_model(db: Session):
    """시드 데이터로 초기 ML 모델 학습."""
    try:
        import pandas as pd
        from sqlalchemy import text
        from .ml.engine import train_models, FEATURE_COLS

        rows = db.execute(text("""
            SELECT b.id, b.agency_id, b.industry_id, b.region_id,
                   b.base_amount, b.bid_open_date, b.region_restriction,
                   r.bid_rate, r.is_winner,
                   (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id) as comp_count
            FROM bids b
            JOIN bid_results r ON r.bid_id = b.id
            WHERE b.status = 'closed'
        """)).fetchall()

        if len(rows) < 100:
            logger.info("학습 데이터 부족 — ML 학습 건너뜀 (규칙 기반 사용)")
            return

        df = pd.DataFrame(rows, columns=[
            "id","agency_id","industry_id","region_id","base_amount",
            "bid_open_date","region_restriction","bid_rate","is_winner","comp_count"
        ])

        # 피처 계산
        import math
        df["amount_log10"]           = df["base_amount"].apply(lambda x: math.log10(max(x,1)))
        df["amount_bucket"]          = df["base_amount"].apply(_amount_bucket)
        df["month_of_year"]          = pd.to_datetime(df["bid_open_date"]).dt.month
        df["season_index"]           = (pd.to_datetime(df["bid_open_date"]).dt.month - 1) // 3 + 1
        df["is_q4"]                  = (pd.to_datetime(df["bid_open_date"]).dt.month >= 10).astype(int)
        df["has_region_restriction"] = df["region_restriction"].astype(int)
        df["expected_competitor_count"] = df["comp_count"]
        df["competitor_strength_score"] = 5.0

        # 집계 피처 (같은 기관의 이전 입찰)
        df = df.sort_values("bid_open_date")
        agency_rates = df[df["is_winner"]].groupby("agency_id")["bid_rate"].expanding().mean().reset_index(level=0, drop=True)
        df["agency_avg_rate_12m"]  = df.groupby("agency_id")["bid_rate"].transform(lambda x: x.shift(1).expanding().mean())
        df["agency_win_rate_12m"]  = df.groupby("agency_id")["is_winner"].transform(lambda x: x.shift(1).expanding().mean())
        df["agency_bid_count_12m"] = df.groupby("agency_id").cumcount()
        df["region_avg_rate_12m"]  = df.groupby("region_id")["bid_rate"].transform(lambda x: x.shift(1).expanding().mean())
        df["industry_avg_rate_12m"]= df.groupby("industry_id")["bid_rate"].transform(lambda x: x.shift(1).expanding().mean())

        # 유사 입찰 피처 (단순화)
        df["similar_bid_count"] = df.groupby(["industry_id","region_id"]).cumcount()
        df["similar_avg_rate"]  = df.groupby(["industry_id","region_id"])["bid_rate"].transform(lambda x: x.shift(1).expanding().mean())
        df["similar_std_rate"]  = df.groupby(["industry_id","region_id"])["bid_rate"].transform(lambda x: x.shift(1).expanding().std().fillna(0.003))

        df["target_rate"] = df["bid_rate"]
        df_train = df.dropna(subset=["agency_avg_rate_12m"]).copy()

        if len(df_train) >= 100:
            train_models(df_train)
            from .ml.engine import get_engine
            get_engine().reload()
            logger.info("초기 ML 모델 학습 완료")

    except Exception as e:
        logger.warning(f"초기 모델 학습 실패 (규칙 기반으로 동작): {e}")


def _amount_bucket(amount: int) -> int:
    if amount < 1e8:     return 1
    elif amount < 5e8:   return 2
    elif amount < 1e9:   return 3
    elif amount < 5e9:   return 4
    else:                return 5
