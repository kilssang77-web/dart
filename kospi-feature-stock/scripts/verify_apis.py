"""
API 키 검증 스크립트 — KIS / DART
의존성: httpx (pip install httpx)
"""
import asyncio
import json
import sys
import httpx
from datetime import datetime, timedelta

KIS_APP_KEY    = "PSWLNfXPZnXEGLpnvKJTz8oqn1j1i3sVzN8p"
KIS_APP_SECRET = ("3Q+q0kiDtGLY41OI1IVdVB7tSww74+UX0WRNuuANigM+"
                  "ASS9KTxTCuR9+1Gk/32Tgd+QpwEagqaFQc0rF3Y84u4w0F+"
                  "NX2+SajHsnqnw5wY3JNxSyIYXhfiBC4T0dKsRcEF2wI9S2DS"
                  "vPaX95I80kelUla0D3Q/MrQJ4/8dE2p2pzwe4PAk=")
DART_API_KEY   = "c684ef333fb2e14394ee910611f5d29efec917db"

KIS_BASE  = "https://openapi.koreainvestment.com:9443"
DART_BASE = "https://opendart.fss.or.kr/api"

PASS = "✓"
FAIL = "✗"


async def test_kis_token(client: httpx.AsyncClient) -> dict:
    print("\n[1] KIS OAuth 토큰 발급 테스트")
    try:
        resp = await client.post(
            f"{KIS_BASE}/oauth2/tokenP",
            json={
                "grant_type":  "client_credentials",
                "appkey":      KIS_APP_KEY,
                "appsecret":   KIS_APP_SECRET,
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("access_token"):
            token   = data["access_token"]
            expires = data.get("expires_in", 0)
            print(f"  {PASS} 토큰 발급 성공")
            print(f"     토큰(앞 30자): {token[:30]}...")
            print(f"     만료: {expires}초 ({expires//3600}시간)")
            return {"ok": True, "token": token, "expires_in": expires}
        else:
            print(f"  {FAIL} 발급 실패: HTTP {resp.status_code}")
            print(f"     응답: {json.dumps(data, ensure_ascii=False)[:200]}")
            return {"ok": False, "error": data}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def test_kis_ws_approval(client: httpx.AsyncClient) -> dict:
    print("\n[2] KIS WebSocket Approval Key 발급 테스트")
    try:
        resp = await client.post(
            f"{KIS_BASE}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey":     KIS_APP_KEY,
                "secretkey":  KIS_APP_SECRET,
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("approval_key"):
            key = data["approval_key"]
            print(f"  {PASS} WS Approval Key 발급 성공")
            print(f"     Key(앞 20자): {key[:20]}...")
            return {"ok": True, "approval_key": key}
        else:
            print(f"  {FAIL} 발급 실패: HTTP {resp.status_code}")
            print(f"     응답: {json.dumps(data, ensure_ascii=False)[:200]}")
            return {"ok": False, "error": data}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def test_kis_quote(client: httpx.AsyncClient, token: str) -> dict:
    print("\n[3] KIS 현재가 조회 테스트 (삼성전자 005930)")
    try:
        resp = await client.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "Content-Type":  "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey":        KIS_APP_KEY,
                "appsecret":     KIS_APP_SECRET,
                "tr_id":         "FHKST01010100",
                "custtype":      "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         "005930",
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("rt_cd") == "0":
            out = data.get("output", {})
            print(f"  {PASS} 현재가 조회 성공")
            print(f"     종목: 삼성전자 (005930)")
            print(f"     현재가: {int(out.get('stck_prpr',0)):,}원")
            print(f"     등락률: {out.get('prdy_ctrt','N/A')}%")
            print(f"     거래량: {int(out.get('acml_vol',0)):,}주")
            print(f"     거래대금: {int(out.get('acml_tr_pbmn',0))//100000000:,}억원")
            return {"ok": True, "price": out.get("stck_prpr")}
        else:
            print(f"  {FAIL} 조회 실패: HTTP {resp.status_code} rt_cd={data.get('rt_cd')}")
            print(f"     msg: {data.get('msg1','')}")
            return {"ok": False, "error": data.get("msg1")}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def test_kis_daily_bars(client: httpx.AsyncClient, token: str) -> dict:
    print("\n[4] KIS 일봉 조회 테스트 (삼성전자, 최근 5일)")
    today = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    try:
        resp = await client.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers={
                "Content-Type":  "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey":        KIS_APP_KEY,
                "appsecret":     KIS_APP_SECRET,
                "tr_id":         "FHKST01010100",
                "custtype":      "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         "005930",
                "FID_INPUT_DATE_1":       start,
                "FID_INPUT_DATE_2":       today,
                "FID_PERIOD_DIV_CODE":    "D",
                "FID_ORG_ADJ_PRC":        "0",
            },
            timeout=15,
        )
        data = resp.json()
        rows = data.get("output2", [])
        if resp.status_code == 200 and rows:
            print(f"  {PASS} 일봉 조회 성공 ({len(rows)}개 봉)")
            print(f"     {'날짜':<12} {'시가':>8} {'고가':>8} {'저가':>8} {'종가':>8} {'거래량':>12}")
            print(f"     {'-'*60}")
            for r in rows[:5]:
                d = r.get("stck_bsop_date","")
                o = int(r.get("stck_oprc",0) or 0)
                h = int(r.get("stck_hgpr",0) or 0)
                l = int(r.get("stck_lwpr",0) or 0)
                c = int(r.get("stck_clpr",0) or 0)
                v = int(r.get("acml_vol",0) or 0)
                print(f"     {d:<12} {o:>8,} {h:>8,} {l:>8,} {c:>8,} {v:>12,}")
            return {"ok": True, "rows": len(rows)}
        else:
            print(f"  {FAIL} rt_cd={data.get('rt_cd')} msg={data.get('msg1','')}")
            return {"ok": False}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def test_dart_list(client: httpx.AsyncClient) -> dict:
    print("\n[5] DART 공시 목록 조회 테스트 (오늘/어제)")
    today = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    try:
        resp = await client.get(
            f"{DART_BASE}/list.json",
            params={
                "crtfc_key": DART_API_KEY,
                "bgn_de":    start,
                "end_de":    today,
                "last_reprt_at": "Y",
                "page_no":   1,
                "page_count": 10,
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("status") == "000":
            items = data.get("list", [])
            total = data.get("total_count", 0)
            print(f"  {PASS} 공시 목록 조회 성공")
            print(f"     전체 공시 수: {total:,}건")
            print(f"     최근 공시 (최대 5건):")
            for item in items[:5]:
                dt   = item.get("rcept_dt","")
                corp = item.get("corp_name","")
                title = item.get("report_nm","")[:40]
                code  = item.get("stock_code","")
                print(f"     [{dt}] {corp}({code}) - {title}")
            return {"ok": True, "total": total}
        else:
            print(f"  {FAIL} status={data.get('status')} message={data.get('message','')}")
            return {"ok": False, "error": data.get("message")}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def test_dart_company(client: httpx.AsyncClient) -> dict:
    print("\n[6] DART 기업 정보 조회 테스트 (삼성전자)")
    try:
        resp = await client.get(
            f"{DART_BASE}/company.json",
            params={
                "crtfc_key": DART_API_KEY,
                "stock_code": "005930",
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("status") == "000":
            print(f"  {PASS} 기업 정보 조회 성공")
            print(f"     기업명:   {data.get('corp_name')}")
            print(f"     영문명:   {data.get('corp_name_eng')}")
            print(f"     대표자:   {data.get('ceo_nm')}")
            print(f"     설립일:   {data.get('est_dt')}")
            print(f"     업종:     {data.get('induty_code')}")
            print(f"     홈페이지: {data.get('hm_url')}")
            return {"ok": True}
        else:
            print(f"  {FAIL} status={data.get('status')}")
            return {"ok": False}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def test_kis_supply(client: httpx.AsyncClient, token: str) -> dict:
    print("\n[7] KIS 투자자별 매매동향 조회 (삼성전자, 오늘)")
    today = datetime.now().strftime("%Y%m%d")
    try:
        resp = await client.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
            headers={
                "Content-Type":  "application/json; charset=utf-8",
                "authorization": f"Bearer {token}",
                "appkey":        KIS_APP_KEY,
                "appsecret":     KIS_APP_SECRET,
                "tr_id":         "FHKST01010900",
                "custtype":      "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         "005930",
                "FID_INPUT_DATE_1":       today,
                "FID_INPUT_DATE_2":       today,
                "FID_PERIOD_DIV_CODE":    "D",
            },
            timeout=15,
        )
        data = resp.json()
        rows = data.get("output", [])
        if resp.status_code == 200 and data.get("rt_cd") == "0" and rows:
            r = rows[0]
            print(f"  {PASS} 수급 조회 성공")
            print(f"     외국인 순매수:  {int(r.get('frgn_ntby_qty',0) or 0):>10,}주")
            print(f"     기관   순매수:  {int(r.get('orgn_ntby_qty',0) or 0):>10,}주")
            print(f"     개인   순매수:  {int(r.get('indv_ntby_qty',0) or 0):>10,}주")
            print(f"     프로그램순매수: {int(r.get('pgtr_ntby_qty',0) or 0):>10,}주")
            return {"ok": True}
        else:
            msg = data.get("msg1","")
            print(f"  {FAIL} rt_cd={data.get('rt_cd')} msg={msg}")
            return {"ok": False, "error": msg}
    except Exception as e:
        print(f"  {FAIL} 예외: {e}")
        return {"ok": False, "error": str(e)}


async def main():
    print("=" * 60)
    print(" KOSPI 특징주 시스템 — API 키 검증")
    print(f" 실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = {}
    async with httpx.AsyncClient(timeout=20, verify=True) as client:
        # KIS 토큰
        tok_res = await test_kis_token(client)
        results["kis_token"] = tok_res["ok"]

        token = tok_res.get("token", "")

        # WS Approval Key
        ws_res = await test_kis_ws_approval(client)
        results["kis_ws_approval"] = ws_res["ok"]

        if token:
            # 현재가
            q_res = await test_kis_quote(client, token)
            results["kis_quote"] = q_res["ok"]

            # 일봉
            d_res = await test_kis_daily_bars(client, token)
            results["kis_daily"] = d_res["ok"]

            # 수급
            s_res = await test_kis_supply(client, token)
            results["kis_supply"] = s_res["ok"]
        else:
            print("\n  ⚠  토큰 없음 — 시세/수급 테스트 건너뜀")
            results["kis_quote"]  = False
            results["kis_daily"]  = False
            results["kis_supply"] = False

        # DART
        dart_res = await test_dart_list(client)
        results["dart_list"] = dart_res["ok"]

        corp_res = await test_dart_company(client)
        results["dart_company"] = corp_res["ok"]

    # 최종 결과
    print("\n" + "=" * 60)
    print(" 검증 결과 요약")
    print("=" * 60)
    labels = {
        "kis_token":      "KIS OAuth 토큰",
        "kis_ws_approval":"KIS WS Approval Key",
        "kis_quote":      "KIS 현재가 조회",
        "kis_daily":      "KIS 일봉 조회",
        "kis_supply":     "KIS 수급 조회",
        "dart_list":      "DART 공시 목록",
        "dart_company":   "DART 기업 정보",
    }
    ok_cnt = 0
    for key, label in labels.items():
        ok = results.get(key, False)
        mark = PASS if ok else FAIL
        print(f"  {mark}  {label}")
        if ok:
            ok_cnt += 1

    total = len(labels)
    print(f"\n  결과: {ok_cnt}/{total} 항목 통과")
    if ok_cnt == total:
        print("  → 모든 API 정상. 시스템 기동 준비 완료.")
    elif ok_cnt >= 4:
        print("  → 핵심 API 정상. 일부 기능 제한 가능.")
    else:
        print("  → API 오류 확인 필요.")
    print("=" * 60)
    return ok_cnt == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
