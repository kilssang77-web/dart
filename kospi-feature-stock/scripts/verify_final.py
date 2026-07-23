import asyncio, sys, os, httpx
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

KIS_KEY    = os.environ.get("KIS_APP_KEY", "")
KIS_SEC    = os.environ.get("KIS_APP_SECRET", "")
DART_KEY   = os.environ.get("DART_API_KEY", "")

if not KIS_KEY or not KIS_SEC or not DART_KEY:
    print("오류: 다음 환경변수가 필요합니다.")
    print("  KIS_APP_KEY, KIS_APP_SECRET, DART_API_KEY")
    print("  .env 파일 또는 export 명령으로 설정하세요.")
    sys.exit(1)

KIS_BASE   = os.environ.get("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
DART_BASE  = "https://opendart.fss.or.kr/api"

def safe_json(r):
    try:
        return r.json()
    except Exception:
        return {}

def hdr(tok, tr):
    return {"Content-Type":"application/json; charset=utf-8",
            "authorization":f"Bearer {tok}","appkey":KIS_KEY,
            "appsecret":KIS_SEC,"tr_id":tr,"custtype":"P"}

async def main():
    results = []
    token = ""
    today = datetime.now().strftime("%Y%m%d")
    start = (datetime.now()-timedelta(days=14)).strftime("%Y%m%d")
    print("="*60)
    print(f" API Verification | {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("="*60)

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:

        # 1) KIS token
        try:
            r = await c.post(f"{KIS_BASE}/oauth2/tokenP",
                json={"grant_type":"client_credentials","appkey":KIS_KEY,"appsecret":KIS_SEC})
            d = safe_json(r)
            if d.get("access_token"):
                token = d["access_token"]
                exp = d.get("expires_in",0)
                results.append(("OK","KIS OAuth Token",f"TTL {exp//3600}h | {token[:30]}..."))
            else:
                results.append(("FAIL","KIS OAuth Token",d.get("msg1","no token")))
        except Exception as e:
            results.append(("FAIL","KIS OAuth Token",str(e)))

        # 2) WS Approval Key
        try:
            r = await c.post(f"{KIS_BASE}/oauth2/Approval",
                json={"grant_type":"client_credentials","appkey":KIS_KEY,"secretkey":KIS_SEC})
            d = safe_json(r)
            if d.get("approval_key"):
                results.append(("OK","KIS WS Approval Key",d["approval_key"][:22]+"..."))
            else:
                results.append(("FAIL","KIS WS Approval Key",str(d)))
        except Exception as e:
            results.append(("FAIL","KIS WS Approval Key",str(e)))

        if token:
            # 3) 현재가
            await asyncio.sleep(0.4)
            try:
                r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
                    headers=hdr(token,"FHKST01010100"),
                    params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930"})
                d = safe_json(r)
                if d.get("rt_cd")=="0":
                    o = d.get("output",{})
                    p = int(o.get("stck_prpr",0) or 0)
                    rt = o.get("prdy_ctrt","N/A")
                    v = int(o.get("acml_vol",0) or 0)
                    amt = int(o.get("acml_tr_pbmn",0) or 0)//100_000_000
                    results.append(("OK","KIS Current Price 005930",
                        f"{p:,}won ({rt}%) vol={v:,} amt={amt:,}bil"))
                else:
                    results.append(("FAIL","KIS Current Price",d.get("msg1",str(r.status_code))))
            except Exception as e:
                results.append(("FAIL","KIS Current Price",str(e)))

            # 4) 일봉 - inquire-daily-price FHKST01010400
            await asyncio.sleep(0.8)
            try:
                r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
                    headers=hdr(token,"FHKST01010400"),
                    params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930",
                            "FID_INPUT_DATE_1":start,"FID_INPUT_DATE_2":today,
                            "FID_PERIOD_DIV_CODE":"D","FID_ORG_ADJ_PRC":"0"})
                d = safe_json(r)
                rows = d.get("output",[]) or d.get("output2",[])
                if d.get("rt_cd")=="0" and rows:
                    r0 = rows[0]
                    dt = r0.get("stck_bsop_date","")
                    cl = int(r0.get("stck_clpr",r0.get("stck_prpr",0)) or 0)
                    results.append(("OK","KIS Daily Bars",f"{len(rows)} bars | last {dt} close={cl:,}"))
                else:
                    results.append(("FAIL","KIS Daily Bars (FHKST01010400)",
                        d.get("msg1",f"HTTP {r.status_code} rt={d.get('rt_cd')}")))
            except Exception as e:
                results.append(("FAIL","KIS Daily Bars",str(e)))

            # 5) 분봉
            await asyncio.sleep(0.8)
            try:
                r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                    headers=hdr(token,"FHKST03010200"),
                    params={"FID_ETC_CLS_CODE":"","FID_COND_MRKT_DIV_CODE":"J",
                            "FID_INPUT_ISCD":"005930","FID_INPUT_HOUR_1":"090000",
                            "FID_PW_DATA_INCU_YN":"Y"})
                d = safe_json(r)
                rows = d.get("output2",[])
                if d.get("rt_cd")=="0" and rows:
                    r0 = rows[0]
                    t_ = r0.get("stck_cntg_hour","")
                    cl = int(r0.get("stck_prpr",0) or 0)
                    results.append(("OK","KIS Minute Bars",f"{len(rows)} bars | {t_} close={cl:,}"))
                else:
                    results.append(("FAIL","KIS Minute Bars",d.get("msg1","")))
            except Exception as e:
                results.append(("FAIL","KIS Minute Bars",str(e)))

            # 6) 수급 (충분한 딜레이)
            await asyncio.sleep(2.0)
            try:
                r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
                    headers=hdr(token,"FHKST01010900"),
                    params={"FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":"005930",
                            "FID_INPUT_DATE_1":today,"FID_INPUT_DATE_2":today,
                            "FID_PERIOD_DIV_CODE":"D"})
                d = safe_json(r)
                rows = d.get("output",[])
                if d.get("rt_cd")=="0" and rows:
                    row = rows[0]
                    fgn  = int(row.get("frgn_ntby_qty",0) or 0)
                    inst = int(row.get("orgn_ntby_qty",0) or 0)
                    indv = int(row.get("indv_ntby_qty",0) or 0)
                    results.append(("OK","KIS Supply/Demand",
                        f"foreign={fgn:+,} inst={inst:+,} indiv={indv:+,}shares"))
                else:
                    results.append(("FAIL","KIS Supply/Demand",d.get("msg1","")))
            except Exception as e:
                results.append(("FAIL","KIS Supply/Demand",str(e)))

            # 7) 공매도
            await asyncio.sleep(0.8)
            try:
                r = await c.get(f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-shortsale",
                    headers=hdr(token,"FHPST01810000"),
                    params={"FID_INPUT_ISCD":"005930","FID_INPUT_DATE_1":start,"FID_INPUT_DATE_2":today})
                d = safe_json(r)
                rows = d.get("output",[])
                if d.get("rt_cd")=="0" and rows:
                    r0 = rows[0]
                    vol = int(r0.get("shnu_vol",0) or 0)
                    dt_ = r0.get("stck_bsop_date","")
                    results.append(("OK","KIS Short Selling",f"({dt_}) {vol:,}shares"))
                else:
                    results.append(("FAIL","KIS Short Selling",d.get("msg1","")))
            except Exception as e:
                results.append(("FAIL","KIS Short Selling",str(e)))

        # 8) DART 공시목록
        try:
            r = await c.get(f"{DART_BASE}/list.json",
                params={"crtfc_key":DART_KEY,
                        "bgn_de":(datetime.now()-timedelta(days=1)).strftime("%Y%m%d"),
                        "end_de":today,"last_reprt_at":"Y","page_no":1,"page_count":5})
            d = safe_json(r)
            if d.get("status")=="000":
                total = d.get("total_count",0)
                items = d.get("list",[])
                s = f"{items[0].get('corp_name','')} - {items[0].get('report_nm','')[:30]}" if items else ""
                results.append(("OK","DART Disclosure List",f"total={total:,} | {s}"))
            else:
                results.append(("FAIL","DART Disclosure List",d.get("message","")))
        except Exception as e:
            results.append(("FAIL","DART Disclosure List",str(e)))

        # 9) DART 기업정보
        try:
            r = await c.get(f"{DART_BASE}/company.json",
                params={"crtfc_key":DART_KEY,"stock_code":"005930"})
            d = safe_json(r)
            if d.get("status")=="000":
                results.append(("OK","DART Company Info",
                    f"{d.get('corp_name')} | CEO:{d.get('ceo_nm')} | Est:{d.get('est_dt')}"))
            else:
                r2 = await c.get(f"{DART_BASE}/company.json",
                    params={"crtfc_key":DART_KEY,"corp_code":"00126380"})
                d2 = safe_json(r2)
                if d2.get("status")=="000":
                    results.append(("OK","DART Company Info (corp_code)",
                        f"{d2.get('corp_name')} | CEO:{d2.get('ceo_nm')}"))
                else:
                    results.append(("FAIL","DART Company Info",
                        f"status_stock={d.get('status')} status_corp={d2.get('status')}"))
        except Exception as e:
            results.append(("FAIL","DART Company Info",str(e)))

        # 10) DART 재무데이터
        try:
            r = await c.get(f"{DART_BASE}/fnlttSinglAcntAll.json",
                params={"crtfc_key":DART_KEY,"corp_code":"00126380",
                        "bsns_year":"2023","reprt_code":"11011","fs_div":"CFS"})
            d = safe_json(r)
            if d.get("status")=="000":
                cnt = len(d.get("list",[]))
                results.append(("OK","DART Financial Data (Samsung 2023)",f"{cnt} items"))
            else:
                results.append(("FAIL","DART Financial Data",d.get("message",d.get("status",""))))
        except Exception as e:
            results.append(("FAIL","DART Financial Data",str(e)))

    # 출력
    print()
    ok = sum(1 for s,_,_ in results if s=="OK")
    for status, label, detail in results:
        mark = "[OK  ]" if status=="OK" else "[FAIL]"
        print(f"  {mark}  {label}")
        if detail:
            print(f"           {detail}")

    total = len(results)
    print()
    print("="*60)
    print(f"  Result: {ok}/{total} passed")
    if ok==total:  print("  >> ALL OK - Ready to deploy")
    elif ok>=7:    print("  >> CORE OK - Service can start")
    elif ok>=5:    print("  >> PARTIAL - Some features limited")
    else:          print("  >> ERROR - Check API keys/network")
    print("="*60)
    return ok

n = asyncio.run(main())
sys.exit(0 if n>=7 else 1)
