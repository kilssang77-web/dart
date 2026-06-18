from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generator

import httpx
from loguru import logger

from app.config import get_settings

_BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
_RESULTS_URL = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
_MAX_RETRIES = 3
_TIMEOUT = 30.0
_MAX_ROWS = 100


@dataclass
class BidNotice:
    """입찰공고 항목"""

    announcement_no: str
    title: str
    agency_name: str
    base_amount: int | None
    notice_date: str | None
    bid_open_date: str | None
    bid_type: str  # construction / service / goods
    industry_code: str | None = None
    region_code: str | None = None
    bid_close_date: str | None = None    # 투찰마감일시 (bidClseDt)
    estimated_price: int | None = None   # 추정가격 (presmptPrce)
    min_bid_rate: float | None = None    # 낙찰하한율 (sucsfbidLwltRate)
    contract_method: str | None = None   # 계약방법 (cntrctMthNm)
    bid_method: str | None = None        # 입찰방식 (bidMethdNm)


@dataclass
class BidResult:
    """낙찰결과 항목"""

    announcement_no: str
    competitor_name: str
    biz_reg_no: str | None
    bid_amount: int | None
    bid_rate: float | None
    rank: int | None
    is_winner: bool


class NarajangterClient:
    """나라장터 Open API 클라이언트 (공공데이터포털)"""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.g2b_api_key
        if not resolved_key:
            raise ValueError(
                "G2B_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 G2B_API_KEY=<공공데이터포털 인증키>를 추가하세요."
            )
        self._api_key = resolved_key
        self._timeout = _TIMEOUT
        self._max_retries = _MAX_RETRIES

    # ------------------------------------------------------------------ #
    # 공개 조회 메서드                                                     #
    # ------------------------------------------------------------------ #

    def get_construction_bids(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """공사 입찰공고목록 조회 (getBidPblancListInfoCnstwk)"""
        return self._get(
            "getBidPblancListInfoCnstwk",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    def get_service_bids(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """용역 입찰공고목록 조회 (getBidPblancListInfoServc)"""
        return self._get(
            "getBidPblancListInfoServc",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    def get_goods_bids(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """물품 입찰공고목록 조회 (getBidPblancListInfoThng)"""
        return self._get(
            "getBidPblancListInfoThng",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    def get_bid_results(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """낙찰결과목록 조회 — ScsbidInfoService (getScsbidListSttusCnstwk)"""
        return self._get_results(
            "getScsbidListSttusCnstwk",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    # ------------------------------------------------------------------ #
    # 페이지네이션 제너레이터                                               #
    # ------------------------------------------------------------------ #

    def paginate_construction_bids(
        self, inqry_bgn_dt: str, inqry_end_dt: str, **kwargs
    ) -> Generator[list[BidNotice], None, None]:
        """공사 입찰공고 전체 페이지 순회"""
        yield from self._paginate_notices(
            self.get_construction_bids, "construction", inqry_bgn_dt, inqry_end_dt, **kwargs
        )

    def paginate_service_bids(
        self, inqry_bgn_dt: str, inqry_end_dt: str, **kwargs
    ) -> Generator[list[BidNotice], None, None]:
        """용역 입찰공고 전체 페이지 순회"""
        yield from self._paginate_notices(
            self.get_service_bids, "service", inqry_bgn_dt, inqry_end_dt, **kwargs
        )

    def paginate_goods_bids(
        self, inqry_bgn_dt: str, inqry_end_dt: str, **kwargs
    ) -> Generator[list[BidNotice], None, None]:
        """물품 입찰공고 전체 페이지 순회"""
        yield from self._paginate_notices(
            self.get_goods_bids, "goods", inqry_bgn_dt, inqry_end_dt, **kwargs
        )

    def paginate_bid_results(
        self, inqry_bgn_dt: str, inqry_end_dt: str, **kwargs
    ) -> Generator[list[BidResult], None, None]:
        """낙찰결과 전체 페이지 순회"""
        num_of_rows = kwargs.pop("num_of_rows", _MAX_ROWS)
        page_no = 1
        while True:
            raw = self.get_bid_results(
                inqry_bgn_dt, inqry_end_dt, page_no=page_no, num_of_rows=num_of_rows, **kwargs
            )
            items_raw = self._extract_items(raw)
            if not items_raw:
                break
            yield [self._parse_bid_result(item) for item in items_raw]
            total = self._extract_total_count(raw)
            if page_no * num_of_rows >= total:
                break
            page_no += 1

    # ------------------------------------------------------------------ #
    # 파싱 헬퍼                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_items(raw: dict) -> list[dict]:
        """API 응답 body.items 추출 — 직접 배열 또는 items.item 중첩 모두 처리"""
        try:
            body = raw["response"]["body"]
            items_node = body.get("items")
            if not items_node:
                return []
            # 신규 포맷: body.items = [...]
            if isinstance(items_node, list):
                return items_node
            # 구형 포맷: body.items = {"item": [...]} or {"item": {...}}
            if isinstance(items_node, dict):
                item = items_node.get("item")
                if item is None:
                    return []
                return item if isinstance(item, list) else [item]
            return []
        except (KeyError, TypeError):
            return []

    @staticmethod
    def _extract_total_count(raw: dict) -> int:
        try:
            return int(raw["response"]["body"].get("totalCount", 0))
        except (KeyError, TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_notice(item: dict, bid_type: str) -> BidNotice:
        def _safe_int(val: object) -> int | None:
            try:
                return int(str(val).replace(",", ""))
            except (TypeError, ValueError):
                return None

        def _safe_float(val: object) -> float | None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _normalize_rate(val: object) -> float | None:
            r = _safe_float(val)
            if r is None:
                return None
            return r / 100 if r > 1.5 else r

        # 기초금액: asignBdgtAmt(배정예산금액) 우선, 없으면 presmptPrce(추정가격)
        base_amount = _safe_int(item.get("asignBdgtAmt")) or _safe_int(item.get("presmptPrce"))
        estimated_price = _safe_int(item.get("presmptPrce"))

        return BidNotice(
            announcement_no=item.get("bidNtceNo", ""),
            title=item.get("bidNtceNm", ""),
            agency_name=item.get("ntceInsttNm", ""),
            base_amount=base_amount,
            notice_date=item.get("bidNtceDt"),
            bid_open_date=item.get("opengDt"),
            bid_close_date=item.get("bidClseDt"),
            estimated_price=estimated_price,
            min_bid_rate=_normalize_rate(item.get("sucsfbidLwltRate")),
            contract_method=item.get("cntrctMthNm"),
            bid_method=item.get("bidMethdNm"),
            bid_type=bid_type,
            industry_code=item.get("indutyNm") or item.get("prcureThgNm"),
            region_code=item.get("rgstTyNm"),
        )

    @staticmethod
    def _parse_bid_result(item: dict) -> BidResult:
        def _safe_int(val: object) -> int | None:
            try:
                return int(str(val).replace(",", ""))
            except (TypeError, ValueError):
                return None

        def _safe_float(val: object) -> float | None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _normalize_rate(val: object) -> float | None:
            # G2B API sucsfbidRate는 소수형(0.9029)과 퍼센트형(90.29) 혼재
            # 1.5 초과이면 퍼센트형으로 판단해 /100 정규화
            r = _safe_float(val)
            if r is None:
                return None
            return r / 100 if r > 1.5 else r

        # ScsbidInfoService 필드명 매핑 (낙찰자 단건)
        return BidResult(
            announcement_no=item.get("bidNtceNo", ""),
            competitor_name=item.get("bidwinnrNm") or item.get("corpNm", ""),
            biz_reg_no=item.get("bidwinnrBizno") or item.get("bizRegNo"),
            bid_amount=_safe_int(item.get("sucsfbidAmt") or item.get("bidAmt")),
            bid_rate=_normalize_rate(item.get("sucsfbidRate") or item.get("rate")),
            rank=1,  # ScsbidInfoService는 낙찰자(1위)만 반환
            is_winner=True,
        )

    # ------------------------------------------------------------------ #
    # 내부 HTTP                                                            #
    # ------------------------------------------------------------------ #

    def _get(self, endpoint: str, params: dict) -> dict:
        return self._call(_BASE_URL, endpoint, params)

    def _get_results(self, endpoint: str, params: dict) -> dict:
        return self._call(_RESULTS_URL, endpoint, params)

    def _call(self, base_url: str, endpoint: str, params: dict) -> dict:
        url = f"{base_url}/{endpoint}"
        request_params: dict = {
            "serviceKey": self._api_key,
            "type": "json",
            **params,
        }
        last_exc: Exception = RuntimeError("알 수 없는 오류")
        for attempt in range(1, self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, params=request_params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError) as exc:
                last_exc = exc
                logger.warning(
                    "나라장터 API 호출 실패 [{}/{}]: {} — {}",
                    attempt,
                    self._max_retries,
                    endpoint,
                    exc,
                )
                if attempt < self._max_retries:
                    time.sleep(1.0 * attempt)
        raise last_exc

    def _paginate_notices(
        self,
        fetch_fn,
        bid_type: str,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        **kwargs,
    ) -> Generator[list[BidNotice], None, None]:
        num_of_rows = kwargs.pop("num_of_rows", _MAX_ROWS)
        page_no = 1
        while True:
            raw = fetch_fn(
                inqry_bgn_dt, inqry_end_dt, page_no=page_no, num_of_rows=num_of_rows, **kwargs
            )
            items_raw = self._extract_items(raw)
            if not items_raw:
                break
            yield [self._parse_notice(item, bid_type) for item in items_raw]
            total = self._extract_total_count(raw)
            if page_no * num_of_rows >= total:
                break
            page_no += 1
