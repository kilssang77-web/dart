# -*- coding: utf-8 -*-
"""API 검증 v2"""
import asyncio, sys
import httpx
from datetime import datetime, timedelta

KIS_APP_KEY    = "PSWLNfXPZnXEGLpnvKJTz8oqn1j1i3sVzN8p"
KIS_APP_SECRET = ("3Q+q0kiDtGLY41OI1IVdVB7tSww74+UX0WRNuuANigM+"
                  "ASS9KTxTCuR9+1Gk/32Tgd+QpwEagqaFQc0rF3Y84u4w0F+"
                  "NX2+SajHsnqnw5wY3JNxSyIYXhfiBC4T0dKsRcEF2wI9S2DS"
                  "vPaX95I80kelUla0D3Q/MrQJ4/8dE2p2pzwe4PAk=")
DART_API_KEY   = "c684ef333fb2e14394ee910611f5d29efec917db"
KIS_BASE       = "https://openapi.koreainvestment.com:9443"
DART_BASE      = "https://opendart.fss.or.kr/api"

def H(token, tr_id):
    return {"Content-Type":"application/json; charset=utf-8",
            "authorization":f"Bearer {token}","appkey":KIS_APP_KEY,
            "appsecret":KIS_APP_SECRET,"tr_id":tr_id,"custtype":"P"}

async def main():
    results = []
    token = ""
    sep = "=" * 62
    print(sep)
    print(f" API 검증 v2  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(sep)

    async with httpx.AsyncClient(timeout=20) as c:
        # 1. KIS 토큰
        r = await c.post(f"{KIS_BASE}/oauth2/tokenP", json={
            "grant_type":"client_credentials","appkey":KIS_APP_KEY,"appsecret":KIS_APP_SECRET})
        d = r.json()
        if r.status_code==200 and d.get("access_token"):
            token = d["access_token"]
            exp   = d.get("expires_in",0)
            results.append(("OK","KIS OAuth 토큰",
                f"만료 {exp//3600}h | {token[:30]}..."))
        else:
            results.append(("FAIL","KIS OAuth 토큰",str(d.get("msg1",""))))

        # 2. WS Approval
        r = await c.post(f"{KIS_BASE}/oauth2/Approval", json={
            "grant_type":"client_credentials","appkey":KIS_APP_KEY,"secretkey":KIS_APP_SECRET})
        d = r.json()
        if r.status_code==200 and d.get("approval_key"):
            results.append(("OK","KIS WS Approval Key",d["approval_key"][:25]+"..."))
        else:
            results.append(("FAIL","KIS WS Approval Key",str(r.status_code)))

        if not token:
            print("토큰 없음 - KIS 시세 테스트 스킵")
        else:
            # 3. 현재가
            await asyncio.sleep(0.3)
            r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=H(token,"FHKST01010100"),
                params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930"})
            d = r.json()
            if d.get("rt_cd")=="0":
                o = d.get("output",{})
                price = int(o.get("stck_prpr",0) or 0)
                rate  = o.get("prdy_ctrt","N/A")
                vol   = int(o.get("acml_vol",0) or 0)
                amt   = int(o.get("acml_tr_pbmn",0) or 0)//100_000_000
                results.append(("OK","KIS 현재가 (005930)",
                    f"{price:,}원 ({rate}%) 거래량{vol:,} 거래대금{amt:,}억"))
            else:
                results.append(("FAIL","KIS 현재가",d.get("msg1","")))

            # 4. 일봉 - FHKST01010400
            await asyncio.sleep(0.8)
            today = datetime.now().strftime("%Y%m%d")
            start = (datetime.now()-timedelta(days=14)).strftime("%Y%m%d")
            r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
                headers=H(token,"FHKST01010400"),
                params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930",
                        "FID_INPUT_DATE_1":start,"FID_INPUT_DATE_2":today,
                        "FID_PERIOD_DIV_CODE":"D","FID_ORG_ADJ_PRC":"0"})
            d = r.json()
            rows = d.get("output",[]) or d.get("output2",[])
            if d.get("rt_cd")=="0" and rows:
                row0 = rows[0]
                dt = row0.get("stck_bsop_date","")
                cl = int(row0.get("stck_clpr",row0.get("stck_prpr",0)) or 0)
                vl = int(row0.get("acml_vol",0) or 0)
                results.append(("OK","KIS 일봉 (FHKST01010400)",
                    f"{len(rows)}봉 수신 | 최근 {dt} 종가{cl:,}원 {vl:,}주"))
            else:
                # fallback: itemchartprice
                await asyncio.sleep(0.5)
                r2 = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                    headers=H(token,"FHKST03010100"),
                    params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930",
                            "FID_INPUT_DATE_1":start,"FID_INPUT_DATE_2":today,
                            "FID_PERIOD_DIV_CODE":"D","FID_ORG_ADJ_PRC":"0"})
                d2 = r2.json()
                rows2 = d2.get("output2",[])
                if d2.get("rt_cd")=="0" and rows2:
                    r0 = rows2[0]
                    dt = r0.get("stck_bsop_date","")
                    cl = int(r0.get("stck_clpr",0) or 0)
                    results.append(("OK","KIS 일봉 (FHKST03010100 fallback)",
                        f"{len(rows2)}봉 | 최근 {dt} {cl:,}원"))
                else:
                    results.append(("FAIL","KIS 일봉",
                        f"1차:{d.get('msg1','')} 2차:{d2.get('msg1','')}"))

            # 5. 수급 - 딜레이 충분히
            await asyncio.sleep(1.5)
            r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
                headers=H(token,"FHKST01010900"),
                params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930",
                        "FID_INPUT_DATE_1":today,"FID_INPUT_DATE_2":today,
                        "FID_PERIOD_DIV_CODE":"D"})
            d = r.json()
            rows = d.get("output",[])
            if d.get("rt_cd")=="0" and rows:
                row = rows[0]
                fgn  = int(row.get("frgn_ntby_qty",0) or 0)
                inst = int(row.get("orgn_ntby_qty",0) or 0)
                indv = int(row.get("indv_ntby_qty",0) or 0)
                results.append(("OK","KIS 수급 매매동향",
                    f"외국인{fgn:+,} 기관{inst:+,} 개인{indv:+,}주"))
            else:
                results.append(("FAIL","KIS 수급",d.get("msg1","")))

            # 6. 분봉
            await asyncio.sleep(0.8)
            r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                headers=H(token,"FHKST03010200"),
                params={"FID_ETC_CLS_CODE":"","FID_COND_MRKT_DIV_CODE":"J",
                        "FID_INPUT_ISCD":"005930","FID_INPUT_HOUR_1":"090000",
                        "FID_PW_DATA_INCU_YN":"Y"})
            d = r.json()
            rows = d.get("output2",[])
            if d.get("rt_cd")=="0" and rows:
                r0 = rows[0]
                t_ = r0.get("stck_cntg_hour","")
                cl = int(r0.get("stck_prpr",0) or 0)
                vl = int(r0.get("cntg_vol",0) or 0)
                results.append(("OK","KIS 분봉 (1분)",
                    f"{len(rows)}개 | 최근 {t_} {cl:,}원 {vl:,}주"))
            else:
                results.append(("FAIL","KIS 분봉",d.get("msg1","")))

            # 7. 공매도
            await asyncio.sleep(0.8)
            r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-shortsale",
                headers=H(token,"FHPST01810000"),
                params={"FID_INPUT_ISCD":"005930","FID_INPUT_DATE_1":start,"FID_INPUT_DATE_2":today})
            d = r.json()
            rows = d.get("output",[])
            if d.get("rt_cd")=="0" and rows:
                row0 = rows[0]
                vol  = int(row0.get("shnu_vol",0) or 0)
                dt_  = row0.get("stck_bsop_date","")
                results.append(("OK","KIS 공매도",f"최근({dt_}) {vol:,}주"))
            else:
                results.append(("FAIL","KIS 공매도",d.get("msg1","")))

        # 8. DART 공시 목록
        r = await c.get(f"{DART_BASE}/list.json", params={
            "crtfc_key":DART_API_KEY,
            "bgn_de":(datetime.now()-timedelta(days=1)).strftime("%Y%m%d"),
            "end_de":datetime.now().strftime("%Y%m%d"),
            "last_reprt_at":"Y","page_no":1,"page_count":3})
        d = r.json()
        if d.get("status")=="000":
            total = d.get("total_count",0)
            items = d.get("list",[])
            sample = f"{items[0].get('corp_name','')} - {items[0].get('report_nm','')[:30]}" if items else ""
            results.append(("OK","DART 공시 목록",f"총{total:,}건 | {sample}"))
        else:
            results.append(("FAIL","DART 공시 목록",d.get("message","")))

        # 9. DART company.json (stock_code로 조회)
        r = await c.get(f"{DART_BASE}/company.json",
            params={"crtfc_key":DART_API_KEY,"stock_code":"005930"})
        d = r.json()
        if d.get("status")=="000":
            results.append(("OK","DART 기업정보",
                f"{d.get('corp_name')} | 대표:{d.get('ceo_nm')} | 설립:{d.get('est_dt')}"))
        else:
            # fallback: 재무정보
            r2 = await c.get(f"{DART_BASE}/fnlttSinglAcntAll.json",
                params={"crtfc_key":DART_API_KEY,"corp_code":"00126380",
                        "bsns_year":"2023","reprt_code":"11011","fs_div":"CFS"})
            d2 = r2.json()
            if d2.get("status")=="000":
                cnt = len(d2.get("list",[]))
                results.append(("OK","DART 재무데이터 (fallback)",
                    f"삼성전자 2023년 재무 {cnt}개 항목"))
            else:
                results.append(("FAIL","DART 기업정보",
                    f"company:{d.get('status')} fnltt:{d2.get('status')}"))

        # 10. DART 사업보고서 공시 목록
        r = await c.get(f"{DART_BASE}/list.json", params={
            "crtfc_key":DART_API_KEY,"corp_code":"00126380",
            "bgn_de":"20240101","end_de":"20241231",
            "pblntf_ty":"A","page_no":1,"page_count":3})
        d = r.json()
        if d.get("status")=="000":
            items = d.get("list",[])
            sample = items[0].get("report_nm","")[:40] if items else "없음"
            results.append(("OK","DART 삼성전자 공시이력",
                f"{len(items)}건 | {sample}"))
        else:
            results.append(("FAIL","DART 공시이력",d.get("message","")))

    # 결과 출력
    print()
    ok_cnt = 0
    for status, label, detail in results:
        mark = "[OK  ]" if status=="OK" else "[FAIL]"
        if status=="OK": ok_cnt+=1
        print(f"  {mark}  {label}")
        if detail: print(f"           {detail}")

    total = len(results)
    print()
    print(sep)
    print(f"  최종 결과: {ok_cnt}/{total} 항목 통과")
    if ok_cnt == total:
        print("  >> 모든 API 정상 - 시스템 기동 준비 완료")
    elif ok_cnt >= 7:
        print("  >> 핵심 API 정상 - 실서비스 기동 가능")
    elif ok_cnt >= 5:
        print("  >> 부분 정상 - 일부 기능 제한")
    else:
        print("  >> 오류 다수 - 키/네트워크 확인 필요")
    print(sep)
    return ok_cnt

if __name__=="__main__":
    n = asyncio.run(main())
    sys.exit(0 if n>=7 else 1)
