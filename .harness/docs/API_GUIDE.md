# API 가이드

---

## REST 규약

- Base URL: `/api/v1`
- Content-Type: `application/json`
- 버저닝: URL 경로 (`/api/v1`)

---

## 에러 응답 포맷

```json
{
  "detail": "에러 메시지"
}
```

FastAPI 기본 HTTPException 구조 사용. 422 Unprocessable Entity는 Pydantic 검증 실패 시 자동 반환.

---

## 주요 API — 외부 서비스 (api service, port 8000)

### 추천 신호

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/recommendations` | 추천 목록 조회 |
| GET | `/api/v1/recommendations/buy-signals` | BUY 신호만 조회 |

**GET /api/v1/recommendations 쿼리 파라미터:**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `action` | — | `BUY` / `WAIT` / `SKIP` 필터 |
| `min_prob` | `0.35` | 최소 성공 확률 임계값 |
| `limit` | `50` | 최대 반환 건수 |

**응답 예시:**
```json
[
  {
    "id": 1,
    "code": "003550",
    "name": "LG",
    "action": "BUY",
    "entry_price": 72000,
    "target_price": 79200,
    "stop_loss": 68400,
    "success_prob": 0.4266,
    "risk_score": 0.31,
    "event_type": "VI_TRIGGERED",
    "created_at": "2026-06-05T14:23:11+09:00"
  }
]
```

### 특징 이벤트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/features` | feature_events 목록 조회 |
| GET | `/api/v1/features/{event_id}` | 특정 이벤트 상세 |

**지원 EVENT_TYPES**: `VOLUME_SURGE`, `BREAKOUT_52W`, `MORNING_STAR`, `VI_TRIGGERED`

---

## 내부 ML 서비스 API (ml service, port 8001)

recommender에서 HTTP로 호출하는 내부 전용 API. 외부 노출 없음.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 서비스 헬스 체크 |
| POST | `/predict` | ML 추론 요청 |
| POST | `/reload` | 모델 핫스왑 (재학습 후 호출) |

**GET /health 응답:**
```json
{ "status": "ok", "model_loaded": true }
```

**POST /predict 요청:**
```json
{
  "features": {
    "rsi14": 68.4,
    "macd_hist": 0.0023,
    "volume_ratio": 5.2,
    ...
  }
}
```

**POST /predict 응답:**
```json
{
  "success_prob": 0.4266,
  "risk_prob": 0.31,
  "model_used": true
}
```

---

## Kafka 토픽

| 토픽 | 발행 | 소비 | 설명 |
|------|------|------|------|
| `tick-data` | collector | detector | 실시간 체결 데이터 |
| `feature-events` | detector | recommender | 패턴 탐지 이벤트 |
| `signal-generated` | recommender | (알림 서비스 예정) | BUY 신호만 발행 |

**signal-generated 메시지 포맷:**
```json
{
  "code": "003550",
  "action": "BUY",
  "entry_price": 72000,
  "target_price": 79200,
  "stop_loss": 68400,
  "success_prob": 0.4266,
  "risk_score": 0.31
}
```

---

## 추론 우선순위 (recommender → ml 호출 순서)

```
1. HTTP POST http://ml:8001/predict (ML_SERVICE_URL 환경변수)
2. 로컬 LightGBM 직접 추론 (fallback)
3. rule-based 고정값 (최종 fallback, success_prob=0.575)
```

---

## 환경변수 — API 동작 관련

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `REC_MIN_PROB` | `0.35` | BUY 판정 최소 확률 |
| `REC_MAX_RISK` | `0.60` | BUY 판정 최대 리스크 점수 |
| `REC_MIN_RISK_REWARD` | `2.0` | 최소 손익비 |
| `ML_SERVICE_URL` | `""` | ML 서비스 URL (`http://ml:8001`) |
| `ML_API_PORT` | `8001` | ML 서비스 포트 |
