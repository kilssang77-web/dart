"""G2B 과거 데이터 백필 — 30일 청크 단위 수집 + DB 진행 상황 저장."""
from __future__ import annotations

import time
import threading
from datetime import date, datetime, timedelta

from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import text

_STOP_EVENT: threading.Event = threading.Event()
_CHUNK_DAYS = 30


def _ensure_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS backfill_jobs (
            id              SERIAL PRIMARY KEY,
            job_name        VARCHAR(50)  NOT NULL DEFAULT 'g2b_backfill',
            status          VARCHAR(20)  NOT NULL DEFAULT 'running',
            start_date      DATE         NOT NULL,
            end_date        DATE         NOT NULL,
            current_chunk   DATE,
            total_chunks    INTEGER      DEFAULT 0,
            done_chunks     INTEGER      DEFAULT 0,
            success_count   INTEGER      DEFAULT 0,
            fail_count      INTEGER      DEFAULT 0,
            started_at      TIMESTAMPTZ  DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  DEFAULT NOW(),
            error_msg       TEXT
        )
    """))
    db.commit()


def get_status(db: Session) -> dict:
    _ensure_table(db)
    row = db.execute(text("""
        SELECT id, status, start_date, end_date, current_chunk,
               total_chunks, done_chunks, success_count, fail_count,
               started_at, updated_at, error_msg
        FROM backfill_jobs ORDER BY id DESC LIMIT 1
    """)).fetchone()

    if not row:
        return {"status": "idle", "message": "백필 실행 이력 없음"}

    pct = round(row.done_chunks / max(row.total_chunks, 1) * 100, 1)
    now = datetime.utcnow()
    elapsed = (now - row.started_at.replace(tzinfo=None)).total_seconds() if row.started_at else 0
    eta_sec = (elapsed / max(row.done_chunks, 1)) * (row.total_chunks - row.done_chunks) if row.done_chunks > 0 else None

    return {
        "id": row.id,
        "status": row.status,
        "start_date": str(row.start_date),
        "end_date": str(row.end_date),
        "current_chunk": str(row.current_chunk) if row.current_chunk else None,
        "total_chunks": row.total_chunks,
        "done_chunks": row.done_chunks,
        "progress_pct": pct,
        "success_count": row.success_count,
        "fail_count": row.fail_count,
        "eta_minutes": round(eta_sec / 60, 1) if eta_sec else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "error_msg": row.error_msg,
    }


def request_stop() -> str:
    _STOP_EVENT.set()
    return "백필 중단 요청 완료 — 현재 청크 완료 후 종료됩니다"


def run_backfill(start_year: int = 2016, delay: float = 1.2) -> dict:
    """
    start_year 1월 1일부터 오늘까지 30일 청크로 분할해 G2B 공고+결과 수집.
    이전 미완료 작업이 있으면 이어서 실행.
    """
    from app.config import get_settings
    from app.database import SessionLocal
    from app.collector.client import NarajangterClient
    from app.collector.service import (
        _upsert_agency, _upsert_bid, _upsert_competitor,
        _upsert_bid_result, _record_log,
    )
    from app.models import Bid

    _STOP_EVENT.clear()
    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    start_date = date(start_year, 1, 1)
    end_date = date.today()

    # 청크 목록 생성
    chunks: list[tuple[date, date]] = []
    cursor = start_date
    while cursor < end_date:
        chunk_end = min(cursor + timedelta(days=_CHUNK_DAYS - 1), end_date)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    total = len(chunks)

    # 잡 생성 or 재개
    db0 = SessionLocal()
    try:
        _ensure_table(db0)
        last = db0.execute(text("""
            SELECT id, status, current_chunk, done_chunks
            FROM backfill_jobs
            WHERE status IN ('running','paused','error') AND start_date=:sd
            ORDER BY id DESC LIMIT 1
        """), {"sd": start_date}).fetchone()

        if last and last.current_chunk:
            job_id = last.id
            resume_idx = next(
                (i for i, (cs, _) in enumerate(chunks) if cs >= last.current_chunk), 0
            )
            logger.info("백필 재개: 청크 %d/%d (%s~)", resume_idx, total, last.current_chunk)
            db0.execute(text(
                "UPDATE backfill_jobs SET status='running', updated_at=NOW() WHERE id=:id"
            ), {"id": job_id})
        else:
            row = db0.execute(text("""
                INSERT INTO backfill_jobs
                    (job_name, status, start_date, end_date, total_chunks)
                VALUES ('g2b_backfill','running',:sd,:ed,:tc)
                RETURNING id
            """), {"sd": start_date, "ed": end_date, "tc": total}).fetchone()
            job_id = row[0]
            resume_idx = 0
        db0.commit()
    finally:
        db0.close()

    total_ok = total_ng = 0

    for i, (cs, ce) in enumerate(chunks[resume_idx:], start=resume_idx):
        if _STOP_EVENT.is_set():
            _update_job(job_id, "paused", cs, i, 0, 0)
            logger.info("백필 중단 (청크 %d/%d)", i, total)
            return {"status": "paused", "done": i, "total": total}

        bgn = cs.strftime("%Y%m%d") + "0000"
        end = ce.strftime("%Y%m%d") + "2359"
        chunk_ok = chunk_ng = 0

        db = SessionLocal()
        try:
            # 공고 3종
            for ctype, paginate_fn in [
                ("notice_cnstwk", client.paginate_construction_bids),
                ("notice_servc",  client.paginate_service_bids),
                ("notice_thng",   client.paginate_goods_bids),
            ]:
                try:
                    for page in paginate_fn(bgn, end):
                        for notice in page:
                            try:
                                agency = _upsert_agency(db, notice.agency_name)
                                _upsert_bid(db, notice, agency.id)
                                db.commit()
                                chunk_ok += 1
                            except Exception:
                                db.rollback()
                                chunk_ng += 1
                        time.sleep(delay)
                except Exception as e:
                    logger.warning("백필 공고 실패 [%s %s~%s]: %s", ctype, bgn, end, e)
                    chunk_ng += 1

            # 낙찰결과
            try:
                for page in client.paginate_bid_results(bgn, end):
                    for r in page:
                        try:
                            bid = db.query(Bid).filter(
                                Bid.announcement_no == r.announcement_no
                            ).first()
                            if not bid:
                                continue
                            comp = _upsert_competitor(db, r.competitor_name, r.biz_reg_no)
                            _upsert_bid_result(db, bid.id, comp.id, r)
                            db.commit()
                            chunk_ok += 1
                        except Exception:
                            db.rollback()
                            chunk_ng += 1
                    time.sleep(delay)
            except Exception as e:
                logger.warning("백필 결과 실패 [%s~%s]: %s", bgn, end, e)
                chunk_ng += 1

        finally:
            db.close()

        total_ok += chunk_ok
        total_ng += chunk_ng
        _update_job(job_id, "running", cs, i + 1, chunk_ok, chunk_ng)

        logger.info(
            "백필 %d/%d (%.1f%%) [%s~%s] ok=%d ng=%d",
            i + 1, total, (i + 1) / total * 100, cs, ce, chunk_ok, chunk_ng,
        )

    # 완료
    from app.database import SessionLocal as SL
    db_f = SL()
    try:
        db_f.execute(text(
            "UPDATE backfill_jobs SET status='done', updated_at=NOW() WHERE id=:id"
        ), {"id": job_id})
        db_f.commit()
    finally:
        db_f.close()

    logger.info("백필 완료: 성공=%d 실패=%d", total_ok, total_ng)
    return {"status": "done", "success": total_ok, "fail": total_ng}


def _update_job(job_id: int, status: str, chunk_date: date, done: int, ok: int, ng: int) -> None:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE backfill_jobs
            SET status=:st, current_chunk=:cd, done_chunks=:dc,
                success_count=success_count+:ok, fail_count=fail_count+:ng,
                updated_at=NOW()
            WHERE id=:id
        """), {"st": status, "cd": chunk_date, "dc": done, "ok": ok, "ng": ng, "id": job_id})
        db.commit()
    finally:
        db.close()
