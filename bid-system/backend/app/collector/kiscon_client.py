"""KISCON 건설산업지식정보시스템 API 클라이언트 (공공데이터포털)

API: 국토교통부_건설업체 시공능력평가 현황
URL: http://apis.data.go.kr/1613000/CorpCapbtyEvalInfoService/getCorpCapbtyEvalInfo
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

KISCON_BASE = "http://apis.data.go.kr/1613000/CorpCapbtyEvalInfoService"


@dataclass
class KisconCapItem:
    """시공능력평가 단건 (업종별)"""
    biz_reg_no: str
    corp_name: str
    eval_year: int
    biz_type_cd: str        # 업종코드 (01=토목, 02=건축, 03=토건, 04=산업, 05=조경 …)
    biz_type_name: str      # 업종명
    eval_amount: int        # 시공능력평가액 (원)
    rank_no: Optional[int]  # 해당 업종 순위


@dataclass
class KisconCorpProfile:
    """경쟁사 KISCON 통합 프로필"""
    biz_reg_no: str
    corp_name: str
    eval_year: int
    license_types: list[str] = field(default_factory=list)   # 업종코드 목록
    license_names: list[str] = field(default_factory=list)   # 업종명 목록
    capacity_eval_amount: int = 0                             # 평가액 합계
    main_biz_type: str = ""                                   # 최대 평가액 업종명


class KisconClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.timeout = 30
        self._http = httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def fetch_capacity_eval(
        self,
        biz_reg_no: str,
        eval_year: Optional[int] = None,
    ) -> list[KisconCapItem]:
        """사업자등록번호로 시공능력평가 조회 (업종별 다건 반환)."""
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 50,
            "pageNo": 1,
            "type": "json",
            "bizRegNo": biz_reg_no.replace("-", ""),
        }
        if eval_year:
            params["evalYear"] = str(eval_year)

        raw = self._call(f"{KISCON_BASE}/getCorpCapbtyEvalInfo", params)
        return self._parse_items(raw, biz_reg_no)

    def batch_fetch(
        self,
        biz_reg_nos: list[str],
        eval_year: Optional[int] = None,
        delay: float = 0.3,
    ) -> dict[str, KisconCorpProfile]:
        """복수 업체 배치 조회 → {biz_reg_no: KisconCorpProfile}."""
        results: dict[str, KisconCorpProfile] = {}
        for brn in biz_reg_nos:
            try:
                items = self.fetch_capacity_eval(brn, eval_year)
                if items:
                    results[brn] = self._aggregate(items)
                time.sleep(delay)
            except Exception as exc:
                logger.warning("KISCON 조회 실패 [%s]: %s", brn, exc)
        return results

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _call(self, url: str, params: dict, retries: int = 3) -> dict:
        for attempt in range(retries):
            try:
                resp = self._http.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                if attempt == retries - 1:
                    raise
                time.sleep(1 * (attempt + 1))
                logger.debug("KISCON API 재시도 %d/%d: %s", attempt + 1, retries, exc)
        return {}

    def _parse_items(self, raw: dict, biz_reg_no: str) -> list[KisconCapItem]:
        try:
            body = raw.get("response", {}).get("body", {})
            items_raw = body.get("items", {})
            if not items_raw:
                return []
            items = items_raw.get("item", [])
            if isinstance(items, dict):
                items = [items]
        except Exception:
            return []

        result = []
        for it in items:
            try:
                result.append(KisconCapItem(
                    biz_reg_no=str(it.get("bizRegNo", biz_reg_no)).replace("-", ""),
                    corp_name=str(it.get("corpNm", "")),
                    eval_year=int(it.get("evalYear", 0)),
                    biz_type_cd=str(it.get("bizTypeCd", "")),
                    biz_type_name=str(it.get("bizTypeNm", "")),
                    eval_amount=int(str(it.get("evalAmt", 0)).replace(",", "") or 0),
                    rank_no=int(it["rankNo"]) if it.get("rankNo") else None,
                ))
            except Exception as exc:
                logger.debug("KISCON 항목 파싱 오류: %s — %s", exc, it)
        return result

    @staticmethod
    def _aggregate(items: list[KisconCapItem]) -> KisconCorpProfile:
        """업종별 목록 → 통합 프로필."""
        if not items:
            raise ValueError("빈 항목")

        first = items[0]
        total_amount = sum(i.eval_amount for i in items)
        main_item = max(items, key=lambda i: i.eval_amount)

        return KisconCorpProfile(
            biz_reg_no=first.biz_reg_no,
            corp_name=first.corp_name,
            eval_year=first.eval_year,
            license_types=[i.biz_type_cd for i in items if i.biz_type_cd],
            license_names=[i.biz_type_name for i in items if i.biz_type_name],
            capacity_eval_amount=total_amount,
            main_biz_type=main_item.biz_type_name,
        )
