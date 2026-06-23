"""
한국천문연구원 특일정보 API → kr_holidays 테이블 + Redis 캐시 동기화
엔드포인트: https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo
"""
import json
import logging
import os
from datetime import date
import xml.etree.ElementTree as ET

import asyncpg
import httpx
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_API_BASE = (
    "https://apis.data.go.kr/B090041/openapi"
    "/service/SpcdeInfoService/getRestDeInfo"
)
_API_KEY = os.environ.get("GOV_DATA_API_KEY", "")
# Redis TTL ~13개월 (연간 1회 갱신이므로 넉넉히)
_REDIS_TTL = 86400 * 400


async def _fetch_month(year: int, month: int, client: httpx.AsyncClient) -> list[dict]:
    """단일 연-월 공휴일 목록 조회. 반환: [{"date": date, "name": str}]

    공공데이터포털은 serviceKey를 URL에 직접 포함해야 이중 인코딩을 피함.
    """
    url = (
        f"{_API_BASE}"
        f"?serviceKey={_API_KEY}"
        f"&solYear={year}"
        f"&solMonth={month:02d}"
        f"&numOfRows=30"
    )
    resp = await client.get(url, timeout=15.0)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    result_code = root.findtext(".//resultCode", "")
    if result_code not in ("00", "0000"):
        msg = root.findtext(".//resultMsg", "unknown")
        raise RuntimeError(f"API 오류 [{result_code}] {msg}")

    items = []
    for item in root.findall(".//item"):
        if item.findtext("isHoliday", "N") != "Y":
            continue
        locdate = item.findtext("locdate", "")
        name = item.findtext("dateName", "").strip()
        if len(locdate) == 8:
            try:
                d = date(int(locdate[:4]), int(locdate[4:6]), int(locdate[6:]))
                items.append({"date": d, "name": name})
            except ValueError:
                pass
    return items


async def sync_holidays(
    years: list[int],
    db: asyncpg.Pool,
    redis: redis_lib.Redis,
    force: bool = False,
) -> dict[int, int]:
    """
    지정 연도 공휴일을 API에서 가져와 DB + Redis에 저장.

    force=False (기본): Redis 캐시가 이미 있으면 스킵.
    반환: {year: 저장 건수}
    """
    totals: dict[int, int] = {}

    async with httpx.AsyncClient() as client:
        for year in years:
            if not force:
                cached = await redis.get(f"krx:holidays:{year}")
                if cached:
                    logger.debug(f"[HolidaySync] {year}년 캐시 존재, 스킵")
                    totals[year] = len(json.loads(cached))
                    continue

            holidays: list[dict] = []
            errors = 0
            for month in range(1, 13):
                try:
                    month_data = await _fetch_month(year, month, client)
                    holidays.extend(month_data)
                    logger.debug(f"[HolidaySync] {year}-{month:02d}: {len(month_data)}건")
                except Exception as e:
                    errors += 1
                    logger.warning(f"[HolidaySync] {year}-{month:02d} 오류: {e}")

            if not holidays:
                logger.error(f"[HolidaySync] {year}년 데이터 없음 (오류 {errors}건)")
                totals[year] = 0
                continue

            # DB upsert
            async with db.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany(
                        """
                        INSERT INTO kr_holidays (holiday_date, name)
                        VALUES ($1, $2)
                        ON CONFLICT (holiday_date) DO UPDATE SET name = EXCLUDED.name
                        """,
                        [(h["date"], h["name"]) for h in holidays],
                    )

            # Redis 캐시: krx:holidays:{year} = ["2026-01-01", ...]
            date_strs = sorted(h["date"].isoformat() for h in holidays)
            await redis.set(
                f"krx:holidays:{year}",
                json.dumps(date_strs),
                ex=_REDIS_TTL,
            )

            count = len(holidays)
            totals[year] = count
            logger.info(
                f"[HolidaySync] {year}년 공휴일 {count}건 동기화 완료"
                f" (오류 {errors}건)"
            )

    return totals
