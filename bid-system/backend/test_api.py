import requests, json

BASE = 'http://localhost:8000/api/v1'

r = requests.post(BASE+'/auth/login', json={'email':'admin@bid.local','password':'admin1234'})
token = r.json()['access_token']
H = {'Authorization': 'Bearer '+token}
results = []
sep = '-' * 50

results.append(sep)
results.append('=== FULL API TEST ===')
results.append(sep)

def chk(cond, label):
    return '[OK] '+label if cond else '[FAIL] '+label

# ── 1. GO-LIST (TodayPage) ───────────────────────────────────
r = requests.get(BASE+'/selection/go-list?days=14', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'selection/go-list: status=%d' % r.status_code))
if r.status_code == 200:
    go = d.get('go', [])
    watch = d.get('watch', [])
    no_go = d.get('no_go', [])
    results.append('  go=%d watch=%d no_go=%d total=%s' % (len(go), len(watch), len(no_go), d.get('total')))
    results.append(chk(isinstance(go, list), 'go is list'))
    results.append(chk(isinstance(watch, list), 'watch is list'))

# ── 2. BIDS LIST ─────────────────────────────────────────────
r = requests.get(BASE+'/bids?size=10&page=1', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'bids list: total=%s' % d.get('total')))

# ── 3. BIDS DETAIL ───────────────────────────────────────────
r = requests.get(BASE+'/bids/1', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'bid detail id=1: %s' % d.get('title','?')[:20]))

# ── 4. FINAL-RECOMMEND ───────────────────────────────────────
r = requests.get(BASE+'/bids/1/final-recommend', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'final-recommend: status=%d' % r.status_code))
if r.status_code == 200:
    rec = d.get('recommended_rate')
    floor = d.get('floor_rate')
    below = (rec is not None and floor is not None and float(rec) < float(floor))
    results.append(chk(not below, 'floor_rate check: rec=%s floor=%s below=%s' % (rec, floor, below)))
    # prism_top probability scale
    ev = d.get('evidence', {})
    pt = ev.get('prism_top', [])
    if pt:
        if isinstance(pt, dict):
            p0 = pt.get('probability', 0)
        else:
            p0 = pt[0].get('probability', 0)
        results.append(chk(float(p0) <= 1.0, 'prism_top probability=%s (should be 0-1)' % p0))
    # strategies floor check
    strats = d.get('strategies', {})
    all_ok = True
    for k, v in strats.items():
        sr = v.get('rate', 0)
        if floor and sr and float(sr) < float(floor):
            results.append('[FAIL] strategy %s rate=%s < floor=%s' % (k, sr, floor))
            all_ok = False
        wp = v.get('win_prob', 0)
        if below and float(wp) > 0:
            results.append('[FAIL] strategy %s win_prob=%s but rate below floor' % (k, wp))
            all_ok = False
    if all_ok:
        results.append('[OK] all strategies >= floor_rate')

# ── 5. STATISTICS ────────────────────────────────────────────
r = requests.get(BASE+'/stats/overview?months=6', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'stats/overview: status=%d' % r.status_code))
if r.status_code == 200:
    wr = d.get('avg_win_rate')
    br = d.get('avg_bid_rate')
    same = (wr == br)
    results.append('  avg_win_rate=%s avg_bid_rate=%s same=%s' % (wr, br, same))
    results.append(chk(not same or wr is None, 'avg_bid_rate != avg_win_rate'))

# ── 6. STRATEGY/RECOMMEND ───────────────────────────────────
body = {'bid_id':1,'base_amount':3143000000,'agency_id':1}
r = requests.post(BASE+'/strategy/recommend', json=body, headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'strategy/recommend: status=%d' % r.status_code))
if r.status_code == 200:
    rate = d.get('rate')
    wp = d.get('win_prob')
    tp = d.get('strategy_type')
    vr = d.get('valid_range', [0,1])
    results.append('  rate=%s win_prob=%s type=%s valid_range=%s' % (rate, wp, tp, vr))
    # rate must be >= valid_range[0] (floor)
    results.append(chk(float(rate) >= float(vr[0]), 'rate >= valid_range.low'))
    results.append(chk(wp is not None and float(wp) >= 0, 'win_prob >= 0'))
    p5 = d.get('prism_top5', [])
    if p5:
        for i, p in enumerate(p5[:2]):
            results.append('  prism_top5[%d]: rate=%s win_prob=%s (should be 0-1)' % (i, p.get('rate'), p.get('win_prob')))
            results.append(chk(float(p.get('win_prob',0)) <= 1.0, 'prism_top5 win_prob scale'))

# ── 7. MIN_BID_RATE VALIDATION ──────────────────────────────
body2 = {'bid_id':1,'base_amount':3143000000,'agency_id':1,'min_bid_rate':2.0}
r = requests.post(BASE+'/strategy/recommend', json=body2, headers=H)
results.append(chk(r.status_code==422, 'min_bid_rate=2.0 rejected (422): got %d' % r.status_code))

# ── 8. BOOKMARKS ─────────────────────────────────────────────
r = requests.get(BASE+'/bids/bookmarks', headers=H)
results.append(chk(r.status_code==200, 'bookmarks: status=%d' % r.status_code))

# ── 9. MY-BIDS ───────────────────────────────────────────────
r = requests.get(BASE+'/my-bids?size=10', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'my-bids: status=%d' % r.status_code))

# ── 10. KPI DASHBOARD ───────────────────────────────────────
r = requests.get(BASE+'/kpi/dashboard?period_type=MONTHLY', headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'kpi/dashboard: status=%d' % r.status_code))

# ── 11. RECOMMEND-V2 ────────────────────────────────────────
body3 = {'agency_id':1,'industry_id':1,'region_id':1,'base_amount':660000000,'min_bid_rate':0.87745}
r = requests.post(BASE+'/recommend/v2', json=body3, headers=H)
d = r.json()
results.append(chk(r.status_code==200, 'recommend/v2: status=%d' % r.status_code))
if r.status_code == 200:
    results.append('  floor_rate=%s recommended=%s' % (d.get('floor_rate'), d.get('recommended_rate')))

# ── 12. NOTIFICATIONS ───────────────────────────────────────
r = requests.get(BASE+'/notifications?limit=5', headers=H)
results.append(chk(r.status_code==200, 'notifications: status=%d' % r.status_code))

# ── 13. COMPETITORS ─────────────────────────────────────────
r = requests.get(BASE+'/competitors?size=5', headers=H)
results.append(chk(r.status_code==200, 'competitors: status=%d' % r.status_code))

# ── 14. STATS AGENCIES ──────────────────────────────────────
r = requests.get(BASE+'/stats/agencies?months=6', headers=H)
results.append(chk(r.status_code==200, 'stats/agencies: status=%d' % r.status_code))

# ── 15. MARKET INTEL ────────────────────────────────────────
r = requests.get(BASE+'/market-intel/agency-heatmap?months=6', headers=H)
results.append(chk(r.status_code==200, 'market-intel/agency-heatmap: status=%d' % r.status_code))

results.append(sep)
fail_count = sum(1 for l in results if '[FAIL]' in l)
ok_count = sum(1 for l in results if '[OK]' in l)
results.append('RESULT: %d OK / %d FAIL' % (ok_count, fail_count))

for line in results:
    print(line)
