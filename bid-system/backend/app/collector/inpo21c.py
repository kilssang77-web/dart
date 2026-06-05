"""
inpo21c 전 참여자 수집 모듈.

cloud.info21c.net에서 낙찰 목록 → 각 공고 전체 참가업체 데이터 수집.
쿠키는 settings.inpo21c_cookie (환경변수 INPO21C_COOKIE)에서 읽는다.
"""
import re
import time
import logging
from urllib.request import Request, urlopen
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

BASE = "https://cloud.info21c.net"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _fetch(url: str, cookie: str, referer: str = BASE) -> str:
    req = Request(url, headers={
        "Cookie":          cookie,
        "User-Agent":      UA,
        "Referer":         referer,
        "sec-fetch-mode":  "cors",
        "sec-fetch-site":  "same-origin",
    })
    try:
        with urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("inpo21c fetch 실패 [%s]: %s", url, e)
        return ""


def _get_bid_ids(page: int, cookie: str) -> list:
    html = _fetch(f"{BASE}/suc/con?division=1&page={page}", cookie)
    return [m.group(1) for m in re.finditer(r'/suc/view/con/([^"]+)"', html)]


def _parse_participants(html: str) -> list:
    rows = []
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr.group(1), re.DOTALL)
        if len(cells) < 8:
            continue

        def txt(s):
            return re.sub(r"<[^>]+>", "", s).strip()

        rank_s = txt(cells[0])
        if not rank_s.isdigit():
            continue
        biz_no    = txt(cells[1])
        name_m    = re.search(r'data-officenm="([^"]+)"', cells[2])
        name      = name_m.group(1) if name_m else txt(cells[2])
        amt_s     = txt(cells[4]).replace(",", "")
        rate_s    = txt(cells[5])
        base_s    = txt(cells[6])
        assess_m  = re.match(r"[\d.]+", txt(cells[7]))
        is_winner = "1순위" in txt(cells[8]) if len(cells) > 8 else False
        try:
            rows.append({
                "rank":            int(rank_s),
                "biz_reg_no":      biz_no,
                "company_name":    name,
                "bid_amount":      int(amt_s) if amt_s else None,
                "bid_rate":        float(rate_s) / 100 if rate_s else None,
                "base_ratio":      float(base_s) / 100 if base_s else None,
                "assessment_rate": float(assess_m.group()) / 100 if assess_m else None,
                "is_winner":       is_winner,
            })
        except Exception:
            continue
    return rows


def _upsert_participants(db: Session, bid_id: str, rows: list) -> int:
    count = 0
    for r in rows:
        try:
            db.execute(text("""
                INSERT INTO inpo21c_participants
                    (inpo21c_bid_id, rank, biz_reg_no, company_name,
                     bid_amount, bid_rate, base_ratio, assessment_rate, is_winner)
                VALUES
                    (:bid_id, :rank, :biz_reg_no, :company_name,
                     :bid_amount, :bid_rate, :base_ratio, :assessment_rate, :is_winner)
                ON CONFLICT (inpo21c_bid_id, biz_reg_no) DO UPDATE SET
                    bid_rate        = EXCLUDED.bid_rate,
                    base_ratio      = EXCLUDED.base_ratio,
                    assessment_rate = EXCLUDED.assessment_rate,
                    is_winner       = EXCLUDED.is_winner
            """), {"bid_id": bid_id, **r})
            count += 1
        except Exception as e:
            logger.debug("upsert 실패 [%s/%s]: %s", bid_id, r.get("biz_reg_no"), e)
    db.commit()
    return count


def collect_inpo21c(db: Session, max_pages: int = 4) -> dict:
    """
    inpo21c 낙찰 목록을 순회하며 전 참여자 데이터를 수집.

    Returns:
        {"bids": int, "participants": int, "skipped": int}
    """
    from app.config import get_settings
    settings = get_settings()
    cookie   = getattr(settings, "inpo21c_cookie", "")
    if not cookie:
        logger.warning("INPO21C_COOKIE 미설정 — inpo21c 수집 건너뜀")
        return {"bids": 0, "participants": 0, "skipped": 0}

    # 기존 수집된 bid_id 목록 캐싱 (중복 스킵)
    existing = {r[0] for r in db.execute(
        text("SELECT DISTINCT inpo21c_bid_id FROM inpo21c_participants")
    ).fetchall()}

    total_bids = total_participants = skipped = 0

    for page in range(1, max_pages + 1):
        bid_ids = list(dict.fromkeys(_get_bid_ids(page, cookie)))
        if not bid_ids:
            break
        for bid_id in bid_ids:
            if bid_id in existing:
                skipped += 1
                continue
            detail_url = f"{BASE}/suc/view/con/{bid_id}"
            html = _fetch(detail_url, cookie, referer=f"{BASE}/suc/con?division=1")
            rows = _parse_participants(html)
            if rows:
                cnt = _upsert_participants(db, bid_id, rows)
                total_participants += cnt
                total_bids += 1
                existing.add(bid_id)
            time.sleep(0.5)

    logger.info("inpo21c 수집 완료: %d건 공고, %d명 참여자, %d건 스킵",
                total_bids, total_participants, skipped)
    return {"bids": total_bids, "participants": total_participants, "skipped": skipped}
