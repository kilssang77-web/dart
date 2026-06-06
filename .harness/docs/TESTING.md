# 테스트 전략

---

## 테스트 피라미드

```
         /\
        /E2E\         미구현 (production 단계 예정)
       /──────\
      /통합 테스트\    미구현 (production 단계 예정)
     /────────────\
    /  단위 테스트  \  pytest 27개 ✅ (mvp 충족)
   /────────────────\
```

| 레이어 | 현황 | 도구 |
|--------|------|------|
| 단위 테스트 | ✅ 27개 통과 | pytest |
| 통합 테스트 | — (production 예정) | pytest + real DB |
| E2E 테스트 | — (production 예정) | 미정 |

---

## 단위 테스트 목록

### tests/test_candlestick.py (15개)

| 테스트 | 검증 내용 |
|--------|---------|
| 장대양봉 완전 커버 | 바디 비율 임계값, 경계값 |
| 망치형 완전 커버 | 아랫꼬리 비율, 바디 위치 |
| 모닝스타 완전 커버 | 3봉 구조 (하락봉 + 소형봉 + 상승봉) |

### tests/test_entry_recommender.py (12개)

| 테스트 | 검증 내용 |
|--------|---------|
| 진입 판단 | BUY/WAIT/SKIP 분기 조건 |
| 가격 계산 | entry_price, target_price, stop_loss 산출 |
| 확률 혼합 | ML 확률 + rule-based 확률 혼합 로직 |

---

## 실행 방법

```bash
# 의존성 설치
pip install -r tests/requirements-test.txt

# 전체 실행
pytest tests/ -v

# 특정 파일만
pytest tests/test_candlestick.py -v

# 커버리지 측정 (production 단계 목표: 70%+)
pytest tests/ --cov=services --cov-report=term-missing
```

---

## 단계별 테스트 요구사항

| 단계 | 최소 요건 |
|------|---------|
| prototype | Docker Compose 기동 후 `/health` 통과 |
| **mvp** (현재) | **pytest 27개 이상 통과** |
| production | pytest 커버리지 70%+, 보안 스캔, E2E 시나리오 |

---

## 테스트 데이터 원칙

- 단위 테스트: 인라인 fixture (DB 불필요)
- 통합 테스트 (production 예정): 실 DB 연결 (TimescaleDB), asyncpg 사용
- 모킹: DB·Kafka·KIS API 모킹 금지 — 실 연결 또는 fixture 데이터 사용

---

## 주요 검증 포인트

### Recovery 무결성
- 재시작 후 중복 처리 0건 (feature_event_id 기반 NOT EXISTS 조건)
- 검증: `docker compose restart recommender` → 로그에서 `Recovery: completed X/X` 확인

### ML 추론 정상 동작
```bash
curl http://localhost:8001/health
# → {"status": "ok", "model_loaded": true}

curl -X POST http://localhost:8001/predict -d '{"features": {...}}'
# → {"success_prob": 0.43, "risk_prob": 0.31, "model_used": true}
```

### pattern_vector 활성화
```sql
SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NULL;
-- 0건이어야 함 (백필 완료 상태)
```
