"""
KOSDAQ volume-rank 가능 여부 테스트
실행: python test_kosdaq_rank.py
성공: KOSDAQ 거래량 급등 종목 목록 출력
실패: rt_cd != "0" 오류 메시지 출력 → WebSocket 방식으로 전환 필요
"""
import json
import os
import time
import urllib.request
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))

APP_KEY    = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
KIS_BASE   = "https://openapi.koreainvestment.com:9443"

_TOKEN: dict = {}

def get_token() -> str:
    if _TOKEN.get("exp", 0) > time.time():
        return _TOKEN["tok"]
    body = json.dumps({"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}).encode()
    req  = urllib.request.Request(f"{KIS_BASE}/oauth2/tokenP", data=body,
           headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    _TOKEN.update({"tok": d["access_token"], "exp": time.time() + 23*3600})
    print("토큰 발급 OK")
    return _TOKEN["tok"]

def kis_get(path, tr_id, params):
    qs  = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{KIS_BASE}{path}?{qs}",
          headers={"authorization": f"Bearer {get_token()}", "appkey": APP_KEY,
                   "appsecret": APP_SECRET, "tr_id": tr_id, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def test_volume_rank(mkt_div: str, label: str):
    print(f"\n=== {label} (FID_COND_MRKT_DIV_CODE={mkt_div}) ===")
    d = kis_get(
        "/uapi/domestic-stock/v1/quotations/volume-rank",
        "FHPST01710000",
        {
            "FID_COND_MRKT_DIV_CODE": mkt_div,
            "FID_COND_SCR_DIV_CODE":  "20171",
            "FID_INPUT_ISCD":          "0000",
            "FID_DIV_CLS_CODE":        "0",
            "FID_BLNG_CLS_CODE":       "0",
            "FID_TRGT_CLS_CODE":       "111111111",
            "FID_TRGT_EXLS_CLS_CODE":  "000000",
            "FID_INPUT_PRICE_1":       "",
            "FID_INPUT_PRICE_2":       "",
            "FID_VOL_CNT":             "10000",
            "FID_INPUT_DATE_1":        "",
        },
    )
    rt_cd = d.get("rt_cd")
    msg   = d.get("msg1", "")
    items = d.get("output", [])
    print(f"rt_cd={rt_cd}  msg={msg}  items={len(items)}")
    if rt_cd == "0" and items:
        for item in items[:5]:
            code = item.get("mksc_shrn_iscd", item.get("stck_shrn_iscd", "?"))
            name = item.get("hts_kor_isnm", "?")
            vol_inrt = item.get("vol_inrt", "?")
            prdy_ctrt = item.get("prdy_ctrt", "?")
            print(f"  {code}  {name}  증가율={vol_inrt}%  등락={prdy_ctrt}%")
        print(f"→ ✅ {label} volume-rank 정상 작동")
    else:
        print(f"→ ❌ {label} volume-rank 실패 — WebSocket H0STCNT0 방식으로 대체 필요")

if __name__ == "__main__":
    test_volume_rank("J", "KOSPI")
    time.sleep(0.3)
    test_volume_rank("Q", "KOSDAQ")
    time.sleep(0.3)
    # 추가: 통합 시장 코드 테스트
    test_volume_rank("K", "KOSDAQ(K코드)")
