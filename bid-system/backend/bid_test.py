import urllib.request, json

BASE = "http://localhost:8100/api/v1"
RESULTS = []

def req(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_msg": e.read().decode()[:200]}
    except Exception as e:
        return {"_error": str(e)}

def chk(name, result, ok):
    status = "PASS" if ok else "FAIL"
    RESULTS.append((status, name, result))
    print(f"[{status}] {name}")
    if not ok:
        print(f"       → {str(result)[:180]}")

# ── 인증 ──
login = req("POST", "/auth/login", {"email": "admin@bid.local", "password": "admin1234"})
T = login.get("access_token", "")
chk("로그인", login, bool(T))
me = req("GET", "/auth/me", token=T)
chk("내 정보 (admin)", me, me.get("role") == "admin")

# ── 공고 목록 ──
bids = req("GET", "/bids?page=1&size=10", token=T)
total = bids.get("total", 0)
chk(f"공고 목록 전체 ({total:,}건)", bids, total > 5000)

bids_open = req("GET", "/bids?status=open&page=1&size=5", token=T)
chk(f"open 공고 필터 ({bids_open.get('total',0):,}건)", bids_open, bids_open.get("total", 0) > 0)

bids_ind = req("GET", "/bids?industry_id=24&page=1&size=5", token=T)
chk(f"업종24(방수) 필터 ({bids_ind.get('total',0):,}건)", bids_ind, bids_ind.get("total", 0) > 0)

# ── 검색 ──
s_apjang = req("GET", "/bids?keyword=%EA%B0%80%EC%95%95%EC%9E%A5&page=1&size=5", token=T)
found = any("가압장" in x.get("title","") for x in s_apjang.get("items",[]))
chk("가압장 방수공사 검색", s_apjang, found)

s_null = req("GET", "/bids?q=%EC%88%98%EC%9D%98&page=1&size=5", token=T)
chk(f"수의계약 검색 ({s_null.get('total',0):,}건)", s_null, s_null.get("total", 0) > 0)

# ── 공고 상세 ──
detail = req("GET", "/bids/150044", token=T)
chk("공고 상세 (bid#150044)", detail, detail.get("id") == 150044 and "가압장" in detail.get("title",""))

# ── AI 추천 / 의사결정 ──
rec = req("GET", "/bids/recommended?limit=5", token=T)
chk("AI 추천 목록", rec, isinstance(rec, list) and not (isinstance(rec, dict) and rec.get("_error")))

sim = req("POST", "/bids/150044/simulate-bid", {"yega_values": None, "our_bid_rate": 0.9235, "competitor_rates": None, "n_sim": 500}, token=T)
chk("시뮬레이션 API", sim, "strategies" in sim and not sim.get("_error"))

best = req("GET", "/bids/150044/best-rate", token=T)
chk("최적 투찰율 API", best, not best.get("_error"))

prism = req("GET", "/bids/150044/prism-histogram?period=24M", token=T)
chk("프리즘 히스토그램", prism, "histogram" in prism and not prism.get("_error"))

# ── 투찰 저널 ──
journal = req("GET", "/journal?page=1&size=5", token=T)
chk("투찰 저널 목록", journal, "items" in journal or isinstance(journal, list))

# ── 경쟁사 / 실행내역 ──
comp = req("GET", "/competitors?page=1&size=5", token=T)
chk("경쟁사 목록", comp, "items" in comp or isinstance(comp, list) or not comp.get("_error"))

exec_l = req("GET", "/executions?page=1&size=5", token=T)
chk("실행내역", exec_l, "items" in exec_l or isinstance(exec_l, list) or not exec_l.get("_error"))

# ── KPI ──
kpi = req("GET", "/kpi/dashboard", token=T)
chk("KPI 대시보드", kpi, not kpi.get("_error"))

# ── 관리자 ──
sys_s = req("GET", "/admin/system-status", token=T)
chk(f"시스템 상태 (bids:{sys_s.get('db_stats',{}).get('total_bids',0):,})", sys_s, sys_s.get("db_stats",{}).get("total_bids",0) > 0)

col_logs = req("GET", "/admin/collection-logs?days=7", token=T)
chk("수집 로그 (7일)", col_logs, isinstance(col_logs, list) and len(col_logs) > 0)

inpo_s = req("GET", "/admin/inpo21c/status", token=T)
chk(f"inpo21c 연결 ({inpo_s.get('status','')})", inpo_s, "status" in inpo_s)

inpo_stat = req("GET", "/admin/inpo21c/stats", token=T)
chk(f"inpo21c 통계 (참여자:{inpo_stat.get('participants',0):,})", inpo_stat, inpo_stat.get("participants",0) > 0)

ml_wp = req("GET", "/admin/ml/win-prob-status", token=T)
chk("win-prob 모델 상태", ml_wp, not ml_wp.get("_error"))

ml_bias = req("GET", "/admin/ml/bias-report", token=T)
chk("ML 편향 리포트", ml_bias, "global" in ml_bias and not ml_bias.get("_error"))

col_stat = req("GET", "/admin/collector-status", token=T)
chk("수집기 상태", col_stat, "today_notices" in col_stat and not col_stat.get("_error"))

# ── 결과 요약 ──
passed = sum(1 for s,_,_ in RESULTS if s == "PASS")
failed = sum(1 for s,_,_ in RESULTS if s == "FAIL")
print(f"\n{'='*45}")
print(f" PASS {passed}/{len(RESULTS)}  |  FAIL {failed}/{len(RESULTS)}")
print(f"{'='*45}")
if failed:
    print("\n[실패 항목]")
    for s, n, d in RESULTS:
        if s == "FAIL":
            print(f"  ✗ {n}")
            print(f"    {str(d)[:160]}")
