from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generator

import httpx
from loguru import logger

from app.config import get_settings

_BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
_RESULTS_URL = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
_PRE_SPEC_URL = "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
_CONTRACT_URL = "https://apis.data.go.kr/1230000/ao/CntrctInfoService"
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
    construction_work_div: str | None = None  # 공사분류 (cnstrtnWorkDivNm)
    joint_supply_bid: str | None = None       # 공동수급협정입찰여부 (cmmnSpldmdAgrmntBidYn)
    participant_limit: str | None = None      # 참가제한여부 (prtcptLmttYn)


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


@dataclass
class BidParticipant:
    """개찰완료 전참여자 항목 (getOpengResultListInfoOpengCompt)"""

    announcement_no: str
    bid_ntce_ord: str        # 입찰공고차수
    rank: int | None         # 개찰순위
    competitor_name: str
    biz_reg_no: str | None
    bid_amount: int | None
    bid_rate: float | None   # 투찰률 (기초금액 대비)
    is_winner: bool
    draw_no1: int | None     # 추첨번호1 (복수예가 추첨 번호)
    draw_no2: int | None     # 추첨번호2
    bid_dt: str | None       # 투찰일시


@dataclass
class BidOpeningItem:
    """개찰결과 목록 항목 (getOpengResultListInfoCnstwk)"""

    announcement_no: str
    announcement_name: str
    participant_count: int | None   # 참가업체수
    bid_open_dt: str | None         # 개찰일시
    progress_code: str | None       # 진행구분코드명 (낙찰, 유찰 등)
    has_yega_file: str | None       # 예비가격파일존재여부 (Y/N)
    agency_name: str | None


@dataclass
class BidYegaItem:
    """예비가격 상세 항목 (getOpengResultListInfoCnstwkPreparPcDetail)"""

    announcement_no: str
    base_amount: int | None         # 기초금액
    estimated_price: int | None     # 예정가격
    yega_total: int | None          # 총예가건수
    yega_no: int | None             # 복수예가순번 (1~15)
    yega_price: int | None          # 기초예정가격 (해당 순번의 금액)
    is_selected: bool               # 추첨여부 (Y=선택됨)
    draw_count: int | None          # 추첨횟수
    bid_open_dt: str | None         # 실개찰일시


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

    def get_opening_results(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """개찰결과 공사 목록 조회 (getOpengResultListInfoCnstwk)
        참가업체수, 예비가격파일존재여부 등 개찰 메타 정보."""
        return self._get_results(
            "getOpengResultListInfoCnstwk",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    def get_all_participants(
        self,
        bid_ntce_no: str,
        bid_ntce_ord: str = "000",
        bid_clsfc_no: str = "0",
        rbid_no: str = "000",
        num_of_rows: int = 200,
    ) -> dict:
        """개찰완료 전참여자 조회 (getOpengResultListInfoOpengCompt).
        낙찰자 포함 전 투찰 업체의 투찰금액, 투찰률, 추첨번호를 반환."""
        return self._get_results(
            "getOpengResultListInfoOpengCompt",
            {
                "bidNtceNo": bid_ntce_no,
                "bidNtceOrd": bid_ntce_ord,
                "bidClsfcNo": bid_clsfc_no,
                "rbidNo": rbid_no,
                "pageNo": 1,
                "numOfRows": num_of_rows,
            },
        )

    def get_yega_detail(
        self,
        bid_ntce_no: str,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        num_of_rows: int = 50,
    ) -> dict:
        """개찰결과 예비가격 상세 조회 (getOpengResultListInfoCnstwkPreparPcDetail).
        복수예가 15개 순번별 금액 + 추첨 여부."""
        return self._get_results(
            "getOpengResultListInfoCnstwkPreparPcDetail",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "bidNtceNo": bid_ntce_no,
                "pageNo": 1,
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
            construction_work_div=item.get("cnstrtnWorkDivNm"),
            joint_supply_bid=item.get("cmmnSpldmdAgrmntBidYn"),
            participant_limit=item.get("prtcptLmttYn"),
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

    @staticmethod
    def _parse_bid_participant(item: dict) -> "BidParticipant":
        """getOpengResultListInfoOpengCompt 응답 파싱 — 전참여자."""
        def _si(v):
            try: return int(str(v).replace(",", ""))
            except: return None
        def _sf(v):
            try: return float(v)
            except: return None
        def _rate(v):
            r = _sf(v)
            if r is None: return None
            return r / 100 if r > 1.5 else r

        rank_raw = _si(item.get("opengRank") or item.get("opengRnk"))
        # 낙찰자 판별: 개찰결과구분명="낙찰" 또는 순위=1 (getOpengResultListInfoOpengCompt)
        rslt_nm = str(item.get("opengRsltDivNm", "")).strip()
        is_win = rslt_nm in ("낙찰", "최종낙찰") or (rank_raw == 1 and rslt_nm not in ("개찰완료",))
        # getOpengResultListInfoOpengCompt 실제 필드명
        return BidParticipant(
            announcement_no=item.get("bidNtceNo", ""),
            bid_ntce_ord=str(item.get("bidNtceOrd", "000")),
            rank=rank_raw,
            competitor_name=(
                item.get("prcbdrNm") or item.get("corpNm") or item.get("bidwinnrNm", "")
            ),
            biz_reg_no=(
                item.get("prcbdrBizno") or item.get("bizRegNo") or item.get("bidwinnrBizno")
            ),
            bid_amount=_si(
                item.get("bidprcAmt") or item.get("bidAmt") or item.get("sucsfbidAmt")
            ),
            bid_rate=_rate(
                item.get("bidprcrt") or item.get("bidrlRt") or item.get("sucsfbidRate")
            ),
            is_winner=is_win,
            draw_no1=_si(item.get("drwtNo1") or item.get("rcmdtnNo1")),
            draw_no2=_si(item.get("drwtNo2") or item.get("rcmdtnNo2")),
            bid_dt=item.get("bidprcDt") or item.get("bidDt"),
        )

    @staticmethod
    def _parse_opening_item(item: dict) -> "BidOpeningItem":
        """getOpengResultListInfoCnstwk 응답 파싱."""
        def _si(v):
            try: return int(str(v).replace(",", ""))
            except: return None
        return BidOpeningItem(
            announcement_no=item.get("bidNtceNo", ""),
            announcement_name=item.get("bidNtceNm", ""),
            participant_count=_si(item.get("prtcptnAmt") or item.get("prticCnt")),
            bid_open_dt=item.get("opengDt"),
            progress_code=item.get("prgrssStatDivNm"),
            has_yega_file=item.get("prearPcFileExistYn"),
            agency_name=item.get("ntceInsttNm"),
        )

    @staticmethod
    def _parse_yega_item(item: dict) -> "BidYegaItem":
        """getOpengResultListInfoCnstwkPreparPcDetail 응답 파싱.
        실제 필드명: compnoRsrvtnPrceSno(순번), bssamt(기초금액), bsisPlnprc(기초예정가),
                    plnprc(예정가격), totRsrvtnPrceNum(총예가수), drwtYn(추첨여부), drwtNum(추첨횟수).
        """
        def _si(v):
            try: return int(str(v).replace(",", ""))
            except: return None
        return BidYegaItem(
            announcement_no=item.get("bidNtceNo", ""),
            base_amount=_si(item.get("bssamt") or item.get("bssAmt")),
            estimated_price=_si(item.get("plnprc") or item.get("presmptPrce")),
            yega_total=_si(item.get("totRsrvtnPrceNum") or item.get("totPrearPcCnt")),
            yega_no=_si(item.get("compnoRsrvtnPrceSno") or item.get("mltiPrearPcOdr")),
            yega_price=_si(item.get("bsisPlnprc") or item.get("bssPrearPc")),
            is_selected=str(item.get("drwtYn") or item.get("priceChosYn", "N")).upper() == "Y",
            draw_count=_si(item.get("drwtNum") or item.get("chosNmpr")),
            bid_open_dt=item.get("rlOpengDt") or item.get("rlaOpengDt"),
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

    def paginate_opening_results(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
    ) -> Generator[list["BidOpeningItem"], None, None]:
        """개찰결과 목록 전체 페이지 순회 (getOpengResultListInfoCnstwk)."""
        num_of_rows = _MAX_ROWS
        page_no = 1
        while True:
            raw = self.get_opening_results(inqry_bgn_dt, inqry_end_dt, inqry_div, page_no, num_of_rows)
            items_raw = self._extract_items(raw)
            if not items_raw:
                break
            yield [self._parse_opening_item(item) for item in items_raw]
            total = self._extract_total_count(raw)
            if page_no * num_of_rows >= total:
                break
            page_no += 1

    def get_participants_for_bid(self, announcement_no: str) -> list["BidParticipant"]:
        """입찰공고번호로 개찰완료 전참여자 목록 조회."""
        raw = self.get_all_participants(announcement_no)
        items_raw = self._extract_items(raw)
        return [self._parse_bid_participant(item) for item in items_raw]

    def get_yega_for_bid(
        self, announcement_no: str, inqry_bgn_dt: str, inqry_end_dt: str
    ) -> list["BidYegaItem"]:
        """입찰공고번호로 예비가격 상세 목록 조회."""
        raw = self.get_yega_detail(announcement_no, inqry_bgn_dt, inqry_end_dt)
        items_raw = self._extract_items(raw)
        return [self._parse_yega_item(item) for item in items_raw]

    # ------------------------------------------------------------------ #
    # 사전규격 API (HrcspSsstndrdInfoService)                            #
    # ------------------------------------------------------------------ #

    def get_pre_spec_list(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """사전규격 공사 목록 조회 (getPublicPrcureThngInfoCnstwk)"""
        return self._call(
            _PRE_SPEC_URL,
            "getPublicPrcureThngInfoCnstwk",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDt": inqry_bgn_dt,
                "inqryEndDt": inqry_end_dt,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    def paginate_pre_spec(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
    ) -> Generator[list[dict], None, None]:
        """사전규격 전체 페이지 순회"""
        num_of_rows = _MAX_ROWS
        page_no = 1
        while True:
            raw = self.get_pre_spec_list(inqry_bgn_dt, inqry_end_dt, inqry_div, page_no, num_of_rows)
            items = self._extract_items(raw)
            if not items:
                break
            yield items
            total = self._extract_total_count(raw)
            if page_no * num_of_rows >= total:
                break
            page_no += 1

    # ------------------------------------------------------------------ #
    # 계약정보 API (CntrctInfoService)                                   #
    # ------------------------------------------------------------------ #

    def get_contract_list(
        self,
        inqry_bgn_date: str,
        inqry_end_date: str,
        inqry_div: int = 1,
        page_no: int = 1,
        num_of_rows: int = _MAX_ROWS,
    ) -> dict:
        """나라장터 검색조건에 의한 계약현황 공사조회 (getCntrctInfoListCnstwkPPSSrch)"""
        return self._call(
            _CONTRACT_URL,
            "getCntrctInfoListCnstwkPPSSrch",
            {
                "inqryDiv": inqry_div,
                "inqryBgnDate": inqry_bgn_date,
                "inqryEndDate": inqry_end_date,
                "pageNo": page_no,
                "numOfRows": num_of_rows,
            },
        )

    def paginate_contracts(
        self,
        inqry_bgn_date: str,
        inqry_end_date: str,
        inqry_div: int = 1,
    ) -> Generator[list[dict], None, None]:
        """계약현황 전체 페이지 순회"""
        num_of_rows = _MAX_ROWS
        page_no = 1
        while True:
            raw = self.get_contract_list(inqry_bgn_date, inqry_end_date, inqry_div, page_no, num_of_rows)
            items = self._extract_items(raw)
            if not items:
                break
            yield items
            total = self._extract_total_count(raw)
            if page_no * num_of_rows >= total:
                break
            page_no += 1

    def paginate_scsbid_pps_search(
        self,
        inqry_bgn_dt: str,
        inqry_end_dt: str,
        inqry_div: int = 1,
        num_of_rows: int = 999,
    ) -> Generator[list[dict], None, None]:
        """getScsbidListSttusCnstwkPPSSrch 전체 페이지 순회 — 낙찰결과 고급검색.
        raw dict 리스트를 yield (파싱 없이 원시 반환)."""
        page_no = 1
        while True:
            raw = self._get_results(
                "getScsbidListSttusCnstwkPPSSrch",
                {
                    "inqryDiv": inqry_div,
                    "inqryBgnDt": inqry_bgn_dt,
                    "inqryEndDt": inqry_end_dt,
                    "pageNo": page_no,
                    "numOfRows": num_of_rows,
                    "type": "json",
                },
            )
            items = self._extract_items(raw)
            if not items:
                break
            yield items
            total = self._extract_total_count(raw)
            if page_no * num_of_rows >= total:
                break
            page_no += 1
