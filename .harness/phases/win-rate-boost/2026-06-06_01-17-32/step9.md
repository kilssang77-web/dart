---
step: 9
name: "복수예가 위치 가중 추첨 시뮬레이션"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
`simulate_yejung()`이 15개 예비가격 중 4개를 선택할 때 균등 무작위를 사용하나,
inpo21c_yega.is_selected 실측 데이터에서 특정 번호(위치)가 더 자주 추첨된다는 사실이 확인됨.
`pos_weights`(15개 위치별 가중치)를 시뮬레이션에 반영해 예정가격 분포 정확도를 높인다.

## 구현 상세

### simulation.py — simulate_yejung()
```python
def simulate_yejung(
    base_amount, srate_center, srate_std, n_sim=30_000,
    rng=None,
    pos_weights=None,   # NEW: 15개 위치별 추첨 가중치 (합=1.0), None이면 균등
):
    # pos_weights 있으면 Gumbel-max trick으로 가중 비복원 추첨
    if pos_weights is not None:
        log_w = np.log(np.array(pos_weights))
        gumbel = rng.gumbel(size=(n_sim, 15))
        idx = np.argsort(log_w + gumbel, axis=1)[:, -4:]
    else:
        noise = rng.random((n_sim, 15))
        idx = np.argsort(noise, axis=1)[:, :4]
```

### prism.py — scan_prism_zones()
```python
from .yega import load_inpo21c_yega_stats
yega_stats = load_inpo21c_yega_stats(db, agency_id)
pos_weights = yega_stats.get("pos_weights")
srate_dist = simulate_yejung(..., pos_weights=pos_weights)
```

### simulation.py — monte_carlo_recommend()
동일하게 pos_weights 파라미터 추가 및 prism 동일 방식 적용.

## 기존 시그니처 유지
- pos_weights=None 기본값 → 기존 동작 동일 유지
- DB 변경 없음
