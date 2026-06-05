"""
Engine C — 동적 경쟁강도 분석 엔진

기관/공종별 최근 입찰 이력에서 실시간으로 경쟁강도를 계산.
HHI(허핀달-허슈만 지수) 기반 낙찰 집중도 + 공격성 점수 통합.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

LOOKBACK_WEEKS = 16   # 기본 16주(4개월) 이력 분석


def compute_competition_features(
    db: Session,
    agency_id: int,
    industry_id: int,
    base_amount: int,
    bid_date: Optional[datetime] = None,
    known_competitor_ids: Optional[List[int]] = None,
    lookback_weeks: int = LOOKBACK_WEEKS,
) -> dict:
    """
    최근 lookback_weeks 주간 동일 기관+공종 공고 참여 업체 분석.
    competitor_strength_score 를 동적으로 계산하여 반환.
    """
    dt = bid_date or datetime.now()
    cutoff = dt - timedelta(weeks=lookback_weeks)

    rows = db.execute(text("""
        SELECT
            br.competitor_id,
            br.bid_rate::float,
            br.is_winner,
            b.base_amount::float,
            b.bid_open_date
        FROM bid_results br
        JOIN bids b ON b.id = br.bid_id
        WHERE b.agency_id   = :aid
          AND b.industry_id = :iid
          AND b.bid_open_date BETWEEN :cutoff AND :dt
          AND b.status = 'closed'
          AND b.base_amount BETWEEN :lo AND :hi
    """), {
        "aid": agency_id, "iid": industry_id,
        "cutoff": cutoff, "dt": dt,
        "lo": int(base_amount * 0.5),
        "hi": int(base_amount * 2.0),
    }).fetchall()

    if not rows:
        return _zero_features()

    df = pd.DataFrame(rows, columns=["competitor_id","bid_rate","is_winner","base_amount","bid_open_date"])
    df["bid_rate"] = pd.to_numeric(df["bid_rate"])

    comp_agg = df.groupby("competitor_id").agg(
        avg_rate   = ("bid_rate", "mean"),
        std_rate   = ("bid_rate", lambda x: x.std() if len(x)>1 else 0.005),
        bid_count  = ("bid_rate", "count"),
        win_count  = ("is_winner","sum"),
        agg_score  = ("bid_rate", lambda r: float(np.mean(np.array(r) < 0.88) * 10)),
    ).reset_index()

    # ── HHI (낙찰 집중도)
    wins = comp_agg.set_index("competitor_id")["win_count"]
    total_wins = wins.sum()
    if total_wins > 0:
        win_share = wins / total_wins
        hhi = float((win_share ** 2).sum())
    else:
        hhi = 0.1

    # ── 공격적 업체 비율 (aggression > 5 기준)
    agg_ratio = len(comp_agg[comp_agg["agg_score"] > 5]) / max(len(comp_agg), 1)

    # ── 예상 최저 투찰률 (하위 10% 분위수)
    floor_rate = float(df["bid_rate"].quantile(0.10))
    floor_rate = max(0.870, floor_rate)

    # ── 시장 압박 지수 (0~1)
    pressure = min(1.0, agg_ratio * 0.5 + hhi * 0.3 + comp_agg["avg_rate"].std() * 8 * 0.2)

    # ── 종합 경쟁강도 (0~10)
    avg_agg  = float(comp_agg["agg_score"].mean())
    wr_total = float(comp_agg["win_count"].sum() / max(len(df), 1) * 10)
    avg_cons = float(comp_agg.apply(
        lambda r: max(0.0, 10.0 - (r["std_rate"] / r["avg_rate"] * 100))
        if r["avg_rate"] > 0 else 5.0, axis=1
    ).mean())
    strength = round(avg_agg * 0.4 + wr_total * 0.4 + avg_cons * 0.2, 2)

    # ── 알려진 경쟁사 가중 보정
    if known_competitor_ids:
        known = comp_agg[comp_agg["competitor_id"].isin(known_competitor_ids)]
        if not known.empty:
            known_str = float(known["agg_score"].mean())
            strength = round(strength * 0.6 + known_str * 0.4, 2)

    # ── 예상 경쟁업체 수
    expected_count = len(comp_agg)

    # ── 최근 낙찰 최저가 (공격적 투찰 참고)
    winner_rates = df[df["is_winner"]]["bid_rate"].dropna()
    winner_min = float(winner_rates.min()) if len(winner_rates) > 0 else floor_rate

    return {
        "expected_competitor_count":   expected_count,
        "competitor_strength_score":   min(10.0, strength),
        "market_pressure_index":       round(pressure, 4),
        "hhi_score":                   round(hhi, 4),
        "expected_floor_rate":         round(floor_rate, 4),
        "aggressive_comp_ratio":       round(agg_ratio, 4),
        "recent_winner_min_rate":      round(winner_min, 4),
        "recent_bid_sample":           len(df),
        "unique_competitors":          len(comp_agg),
    }


def get_competitor_profiles(
    db: Session,
    competitor_ids: List[int],
    agency_id: int,
    industry_id: int,
    bid_date: Optional[datetime] = None,
    lookback_weeks: int = LOOKBACK_WEEKS,
) -> List[dict]:
    """특정 경쟁사 목록의 상세 프로파일 반환."""
    if not competitor_ids:
        return []
    dt = bid_date or datetime.now()
    cutoff = dt - timedelta(weeks=lookback_weeks)

    rows = db.execute(text("""
        SELECT
            br.competitor_id,
            c.name,
            AVG(br.bid_rate::float)                                    AS avg_rate,
            STDDEV(br.bid_rate::float)                                 AS std_rate,
            COUNT(*)                                                   AS bid_count,
            SUM(CASE WHEN br.is_winner THEN 1 ELSE 0 END)             AS win_count,
            AVG(CASE WHEN br.bid_rate::float < 0.88 THEN 1.0 ELSE 0.0 END) * 10 AS agg_score
        FROM bid_results br
        JOIN competitors c ON c.id = br.competitor_id
        JOIN bids b ON b.id = br.bid_id
        WHERE br.competitor_id = ANY(:ids)
          AND b.bid_open_date >= :cutoff
        GROUP BY br.competitor_id, c.name
    """), {"ids": competitor_ids, "cutoff": cutoff}).fetchall()

    result = []
    for r in rows:
        cid, name, avg, std, cnt, wins, agg = r
        wr = float(wins or 0) / max(int(cnt), 1)
        cons = max(0.0, 10.0 - float(std or 0) / max(float(avg or 0.88), 0.001) * 100)
        risk_score = float(agg or 5) * 0.4 + wr * 10 * 0.4 + cons * 0.2
        risk = "LOW" if risk_score < 3 else "MEDIUM" if risk_score < 6 else "HIGH"
        result.append({
            "competitor_id":  int(cid),
            "name":           name,
            "avg_rate":       round(float(avg or 0), 4),
            "std_rate":       round(float(std or 0), 4),
            "bid_count":      int(cnt),
            "win_count":      int(wins or 0),
            "win_rate":       round(wr, 4),
            "aggression":     round(float(agg or 5), 2),
            "consistency":    round(cons, 2),
            "risk_level":     risk,
        })
    return result


def _zero_features() -> dict:
    return {
        "expected_competitor_count":   10,
        "competitor_strength_score":   5.0,
        "market_pressure_index":       0.40,
        "hhi_score":                   0.10,
        "expected_floor_rate":         0.878,
        "aggressive_comp_ratio":       0.20,
        "recent_winner_min_rate":      0.879,
        "recent_bid_sample":           0,
        "unique_competitors":          0,
    }

_COMP_DIST_QUERY = text("""
    SELECT
        br.competitor_id,
        AVG(br.bid_rate::float)    AS avg_rate,
        STDDEV(br.bid_rate::float) AS std_rate,
        COUNT(*)                   AS bid_count
    FROM bid_results br
    JOIN bids b ON b.id = br.bid_id
    WHERE {where}
      AND b.bid_open_date >= :cutoff
      AND b.status = 'closed'
    GROUP BY br.competitor_id
    ORDER BY COUNT(*) DESC
    LIMIT :top_n
""")

# 실제 입찰결과 기반 전국 시장 분포 (데이터 없을 때 합성용)
_MARKET_MEAN = 0.8836
_MARKET_STD  = 0.0073
_SYNTH_N     = 10          # 경쟁사 없을 때 합성 인원


def get_market_competitor_distributions(
    db: Session,
    agency_id: int,
    industry_id: int,
    bid_date: Optional[datetime] = None,
    lookback_weeks: int = 52,
    top_n: int = 20,
) -> tuple:
    """
    최근 동일 기관+공종 투찰률 분포 반환 (Monte Carlo 시뮬레이션 입력용).

    Fallback 순서:
      1) 기관+공종 (52주)
      2) 공종만    (52주) — 기관 데이터 < 5개사일 때
      3) 전체 시장 합성 분포 (실제 DB 통계 기반)
    """
    dt     = bid_date or datetime.now()
    cutoff = dt - timedelta(weeks=lookback_weeks)

    def _fetch(where_clause: str, params: dict) -> list:
        q = text(f"""
            SELECT
                br.competitor_id,
                AVG(br.bid_rate::float)    AS avg_rate,
                STDDEV(br.bid_rate::float) AS std_rate,
                COUNT(*)                   AS bid_count
            FROM bid_results br
            JOIN bids b ON b.id = br.bid_id
            WHERE {where_clause}
              AND b.bid_open_date >= :cutoff
              AND b.status = 'closed'
            GROUP BY br.competitor_id
            ORDER BY COUNT(*) DESC
            LIMIT :top_n
        """)
        return db.execute(q, {**params, "cutoff": cutoff, "top_n": top_n}).fetchall()

    # 1차: 기관 + 공종
    rows = _fetch("b.agency_id = :aid AND b.industry_id = :iid",
                  {"aid": agency_id, "iid": industry_id})

    # 2차: 공종만 (5개사 미만이면 더 넓게)
    if len(rows) < 5:
        rows_ind = _fetch("b.industry_id = :iid", {"iid": industry_id})
        if len(rows_ind) > len(rows):
            rows = rows_ind

    # 3차: 데이터 없으면 전국 시장 합성 분포
    if not rows:
        return [_MARKET_MEAN] * _SYNTH_N, [_MARKET_STD] * _SYNTH_N

    means = [float(r[1]) for r in rows if r[1] is not None]
    stds  = [max(float(r[2] or 0.005), 0.003) for r in rows if r[1] is not None]
    return means, stds