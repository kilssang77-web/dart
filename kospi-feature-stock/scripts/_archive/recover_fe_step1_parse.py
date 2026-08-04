"""호스트에서 실행: 신호 로그 파싱 → signals.json 생성"""
import re, json
from collections import defaultdict
from datetime import datetime, timezone

SIGNAL_PAT = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[detector\] INFO - \[SIGNAL\] (\w+) (\w+) score=([\d.]+)'
)

signals = []
seen = set()
with open('/tmp/signals_raw.txt') as f:
    for line in f:
        m = SIGNAL_PAT.search(line)
        if not m:
            continue
        dt_str, code, event_type, score = m.groups()
        date = dt_str[:10]
        key = (code, event_type, date)
        if key in seen:
            continue
        seen.add(key)
        signals.append({
            "code": code,
            "event_type": event_type,
            "detected_at": dt_str + "+00:00",
            "signal_score": float(score),
        })

by_date = defaultdict(int)
by_type = defaultdict(int)
for s in signals:
    by_date[s["detected_at"][:10]] += 1
    by_type[s["event_type"]] += 1

print(f"총 고유 신호: {len(signals)}건")
for d in sorted(by_date): print(f"  {d}: {by_date[d]}건")
for t, c in sorted(by_type.items(), key=lambda x: -x[1]): print(f"  {t}: {c}건")

with open('/tmp/signals.json', 'w') as f:
    json.dump(signals, f, ensure_ascii=False)
print("signals.json 저장 완료")
