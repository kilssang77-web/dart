"""
입찰 서비스 (BidService)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, desc

from ..models import (
    Bid, BidResult, Competitor, Agency, Industry, Region, IndustryFilter,
)
from ..schemas import BidCreate, BidResultCreate
from ._common import get_active_industry_ids

logger = logging.getLogger(__name__)


class BidService:

    def list_bids(
        self, db: Session,
        agency_id=None, industry_id=None, region_id=None,
        status=None, date_from=None, date_to=None,
        keyword=None, page=1, size=20,
        sort_by='notice_date',
        yega_method=None, contract_method=None,
        base_amount_min=None, base_amount_max=None,
    ) -> dict:
        q = db.query(Bid).options(
            joinedload(Bid.agency),
            joinedload(Bid.industry),
            joinedload(Bid.region),
        )
        if agency_id:   q = q.filter(Bid.agency_id == agency_id)
        if industry_id: q = q.filter(Bid.industry_id == industry_id)
        if region_id:   q = q.filter(Bid.region_id == region_id)
        if status:      q = q.filter(Bid.status == status)
        if date_from:   q = q.filter(Bid.bid_open_date >= date_from)
        if date_to:     q = q.filter(Bid.bid_open_date < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
        if keyword:
            q = q.filter(Bid.title.ilike(f"%{keyword}%"))
        if yega_method:     q = q.filter(Bid.yega_method.ilike(f"%{yega_method}%"))
        if contract_method: q = q.filter(Bid.contract_method.ilike(f"%{contract_method}%"))
        if base_amount_min is not None: q = q.filter(Bid.base_amount >= base_amount_min)
        if base_amount_max is not None: q = q.filter(Bid.base_amount <= base_amount_max)

        # 활성 공종 필터 — 사용자가 특정 공종을 지정하지 않은 경우에만 전역 필터 적용
        if not industry_id:
            active_ids = get_active_industry_ids(db)
            if active_ids is not None:
                if not active_ids:
                    return {"items": [], "total": 0, "page": page, "size": size}
                q = q.filter(Bid.industry_id.in_(active_ids))

        total = q.count()

        if sort_by == 'bid_open_date':
            q = q.order_by(desc(Bid.bid_open_date).nullslast(), desc(Bid.created_at))
        else:
            q = q.order_by(desc(Bid.notice_date).nullslast(), desc(Bid.created_at))

        bids = q.offset((page-1)*size).limit(size).all()

        bid_ids = [b.id for b in bids]
        # bid_results: winner_rate + 참여자 수 배치 집계 (SELECT * joinedload 대체)
        winner_map: dict = {}
        count_map: dict = {}
        auto_verdicts: dict = {}
        if bid_ids:
            from sqlalchemy import text as _t
            # winner rate + count in one query
            br_rows = db.execute(_t("""
                SELECT bid_id,
                       MAX(bid_rate) FILTER (WHERE is_winner = true) AS winner_rate,
                       COUNT(*) AS total_count
                FROM bid_results
                WHERE bid_id = ANY(:ids)
                GROUP BY bid_id
            """), {"ids": bid_ids}).fetchall()
            for row in br_rows:
                winner_map[int(row[0])] = float(row[1]) if row[1] else None
                count_map[int(row[0])] = int(row[2])

            qc_rows = db.execute(_t("""
                SELECT bid_id, verdict, pass_prob, fail_reason
                FROM qualification_checks
                WHERE bid_id = ANY(:ids) AND user_id = 1
            """), {"ids": bid_ids}).fetchall()
            for row in qc_rows:
                auto_verdicts[int(row[0])] = {
                    "verdict": row[1], "pass_prob": float(row[2]) if row[2] else None,
                    "fail_reason": row[3],
                }

        items = []
        for b in bids:
            qv = auto_verdicts.get(b.id)
            items.append({
                "id": b.id, "announcement_no": b.announcement_no,
                "title": b.title,
                "agency_name":      b.agency.name if b.agency else "",
                "industry_name":    b.industry.name if b.industry else "",
                "region_name":      b.region.name if b.region else "",
                "base_amount":      b.base_amount,
                "estimated_price":  b.estimated_price,
                "notice_date":      b.notice_date,
                "bid_close_date":   b.bid_close_date,
                "bid_open_date":    b.bid_open_date,
                "status":           b.status,
                "source":           b.source,
                "winner_rate":      winner_map.get(b.id),
                "min_bid_rate":     float(b.min_bid_rate) if b.min_bid_rate else None,
                "yega_method":      b.yega_method,
                "contract_method":  b.contract_method,
                "competitor_count": count_map.get(b.id, 0),
                # 자동 적격 판정
                "auto_verdict":     qv["verdict"] if qv else None,
                "auto_pass_prob":   qv["pass_prob"] if qv else None,
                "auto_fail_reason": qv["fail_reason"] if qv else None,
            })
        return {"items": items, "total": total, "page": page, "size": size}

    def get_bid_detail(self, db: Session, bid_id: int) -> Optional[dict]:
        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return None
        winner = next((r for r in b.results if r.is_winner), None)
        results = [
            {
                "id": r.id,
                "competitor_id":   r.competitor_id,
                "competitor_name": r.competitor.name if r.competitor else "",
                "bid_amount":      r.bid_amount,
                "bid_rate":        float(r.bid_rate),
                "rank":            r.rank,
                "is_winner":       r.is_winner,
                "assessment_rate": float(r.assessment_rate) if r.assessment_rate else None,
            }
            for r in sorted(b.results, key=lambda x: x.rank)
        ]
        from sqlalchemy import text as sa_text
        inpo_row = db.execute(sa_text("""
            SELECT preset_amount, yega_ratio, net_cost
            FROM inpo21c_bids
            WHERE announcement_no LIKE :ano
            ORDER BY open_datetime DESC NULLS LAST
            LIMIT 1
        """), {"ano": b.announcement_no + "%"}).fetchone() if b.announcement_no else None
        preset_amount = int(inpo_row[0]) if inpo_row and inpo_row[0] else None
        yega_ratio    = float(inpo_row[1]) if inpo_row and inpo_row[1] else None
        net_cost      = int(inpo_row[2]) if inpo_row and inpo_row[2] else None

        return {
            "id": b.id, "announcement_no": b.announcement_no,
            "title": b.title,
            "agency_name":           b.agency.name if b.agency else "",
            "industry_name":         b.industry.name if b.industry else "",
            "region_name":           b.region.name if b.region else "",
            "base_amount":           b.base_amount,
            "estimated_price":       b.estimated_price,
            "a_value":               b.a_value,
            "min_bid_rate":          float(b.min_bid_rate) if b.min_bid_rate else None,
            "notice_date":           b.notice_date,
            "bid_open_date":         b.bid_open_date,
            "bid_close_date":        b.bid_close_date,
            "construction_period":   b.construction_period,
            "region_restriction":    b.region_restriction,
            "status":                b.status,
            "source":                b.source,
            "ntce_url":              b.ntce_url,
            "winner_rate":           float(winner.bid_rate) if winner else None,
            "competitor_count":      len(b.results),
            "construction_site":     b.construction_site,
            "contract_method":       b.contract_method,
            "bid_method":            b.bid_method,
            "eligible_regions":      b.eligible_regions,
            "industry_limit":        b.industry_limit,
            "contact_name":          b.contact_name,
            "contact_tel":           b.contact_tel,
            "yega_method":           b.yega_method,
            "registration_deadline": b.registration_deadline,
            "preset_amount":         preset_amount,
            "yega_ratio":            yega_ratio,
            "net_cost":              net_cost,
            "results":               results,
        }

    def create_bid(self, db: Session, data: BidCreate, results: List[BidResultCreate] = None) -> Bid:
        bid = Bid(
            announcement_no=data.announcement_no,
            title=data.title,
            agency_id=data.agency_id,
            industry_id=data.industry_id,
            region_id=data.region_id,
            base_amount=data.base_amount,
            min_bid_rate=data.min_bid_rate,
            a_value=data.a_value,
            bid_open_date=data.bid_open_date,
            construction_period=data.construction_period,
            region_restriction=data.region_restriction,
            source="manual",
            status="closed",
        )
        db.add(bid)
        db.flush()

        if results:
            for r in results:
                comp = db.query(Competitor).filter(Competitor.name == r.competitor_name).first()
                if not comp:
                    comp = Competitor(name=r.competitor_name)
                    db.add(comp)
                    db.flush()
                br = BidResult(
                    bid_id=bid.id,
                    competitor_id=comp.id,
                    bid_amount=r.bid_amount,
                    bid_rate=r.bid_rate,
                    rank=r.rank,
                    is_winner=r.is_winner,
                )
                db.add(br)
        db.commit()
        return bid

    def find_similar_bids(self, db: Session, bid_id: int, top_k: int = 8) -> List[dict]:
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            return []
        rows = db.query(Bid).filter(
            Bid.industry_id == bid.industry_id,
            Bid.region_id == bid.region_id,
            Bid.base_amount.between(int(bid.base_amount * 0.6), int(bid.base_amount * 1.4)),
            Bid.id != bid_id,
            Bid.status == "closed",
        ).order_by(desc(Bid.bid_open_date)).limit(top_k).all()

        results = []
        for b in rows:
            winner = next((r for r in b.results if r.is_winner), None)
            amt_diff = abs(b.base_amount - bid.base_amount) / bid.base_amount
            sim_score = round(1.0 - amt_diff, 3)
            results.append({
                "bid_id": b.id, "title": b.title,
                "agency_name":     b.agency.name if b.agency else "",
                "base_amount":     b.base_amount,
                "bid_open_date":   b.bid_open_date,
                "winner_rate":     float(winner.bid_rate) if winner else None,
                "competitor_count": len(b.results),
                "similarity_score": sim_score,
            })
        return results

    def get_keyword_matches(self, db: Session) -> list:
        """활성 키워드별 매칭 공고 수 + 최근 공고 5건 반환 — Redis 180초 캐시."""
        from ..models import WatchKeyword as KW
        from ..common.cache import get_redis, cache_get, cache_set

        rc = get_redis()
        cache_key = "bids:keyword_matches"
        cached = cache_get(rc, cache_key)
        if cached is not None:
            return cached

        keywords = db.query(KW).filter(KW.is_active == True).order_by(KW.created_at.desc()).all()
        if not keywords:
            return []

        result = []
        cutoff_7d = datetime.now() - timedelta(days=7)
        active_ids = get_active_industry_ids(db)
        ind_filter = ""
        if active_ids:
            ids_str = ",".join(str(i) for i in active_ids)
            ind_filter = f"AND b.industry_id IN ({ids_str})"

        for kw in keywords:
            kw_safe = kw.keyword.replace("'", "''")
            if kw.kw_type == "agency":
                where = f"a.name ILIKE '%{kw_safe}%'"
                join_clause = "JOIN agencies a ON a.id = b.agency_id"
            else:
                where = f"b.title ILIKE '%{kw_safe}%'"
                join_clause = "LEFT JOIN agencies a ON a.id = b.agency_id"

            # DB-side COUNT + 최근 5건 (unbounded fetch 제거)
            agg = db.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE b.created_at >= :cutoff) AS new_7d
                FROM bids b
                {join_clause}
                WHERE {where} {ind_filter}
            """), {"cutoff": cutoff_7d}).fetchone()

            recent_rows = db.execute(text(f"""
                SELECT b.id, b.title, a.name AS agency_name, b.base_amount,
                       b.notice_date, b.status
                FROM bids b
                {join_clause}
                WHERE {where} {ind_filter}
                ORDER BY b.notice_date DESC NULLS LAST
                LIMIT 5
            """)).fetchall()

            total  = int(agg[0]) if agg else 0
            new_7d = int(agg[1]) if agg else 0

            result.append({
                "keyword_id":  kw.id,
                "keyword":     kw.keyword,
                "kw_type":     kw.kw_type,
                "note":        kw.note,
                "match_count": total,
                "new_7d":      new_7d,
                "recent_bids": [
                    {
                        "id":          r[0],
                        "title":       r[1],
                        "agency_name": r[2] or "",
                        "base_amount": r[3],
                        "notice_date": r[4].isoformat() if r[4] else None,
                        "status":      r[5],
                    }
                    for r in recent_rows
                ],
            })

        cache_set(rc, cache_key, result, ttl=180)
        return result
