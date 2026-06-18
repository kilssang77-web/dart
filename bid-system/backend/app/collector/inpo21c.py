"""
inpo21c 수집 모듈.

cloud.info21c.net에서 낙찰/입찰 데이터 수집:
  - /suc/con  : 낙찰 목록 -> 전 참여자 + 복수예가 분포 + 공고 헤더
  - /bid/con  : 입찰공고 중 목록 -> 개찰 전 사전정보(예가방법, 낙찰하한율 등)
쿠키는 settings.inpo21c_cookie (환경변수 INPO21C_COOKIE)에서 읽는다.
자동 로그인: settings.inpo21c_id / settings.inpo21c_pw
"""
import re
import time
import json
import logging
import threading
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _record_log(db: Session, collect_type: str, success: int, fail: int,
                duration: float, error_summary: str | None = None,
                detail: dict | None = None):
    from app.models import CollectionLog
    log = CollectionLog(
        collect_type=collect_type,
        collected_at=datetime.now(tz=timezone.utc),
        success_count=success,
        fail_count=fail,
        duration_sec=round(duration, 2),
        error_summary=error_summary,
        detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
    )
    db.add(log)
    db.commit()

BASE = "https://cloud.info21c.net"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ── 수집 진행 상태 (스레드 안전) ────────────────────────────────
_prog_lock = threading.Lock()
_prog: dict = {
    "running": False, "job_type": None,
    "page": 0, "max_pages": 0, "total_pages": 0,
    "bids": 0, "participants": 0, "yega": 0, "skipped": 0,
    "pct": 0.0, "started_at": None, "finished_at": None, "error": None,
}


def get_collect_progress() -> dict:
    with _prog_lock:
        return dict(_prog)


def _prog_start(job_type: str, max_pages: int) -> None:
    with _prog_lock:
        _prog.update({
            "running": True, "job_type": job_type,
            "page": 0, "max_pages": max_pages, "total_pages": 0,
            "bids": 0, "participants": 0, "yega": 0, "skipped": 0,
            "pct": 0.0, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None, "error": None,
        })


def _prog_page(page: int, pct: float) -> None:
    with _prog_lock:
        _prog["page"] = page
        _prog["total_pages"] += 1
        _prog["pct"] = round(min(pct, 99.0), 1)


def _prog_add(bids: int = 0, participants: int = 0, yega: int = 0, skipped: int = 0) -> None:
    with _prog_lock:
        _prog["bids"] += bids
        _prog["participants"] += participants
        _prog["yega"] += yega
        _prog["skipped"] += skipped


def _prog_done(error: str | None = None) -> None:
    with _prog_lock:
        _prog["running"] = False
        _prog["pct"] = 100.0
        _prog["finished_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            _prog["error"] = error

_LOGIN_SIGNALS = ["login", "sign_in", "로그인", "세션이 만료", "인증이 필요"]

_AUTH_BASE      = "https://infose.info21c.net"
_LOGIN_URL      = f"{_AUTH_BASE}/info21c/member/login/index"
_LOGIN_EXEC_URL = f"{_AUTH_BASE}/info21c/member/login/loginexec"


def auto_login(user_id: str, password: str) -> str | None:
    import http.cookiejar
    import urllib.parse
    from urllib.request import build_opener, HTTPCookieProcessor

    if not user_id or not password:
        logger.warning("INPO21C_ID 또는 INPO21C_PW 미설정 -- 자동 로그인 불가")
        return None

    cj     = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))

    try:
        refurl  = urllib.parse.quote(BASE + "/suc/con")
        req     = Request(
            f"{_LOGIN_URL}?refurl={refurl}",
            headers={"User-Agent": UA, "Accept": "text/html", "Referer": BASE},
        )
        resp    = opener.open(req, timeout=15)
        html    = resp.read().decode("utf-8", errors="replace")

        csrf_match = re.search(
            r'name="_csrf-frontend"[^>]+value="([^"]+)"', html, re.IGNORECASE
        )
        if not csrf_match:
            logger.error("inpo21c CSRF 토큰 취득 실패")
            return None
        csrf_token = csrf_match.group(1)

        signed_match = re.search(
            r'name="signeddata"[^>]*value="([^"]*)"', html, re.IGNORECASE
        )
        signed_data = signed_match.group(1) if signed_match else ""

        payload = urllib.parse.urlencode({
            "_csrf-frontend": csrf_token,
            "refurl":         f"{BASE}/suc/con",
            "signeddata":     signed_data,
            "PlainData":      "info21c",
            "id":             user_id,
            "pass":           password,
        }).encode()

        post_req = Request(
            _LOGIN_EXEC_URL,
            data=payload,
            headers={
                "User-Agent":   UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer":      _LOGIN_URL,
                "Origin":       _AUTH_BASE,
            },
        )
        post_resp = opener.open(post_req, timeout=15)
        post_resp.read()

        sess_id = next((c.value for c in cj if c.name == "INFO21CSESSID"), None)
        if not sess_id:
            logger.error("inpo21c 로그인 실패 -- INFO21CSESSID 없음")
            return None

        cookie_parts = [f"INFO21CSESSID={sess_id}"]
        for c in cj:
            if c.name != "INFO21CSESSID" and "info21c.net" in (c.domain or ""):
                cookie_parts.append(f"{c.name}={c.value}")
        cookie_str = "; ".join(cookie_parts)
        logger.info("inpo21c 자동 로그인 성공 (SESSID 취득)")
        return cookie_str

    except Exception as exc:
        logger.error("inpo21c 자동 로그인 실패: %s", exc)
        return None


def check_cookie_valid(cookie: str) -> bool:
    if not cookie:
        return False
    html = _fetch(f"{BASE}/suc/con?division=1&page=1", cookie)
    if not html:
        logger.error("inpo21c 쿠키 검증 실패 — 응답 없음")
        return False
    if "/suc/view/con/" in html:
        return True
    html_lower = html.lower()
    if any(sig in html_lower for sig in _LOGIN_SIGNALS):
        logger.error("inpo21c 쿠키 만료 — 로그인 페이지로 리다이렉트됨.")
        return False
    logger.error("inpo21c 쿠키 만료 추정 — 낙실 목록 미확인 (응답 길이: %d bytes).", len(html))
    return False


def _fetch(url: str, cookie: str, referer: str = BASE) -> str:
    req = Request(url, headers={
        "Cookie":         cookie,
        "User-Agent":     UA,
        "Referer":        referer,
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    })
    try:
        with urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("inpo21c fetch 실패 [%s]: %s", url, e)
        return ""


def _ensure_tables(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS inpo21c_bids (
            inpo21c_bid_id   VARCHAR(30)  PRIMARY KEY,
            announcement_no  VARCHAR(50),
            title            VARCHAR(500),
            industry         VARCHAR(200),
            region           VARCHAR(200),
            agency_name      VARCHAR(200),
            open_datetime    TIMESTAMP,
            base_amount      BIGINT,
            estimated_amount BIGINT,
            min_bid_rate     NUMERIC(8,4),
            preset_amount    BIGINT,
            yega_ratio       NUMERIC(8,4),
            net_cost         BIGINT,
            created_at       TIMESTAMP DEFAULT now()
        )
    """))
    db.execute(text("ALTER TABLE inpo21c_bids ADD COLUMN IF NOT EXISTS title VARCHAR(500)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_inpo21c_bids_announcement ON inpo21c_bids(announcement_no)"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS inpo21c_yega (
            id              SERIAL PRIMARY KEY,
            inpo21c_bid_id  VARCHAR(30)  NOT NULL,
            yega_no         SMALLINT     NOT NULL,
            amount          BIGINT,
            base_ratio      NUMERIC(8,4),
            base_ratio_pct  NUMERIC(8,4),
            is_selected     BOOLEAN DEFAULT FALSE,
            UNIQUE(inpo21c_bid_id, yega_no)
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_inpo21c_yega_bid ON inpo21c_yega(inpo21c_bid_id)"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS inpo21c_bid_notices (
            inpo21c_bid_id   VARCHAR(30)  PRIMARY KEY,
            announcement_no  VARCHAR(50),
            industry         VARCHAR(200),
            region           VARCHAR(200),
            agency_name      VARCHAR(200),
            yega_method      VARCHAR(100),
            yega_draw_count  SMALLINT,
            yega_total_count SMALLINT,
            yega_range_min   SMALLINT,
            yega_range_max   SMALLINT,
            min_bid_rate     NUMERIC(8,4),
            contract_method  VARCHAR(100),
            reg_deadline     TIMESTAMP,
            bid_deadline     TIMESTAMP,
            open_datetime    TIMESTAMP,
            base_amount      BIGINT,
            estimated_amount BIGINT,
            a_value          BIGINT,
            created_at       TIMESTAMP DEFAULT now(),
            updated_at       TIMESTAMP DEFAULT now()
        )
    """))
    db.execute(text("ALTER TABLE inpo21c_bid_notices ADD COLUMN IF NOT EXISTS a_value BIGINT"))
    db.execute(text("ALTER TABLE inpo21c_bids ADD COLUMN IF NOT EXISTS a_value BIGINT"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_inpo21c_notices_announcement ON inpo21c_bid_notices(announcement_no)"))
    db.commit()


def _get_bid_ids(page: int, cookie: str, division: int = 1) -> list[tuple[str, str]]:
    """낙찰 목록에서 (bid_id, title) 수집."""
    html = _fetch(f"{BASE}/suc/con?division={division}&page={page}", cookie)
    results = []
    for m in re.finditer(
        r'/suc/view/con/([^"]+)"[^>]*class="list_link constnm_link">([^<]*)',
        html,
    ):
        results.append((m.group(1).strip(), m.group(2).strip()))
    if not results:
        results = [(m.group(1), "") for m in re.finditer(r'/suc/view/con/([^"]+)"', html)]
    return results


def _txt(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _parse_amount(s: str) -> int | None:
    if not s:
        return None
    clean = re.sub(r"[^\d]", "", s.split("원")[0])
    return int(clean) if clean else None


def _parse_rate(s: str) -> float | None:
    m = re.match(r"[\d.]+", s.strip()) if s else None
    return float(m.group()) if m else None


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(\d{1,2})시\s*(\d{2})분", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4)), int(m.group(5)))
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _parse_participants(html: str) -> list:
    rows = []
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr.group(1), re.DOTALL)
        c0 = _txt(cells[0]) if cells else ""
        is_winner_row = len(cells) >= 9 and "순위업체" in c0

        if is_winner_row:
            rank_s   = _txt(cells[1])
            biz_no   = _txt(cells[2])
            name_m   = re.search(r'data-officenm="([^"]+)"', cells[3])
            name     = name_m.group(1) if name_m else _txt(cells[3])
            amt_s    = _txt(cells[5]).replace(",", "")
            rate_s   = _txt(cells[6])
            base_s   = _txt(cells[7])
            assess_m = re.match(r"[\d.]+", _txt(cells[8]))
            is_winner = True
        else:
            rank_s = c0
            if not rank_s.isdigit() or len(cells) < 8:
                continue
            biz_no   = _txt(cells[1])
            name_m   = re.search(r'data-officenm="([^"]+)"', cells[2])
            name     = name_m.group(1) if name_m else _txt(cells[2])
            amt_s    = _txt(cells[4]).replace(",", "")
            rate_s   = _txt(cells[5])
            base_s   = _txt(cells[6])
            assess_m = re.match(r"[\d.]+", _txt(cells[7]))
            is_winner = "1순위" in _txt(cells[8]) if len(cells) > 8 else False

        if not rank_s.isdigit():
            continue
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


def _parse_bid_header(html: str) -> dict | None:
    pairs: dict[str, str] = {}
    for m in re.finditer(r"<th>([^<]+)</th>\s*<td[^>]*>(.*?)</td>", html, re.DOTALL):
        key = m.group(1).strip()
        val = _txt(m.group(2)).strip()
        pairs[key] = val
    if not pairs:
        return None

    yega_ratio = None
    raw_yr = pairs.get("예가/기초", "")
    if raw_yr:
        m2 = re.match(r"[\d.]+", raw_yr.strip())
        if m2:
            yega_ratio = float(m2.group())

    return {
        "announcement_no":  re.sub(r"-\d+$", "", pairs.get("공고번호", "").strip()),
        "title":            (pairs.get("공고명", "") or pairs.get("입찰공고명", "") or pairs.get("공사명", "")).strip(),
        "industry":         pairs.get("공고업종", "").strip(),
        "region":           pairs.get("지역", "").strip(),
        "agency_name":      pairs.get("발주기관", "").strip(),
        "open_datetime":    _parse_dt(pairs.get("개찰일시", "")),
        "base_amount":      _parse_amount(pairs.get("기초금액", "")),
        "estimated_amount": _parse_amount(pairs.get("추정가격", "")),
        "min_bid_rate":     _parse_rate(pairs.get("낙찰하한율", "")),
        "preset_amount":    _parse_amount(pairs.get("예정가격", "")),
        "yega_ratio":       yega_ratio,
        "net_cost":         _parse_amount(pairs.get("순공사원가", "")),
        "a_value":          _parse_amount(pairs.get("A값", "")),
    }


def _parse_yega(html: str) -> list:
    rows = []
    yega_match = re.search(r'id="multispare_list_num"(.*?)</tbody>', html, re.DOTALL)
    if not yega_match:
        return rows

    for tr in re.finditer(r"<tr([^>]*)>(.*?)</tr>", yega_match.group(1), re.DOTALL):
        tr_attrs = tr.group(1)
        tr_inner = tr.group(2)
        cells    = re.findall(r"<td[^>]*>(.*?)</td>", tr_inner, re.DOTALL)
        if len(cells) < 4:
            continue

        # text-orange appears on individual <td> tags, not on <tr> — check full row HTML
        is_selected = "text-orange" in tr_inner
        no_s    = _txt(cells[0])
        amt_s   = _txt(cells[1]).replace(",", "")
        ratio_s = _txt(cells[2])
        pct_s   = _txt(cells[3])

        if not no_s.isdigit():
            continue
        try:
            rows.append({
                "yega_no":        int(no_s),
                "amount":         int(amt_s) if amt_s else None,
                "base_ratio":     float(ratio_s) if ratio_s else None,
                "base_ratio_pct": float(pct_s) if pct_s else None,
                "is_selected":    is_selected,
            })
        except Exception:
            continue
    return rows


def _parse_bid_notice(html: str) -> dict | None:
    pairs: dict[str, str] = {}
    for m in re.finditer(r"<th>([^<]+)</th>\s*<td[^>]*>(.*?)</td>", html, re.DOTALL):
        key = m.group(1).strip()
        val = _txt(m.group(2)).strip()
        pairs[key] = val
    if not pairs:
        return None

    yega_method   = pairs.get("예가방법", "")
    yega_draw_cnt = yega_total_cnt = None
    m_yega = re.search(r"복수예가:(\d+)[^/]*/(\d+)", yega_method)
    if m_yega:
        yega_draw_cnt  = int(m_yega.group(1))
        yega_total_cnt = int(m_yega.group(2))

    yega_rmin = yega_rmax = None
    raw_range = pairs.get("예가변동폭", "")
    m_range = re.search(r"(-?\d+)\s*~\s*[+\-]?(\d+)", raw_range)
    if m_range:
        yega_rmin = int(m_range.group(1))
        yega_rmax = int(m_range.group(2))

    return {
        "announcement_no":  re.sub(r"-\d+$", "", pairs.get("공고번호", "").strip()),
        "industry":         pairs.get("업종", "").strip(),
        "region":           pairs.get("지역", "").strip(),
        "agency_name":      (pairs.get("수요기관", "") or pairs.get("발주기관", "")).strip(),
        "yega_method":      yega_method,
        "yega_draw_count":  yega_draw_cnt,
        "yega_total_count": yega_total_cnt,
        "yega_range_min":   yega_rmin,
        "yega_range_max":   yega_rmax,
        "min_bid_rate":     _parse_rate(pairs.get("낙찰하한율", "")),
        "contract_method":  pairs.get("계약방법", "").strip(),
        "reg_deadline":     _parse_dt(pairs.get("참가등록마감", "")),
        "bid_deadline":     _parse_dt(pairs.get("투찰마감일시", "")),
        "open_datetime":    _parse_dt(pairs.get("개찰일시", "")),
        "base_amount":      _parse_amount(pairs.get("기초금액", "")),
        "estimated_amount": _parse_amount(pairs.get("추정가격", "")),
        "a_value":          _parse_amount(pairs.get("A값", "")),
    }


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
                    rank            = EXCLUDED.rank,
                    bid_rate        = EXCLUDED.bid_rate,
                    base_ratio      = EXCLUDED.base_ratio,
                    assessment_rate = EXCLUDED.assessment_rate,
                    is_winner       = EXCLUDED.is_winner
            """), {"bid_id": bid_id, **r})
            count += 1
        except Exception as e:
            logger.debug("participants upsert 실패 [%s/%s]: %s", bid_id, r.get("biz_reg_no"), e)
    db.commit()
    return count


def _upsert_bid_header(db: Session, bid_id: str, data: dict) -> None:
    try:
        db.execute(text("""
            INSERT INTO inpo21c_bids
                (inpo21c_bid_id, announcement_no, title, industry, region, agency_name,
                 open_datetime, base_amount, estimated_amount, min_bid_rate,
                 preset_amount, yega_ratio, net_cost, a_value)
            VALUES
                (:bid_id, :announcement_no, :title, :industry, :region, :agency_name,
                 :open_datetime, :base_amount, :estimated_amount, :min_bid_rate,
                 :preset_amount, :yega_ratio, :net_cost, :a_value)
            ON CONFLICT (inpo21c_bid_id) DO UPDATE SET
                announcement_no  = EXCLUDED.announcement_no,
                title            = COALESCE(EXCLUDED.title, inpo21c_bids.title),
                industry         = EXCLUDED.industry,
                region           = EXCLUDED.region,
                agency_name      = EXCLUDED.agency_name,
                open_datetime    = EXCLUDED.open_datetime,
                base_amount      = EXCLUDED.base_amount,
                estimated_amount = EXCLUDED.estimated_amount,
                min_bid_rate     = EXCLUDED.min_bid_rate,
                preset_amount    = EXCLUDED.preset_amount,
                yega_ratio       = EXCLUDED.yega_ratio,
                net_cost         = EXCLUDED.net_cost,
                a_value          = COALESCE(EXCLUDED.a_value, inpo21c_bids.a_value)
        """), {"bid_id": bid_id, **data})
        db.commit()
    except Exception as e:
        logger.debug("bid_header upsert 실패 [%s]: %s", bid_id, e)
        db.rollback()


def _upsert_yega(db: Session, bid_id: str, rows: list) -> int:
    count = 0
    for r in rows:
        try:
            db.execute(text("""
                INSERT INTO inpo21c_yega
                    (inpo21c_bid_id, yega_no, amount, base_ratio, base_ratio_pct, is_selected)
                VALUES
                    (:bid_id, :yega_no, :amount, :base_ratio, :base_ratio_pct, :is_selected)
                ON CONFLICT (inpo21c_bid_id, yega_no) DO UPDATE SET
                    amount         = EXCLUDED.amount,
                    base_ratio     = EXCLUDED.base_ratio,
                    base_ratio_pct = EXCLUDED.base_ratio_pct,
                    is_selected    = EXCLUDED.is_selected
            """), {"bid_id": bid_id, **r})
            count += 1
        except Exception as e:
            logger.debug("yega upsert 실패 [%s/%s]: %s", bid_id, r.get("yega_no"), e)
    db.commit()
    return count


def _upsert_bid_notice(db: Session, bid_id: str, data: dict) -> None:
    try:
        db.execute(text("""
            INSERT INTO inpo21c_bid_notices
                (inpo21c_bid_id, announcement_no, industry, region, agency_name,
                 yega_method, yega_draw_count, yega_total_count,
                 yega_range_min, yega_range_max, min_bid_rate, contract_method,
                 reg_deadline, bid_deadline, open_datetime, base_amount, estimated_amount,
                 a_value, updated_at)
            VALUES
                (:bid_id, :announcement_no, :industry, :region, :agency_name,
                 :yega_method, :yega_draw_count, :yega_total_count,
                 :yega_range_min, :yega_range_max, :min_bid_rate, :contract_method,
                 :reg_deadline, :bid_deadline, :open_datetime, :base_amount, :estimated_amount,
                 :a_value, now())
            ON CONFLICT (inpo21c_bid_id) DO UPDATE SET
                announcement_no  = EXCLUDED.announcement_no,
                yega_method      = EXCLUDED.yega_method,
                yega_draw_count  = EXCLUDED.yega_draw_count,
                yega_total_count = EXCLUDED.yega_total_count,
                yega_range_min   = EXCLUDED.yega_range_min,
                yega_range_max   = EXCLUDED.yega_range_max,
                min_bid_rate     = EXCLUDED.min_bid_rate,
                open_datetime    = EXCLUDED.open_datetime,
                base_amount      = COALESCE(EXCLUDED.base_amount, inpo21c_bid_notices.base_amount),
                estimated_amount = COALESCE(EXCLUDED.estimated_amount, inpo21c_bid_notices.estimated_amount),
                a_value          = COALESCE(EXCLUDED.a_value, inpo21c_bid_notices.a_value),
                updated_at       = now()
        """), {"bid_id": bid_id, **data})
        db.commit()
    except Exception as e:
        logger.debug("bid_notice upsert 실패 [%s]: %s", bid_id, e)
        db.rollback()


def _get_valid_cookie(settings) -> str | None:
    import os
    from app.config import get_settings as _gs

    cookie = getattr(settings, "inpo21c_cookie", "")
    if cookie and check_cookie_valid(cookie):
        return cookie

    logger.info("inpo21c 쿠키 만료 — 자동 로그인 시도")
    uid = getattr(settings, "inpo21c_id", "")
    pw  = getattr(settings, "inpo21c_pw", "")
    new_c = auto_login(uid, pw)
    if new_c:
        os.environ["INPO21C_COOKIE"] = new_c
        _gs.cache_clear()
        logger.info("inpo21c 쿠키 자동 갱신 완료")
        return new_c

    logger.error("inpo21c 자동 로그인 실패 — INPO21C_ID/PW 확인 필요")
    return None


def collect_inpo21c(db: Session, max_pages: int = 100) -> dict:
    """
    inpo21c 낙찰 목록을 순회하며 세 가지 데이터를 함께 수집:
      1) 전 참여자 (inpo21c_participants) — 낙쳀업체(1순위) 포함 버그 수정
      2) 복수예가 15개 분포 (inpo21c_yega)
      3) 공고 헤더 메타데이터 (inpo21c_bids) — 나라장터 공고번호 포함
    division=1,2,3 (맞춤설정 필터) 모두 순회하여 커버리지 확대.
    """
    from app.config import get_settings
    settings = get_settings()
    _started = time.time()

    cookie = _get_valid_cookie(settings)
    if not cookie:
        _prog_done(error="자동 로그인 실패 — INPO21C_ID/PW 확인 또는 INPO21C_COOKIE 수동 갱신 필요")
        _record_log(db, "inpo21c_daily", 0, 1,
                    time.time() - _started,
                    error_summary="자동 로그인 실패",
                    detail={"source": "inpo21c.net", "error": "auto_login failed"})
        return {
            "bids": 0, "participants": 0, "yega": 0, "skipped": 0,
            "cookie_valid": False,
            "error": "자동 로그인 실패 — INPO21C_ID/PW 확인 또는 INPO21C_COOKIE 수동 갱신 필요",
        }

    _ensure_tables(db)
    _prog_start("division", max_pages)

    # 각 테이블별 기존 수집 여부를 독립적으로 추적
    existing_parts  = {r[0] for r in db.execute(text("SELECT DISTINCT inpo21c_bid_id FROM inpo21c_participants")).fetchall()}
    existing_bids   = {r[0] for r in db.execute(text("SELECT inpo21c_bid_id FROM inpo21c_bids")).fetchall()}
    existing_yega   = {r[0] for r in db.execute(text("SELECT DISTINCT inpo21c_bid_id FROM inpo21c_yega")).fetchall()}

    total_bids = total_participants = total_yega = skipped = 0
    _total_steps = 3 * max_pages

    try:
        for di, division in enumerate((1, 2, 3), start=1):
            for page in range(1, max_pages + 1):
                _step = (di - 1) * max_pages + page
                _prog_page(page, _step / _total_steps * 98)

                page_items = list(dict.fromkeys(_get_bid_ids(page, cookie, division)))
                if not page_items:
                    break

                for bid_id, list_title in page_items:
                    needs_parts  = bid_id not in existing_parts
                    needs_header = bid_id not in existing_bids
                    needs_yega   = bid_id not in existing_yega

                    if not needs_parts and not needs_header and not needs_yega:
                        skipped += 1
                        _prog_add(skipped=1)
                        continue

                    detail_url  = f"{BASE}/suc/view/con/{bid_id}"
                    detail_html = _fetch(detail_url, cookie, referer=f"{BASE}/suc/con?division={division}")

                    if not detail_html:
                        continue

                    if needs_parts:
                        participant_rows = _parse_participants(detail_html)
                        if participant_rows:
                            cnt = _upsert_participants(db, bid_id, participant_rows)
                            total_participants += cnt
                            total_bids += 1
                            _prog_add(bids=1, participants=cnt)
                        existing_parts.add(bid_id)  # 파싱 실패해도 동일 건 재시도 방지

                    if needs_header:
                        header = _parse_bid_header(detail_html)
                        if header:
                            if not header.get("title") and list_title:
                                header["title"] = list_title
                            _upsert_bid_header(db, bid_id, header)
                            existing_bids.add(bid_id)

                    if needs_yega:
                        yega_rows = _parse_yega(detail_html)
                        if yega_rows:
                            yc = _upsert_yega(db, bid_id, yega_rows)
                            total_yega += yc
                            _prog_add(yega=yc)
                        existing_yega.add(bid_id)  # 파싱 실패해도 동일 건 재시도 방지

                    time.sleep(0.5)

        _prog_done()
    except Exception as exc:
        _prog_done(error=str(exc))
        _record_log(db, "inpo21c_daily", total_bids, 1,
                    time.time() - _started,
                    error_summary=str(exc)[:500],
                    detail={"source": "inpo21c.net/suc", "max_pages": max_pages,
                            "bids": total_bids, "participants": total_participants,
                            "yega": total_yega, "skipped": skipped})
        raise

    logger.info(
        "inpo21c 수집 완료: %d건 공고, %d명 참여자, %d개 예가, %d건 스킵",
        total_bids, total_participants, total_yega, skipped,
    )
    _record_log(db, "inpo21c_daily", total_bids, 0,
                time.time() - _started,
                detail={"source": "inpo21c.net/suc", "label": "전참여자+복수예가 (맞춤설정)",
                        "endpoint": "/suc/con", "api_base": "https://infose.info21c.net",
                        "max_pages": max_pages, "bids": total_bids,
                        "participants": total_participants, "yega": total_yega,
                        "skipped": skipped})
    return {
        "bids":         total_bids,
        "participants": total_participants,
        "yega":         total_yega,
        "skipped":      skipped,
        "cookie_valid": True,
    }


def _get_bid_ids_national(page: int, cookie: str) -> list[tuple[str, str]]:
    """division 없이 전체 낙찰 목록에서 (bid_id, title) 수집 (전국 범위)."""
    html = _fetch(f"{BASE}/suc/con?page={page}", cookie)
    results = []
    for m in re.finditer(
        r'/suc/view/con/([^"]+)"[^>]*class="list_link constnm_link">([^<]*)',
        html,
    ):
        bid_id = m.group(1).strip()
        title  = m.group(2).strip()
        results.append((bid_id, title))
    # fallback: 타이틀 없이 ID만 있는 경우
    if not results:
        results = [(m.group(1), "") for m in re.finditer(r'/suc/view/con/([^"]+)"', html)]
    return results


def collect_inpo21c_national(db: Session, max_pages: int = 50) -> dict:
    """
    division 필터 없이 전국 낙찰 결과 수집.

    기존 collect_inpo21c는 맞춤설정(division 1~3)만 순회하여 84개 기관에 그쳤음.
    이 함수는 /suc/con?page=X (division 미지정)로 전국 결과에 접근하여 커버리지 확대.
    연간 발주 5억 이내 소규모 기관 포함 전국 낙찰 데이터 수집.
    """
    from app.config import get_settings
    settings = get_settings()
    _started = time.time()

    cookie = _get_valid_cookie(settings)
    if not cookie:
        _record_log(db, "inpo21c_national", 0, 1,
                    time.time() - _started,
                    error_summary="자동 로그인 실패",
                    detail={"source": "inpo21c.net", "error": "auto_login failed"})
        return {
            "bids": 0, "participants": 0, "yega": 0, "skipped": 0,
            "cookie_valid": False,
            "error": "자동 로그인 실패 — INPO21C_ID/PW 확인 또는 INPO21C_COOKIE 수동 갱신 필요",
        }

    _ensure_tables(db)
    _prog_start("national", max_pages)

    existing_parts = {r[0] for r in db.execute(text("SELECT DISTINCT inpo21c_bid_id FROM inpo21c_participants")).fetchall()}
    existing_bids  = {r[0] for r in db.execute(text("SELECT inpo21c_bid_id FROM inpo21c_bids")).fetchall()}
    existing_yega  = {r[0] for r in db.execute(text("SELECT DISTINCT inpo21c_bid_id FROM inpo21c_yega")).fetchall()}

    total_bids = total_participants = total_yega = skipped = empty_pages = 0

    try:
        for page in range(1, max_pages + 1):
            _prog_page(page, page / max_pages * 98)

            page_items = list(dict.fromkeys(_get_bid_ids_national(page, cookie)))
            if not page_items:
                empty_pages += 1
                if empty_pages >= 3:
                    break
                continue
            empty_pages = 0

            for bid_id, list_title in page_items:
                needs_parts  = bid_id not in existing_parts
                needs_header = bid_id not in existing_bids
                needs_yega   = bid_id not in existing_yega

                if not needs_parts and not needs_header and not needs_yega:
                    skipped += 1
                    _prog_add(skipped=1)
                    continue

                detail_html = _fetch(f"{BASE}/suc/view/con/{bid_id}", cookie, referer=f"{BASE}/suc/con")
                if not detail_html:
                    continue

                if needs_parts:
                    rows = _parse_participants(detail_html)
                    if rows:
                        cnt = _upsert_participants(db, bid_id, rows)
                        total_participants += cnt
                        total_bids += 1
                        _prog_add(bids=1, participants=cnt)
                    existing_parts.add(bid_id)  # 파싱 실패해도 동일 건 재시도 방지

                if needs_header:
                    header = _parse_bid_header(detail_html)
                    if header:
                        # 상세 페이지에 공고명 없으면 목록 페이지 타이틀 사용
                        if not header.get("title") and list_title:
                            header["title"] = list_title
                        _upsert_bid_header(db, bid_id, header)
                        existing_bids.add(bid_id)

                if needs_yega:
                    yega_rows = _parse_yega(detail_html)
                    if yega_rows:
                        yc = _upsert_yega(db, bid_id, yega_rows)
                        total_yega += yc
                        _prog_add(yega=yc)
                    existing_yega.add(bid_id)  # 파싱 실패해도 동일 건 재시도 방지

                time.sleep(0.5)

        _prog_done()
    except Exception as exc:
        _prog_done(error=str(exc))
        _record_log(db, "inpo21c_national", total_bids, 1,
                    time.time() - _started,
                    error_summary=str(exc)[:500],
                    detail={"source": "inpo21c.net/suc", "max_pages": max_pages,
                            "bids": total_bids, "participants": total_participants,
                            "yega": total_yega, "skipped": skipped})
        raise

    logger.info(
        "inpo21c 전국 수집 완료: %d건 공고, %d명 참여자, %d개 예가, %d건 스킵",
        total_bids, total_participants, total_yega, skipped,
    )
    _record_log(db, "inpo21c_national", total_bids, 0,
                time.time() - _started,
                detail={"source": "inpo21c.net/suc", "label": "전참여자+복수예가 (전국)",
                        "endpoint": "/suc/con", "api_base": "https://infose.info21c.net",
                        "max_pages": max_pages, "bids": total_bids,
                        "participants": total_participants, "yega": total_yega,
                        "skipped": skipped})
    return {
        "bids":         total_bids,
        "participants": total_participants,
        "yega":         total_yega,
        "skipped":      skipped,
        "cookie_valid": True,
    }


def collect_bid_notices_inpo21c(db: Session, max_pages: int = 5) -> dict:
    """
    입찰공고 중 목록(/bid/con)에서 개찰 전 사전정보 수집.

    개선 사항:
      - division=1,2,3 전체 수집 (기존: division=1만)
      - A값 없는 기존 공고 재수집 (A값 발표 지연 대응)
      - 수집 완료 후 bids 테이블 자동 동기화
    """
    from app.config import get_settings
    settings = get_settings()
    _started = time.time()

    cookie = _get_valid_cookie(settings)
    if not cookie:
        _record_log(db, "inpo21c_notices", 0, 1,
                    time.time() - _started,
                    error_summary="자동 로그인 실패",
                    detail={"source": "inpo21c.net", "error": "auto_login failed"})
        return {"notices": 0, "skipped": 0, "cookie_valid": False, "error": "로그인 실패"}

    _ensure_tables(db)

    # a_value가 있는 건 = 완전 수집 완료 → 스킵
    # a_value가 없는 건 = 재수집 대상 (A값 발표 대기 중일 수 있음)
    existing_complete = {r[0] for r in db.execute(
        text("SELECT inpo21c_bid_id FROM inpo21c_bid_notices WHERE a_value IS NOT NULL")
    ).fetchall()}

    total_notices = skipped = rescrape = 0
    processed_this_run: set[str] = set()

    for division in (1, 2, 3):
        for page in range(1, max_pages + 1):
            html    = _fetch(f"{BASE}/bid/con?division={division}&page={page}", cookie)
            bid_ids = list(dict.fromkeys(re.findall(r"/bid/view/con/([^\"]+)\"", html)))
            if not bid_ids:
                break

            for bid_id in bid_ids:
                # 이미 완전 수집됐거나 이번 실행에서 처리한 건 스킵
                if bid_id in existing_complete or bid_id in processed_this_run:
                    skipped += 1
                    continue

                detail_url  = f"{BASE}/bid/view/con/{bid_id}"
                detail_html = _fetch(detail_url, cookie,
                                     referer=f"{BASE}/bid/con?division={division}")
                notice_data = _parse_bid_notice(detail_html)
                if notice_data:
                    is_rescrape = db.execute(
                        text("SELECT 1 FROM inpo21c_bid_notices WHERE inpo21c_bid_id=:id"),
                        {"id": bid_id},
                    ).fetchone() is not None
                    _upsert_bid_notice(db, bid_id, notice_data)
                    total_notices += 1
                    if is_rescrape:
                        rescrape += 1
                    if notice_data.get("a_value"):
                        existing_complete.add(bid_id)

                processed_this_run.add(bid_id)
                time.sleep(0.3)

    # 수집 완료 후 bids 테이블 자동 동기화
    sync_stats: dict = {}
    try:
        from app.collector.service import sync_inpo21c_notices_to_bids
        sync_stats = sync_inpo21c_notices_to_bids(db)
    except Exception as e:
        logger.warning("notices→bids 자동 동기화 실패: %s", e)

    logger.info(
        "inpo21c 입찰공고 수집 완료: %d건 신규/재수집(%d재수집), %d건 스킵, 동기화=%s",
        total_notices, rescrape, skipped, sync_stats,
    )
    _record_log(db, "inpo21c_notices", total_notices, 0,
                time.time() - _started,
                detail={"source": "inpo21c.net/bid", "label": "입찰공고 사전정보",
                        "endpoint": "/bid/con", "divisions": "1,2,3",
                        "max_pages": max_pages, "notices": total_notices,
                        "rescrape": rescrape, "skipped": skipped,
                        "sync": sync_stats})
    return {
        "notices":      total_notices,
        "rescrape":     rescrape,
        "skipped":      skipped,
        "sync":         sync_stats,
        "cookie_valid": True,
    }


def rescrape_inpo21c_titles(db: Session, max_pages: int = 100) -> dict:
    """
    title이 없는 inpo21c_bids 레코드를 목록 페이지 순회로 보완.

    상세 페이지에는 공고명 필드가 없으므로, 목록 페이지의
    <a class="list_link constnm_link"> 텍스트에서 타이틀을 추출한다.
    타이틀 확보 후 sync_inpo21c_to_bids로 bids 테이블 신규 등록까지 연계.
    """
    from app.config import get_settings
    settings = get_settings()
    _started = time.time()

    cookie = _get_valid_cookie(settings)
    if not cookie:
        return {"updated": 0, "inserted": 0, "error": "로그인 실패", "cookie_valid": False}

    _ensure_tables(db)

    # title이 없는 bid_id 세트 로드
    no_title_ids = {
        r[0] for r in db.execute(text("""
            SELECT inpo21c_bid_id FROM inpo21c_bids
            WHERE title IS NULL OR title = ''
        """)).fetchall()
    }

    if not no_title_ids:
        return {"updated": 0, "inserted": 0, "duration_sec": 0.1, "cookie_valid": True}

    updated = 0
    empty_pages = 0

    for page in range(1, max_pages + 1):
        page_items = _get_bid_ids_national(page, cookie)
        if not page_items:
            empty_pages += 1
            if empty_pages >= 3:
                break
            continue
        empty_pages = 0

        for bid_id, title in page_items:
            if bid_id in no_title_ids and title:
                try:
                    db.execute(text("""
                        UPDATE inpo21c_bids SET title = :title
                        WHERE inpo21c_bid_id = :bid_id
                    """), {"title": title, "bid_id": bid_id})
                    db.commit()
                    no_title_ids.discard(bid_id)
                    updated += 1
                except Exception as e:
                    db.rollback()
                    logger.warning("title 업데이트 실패 [%s]: %s", bid_id, e)

        if not no_title_ids:
            break  # 모두 채워짐

    # 타이틀 확보 후 bids INSERT 시도
    inserted = 0
    if updated > 0:
        from app.collector.service import sync_inpo21c_to_bids
        result = sync_inpo21c_to_bids(db)
        inserted = result.get("inserted_new_from_inpo21c", 0)

    logger.info("inpo21c title 재스크래핑(목록): updated=%d, inserted=%d, remaining=%d",
                updated, inserted, len(no_title_ids))
    return {
        "updated": updated,
        "inserted": inserted,
        "remaining_no_title": len(no_title_ids),
        "duration_sec": round(time.time() - _started, 1),
        "cookie_valid": True,
    }