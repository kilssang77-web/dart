# 보안 가이드

---

## 인증 · 인가

이 시스템은 내부 마이크로서비스 간 통신 전용입니다. 외부 클라이언트용 인증은 MVP 단계에서 미구현 (API 서비스는 내부망 접근 전제).

| 서비스 | 인증 방식 |
|--------|---------|
| api service | 미인증 (내부망 전용, MVP) |
| ml service | 미인증 (Docker 내부 네트워크 전용) |
| KIS API | 앱키/시크릿 기반 OAuth2 (환경변수 관리) |

---

## 비밀값 관리

**절대 금지 사항:**
- 소스 코드에 API 키·DSN·비밀번호 하드코딩
- `.env` 파일 git 커밋
- 로그에 KIS 앱키·시크릿·계좌번호 출력

**허용 관리 방식:**
- 개발: `.env` 파일 (`.gitignore`에 포함)
- 운영: Docker Secret 또는 환경변수 주입
- 코드에서는 항상 `os.getenv()` 사용

```python
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
# 절대 금지
KIS_APP_KEY = "PSxxxxxxxxxxxxxxxx"
```

---

## 입력 검증

### FastAPI 라우터

- 모든 요청 바디는 Pydantic 스키마로 검증
- 쿼리 파라미터는 FastAPI 타입 선언으로 검증
- `dict` / `Any` 타입 입력 처리 금지

```python
class PredictRequest(BaseModel):
    features: dict[str, float]

@router.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest): ...
```

### SQL 인젝션 방지

asyncpg 파라미터 바인딩 사용 (`$1`, `$2`). 문자열 포맷팅으로 SQL 조합 절대 금지.

### Kafka 메시지

- 수신 메시지는 `orjson.loads()` 파싱 후 타입 검증
- `Decimal` 타입은 `float()`로 명시 변환 후 처리 (`orjson` 직렬화 오류 방지)

---

## OWASP Top 10 현황 (mvp 기준)

| OWASP 항목 | 상태 | 대응 방법 |
|-----------|------|----------|
| A01 - 접근 제어 실패 | ⚠️ | 내부망 격리. 외부 인증 production 단계 추가 예정 |
| A02 - 암호화 실패 | ✅ | 비밀값 환경변수 관리, 코드 하드코딩 없음 |
| A03 - 인젝션 | ✅ | asyncpg 파라미터 바인딩, Pydantic 검증 |
| A04 - 안전하지 않은 설계 | ✅ | 서비스 독립 배포, 타 서비스 DB 직접 접근 금지 |
| A05 - 보안 구성 오류 | ✅ | `.env` gitignore, Docker 내부 네트워크 격리 |
| A06 - 취약하고 오래된 구성요소 | ⚠️ | 수동 확인 (production에서 pip-audit 자동화 예정) |
| A07 - 식별 및 인증 실패 | ⚠️ | MVP 미구현 (내부망 전용) |
| A08 - 소프트웨어 무결성 실패 | ✅ | 모델 파일 atomic rename (tmp → 실제 경로) |
| A09 - 보안 로깅/모니터링 실패 | ✅ | 로그에 비밀값 출력 금지 정책 적용 |
| A10 - SSRF | ✅ | 외부 HTTP 호출은 KIS API·ml service URL만 허용 |

---

## 로깅 PII 정책

- KIS 앱키·시크릿·계좌번호: 로그 출력 절대 금지
- DSN(DB 접속 정보): 로그 출력 금지
- 종목코드·가격·추천 결과: 로그 허용 (개인정보 아님)

```python
# 허용
logger.info("추천 생성: code=%s, action=%s, prob=%.4f", code, action, prob)

# 금지
logger.debug("KIS 요청: app_key=%s", KIS_APP_KEY)
```

---

## 의존성 보안 스캔

```bash
# Python 패키지 취약점 검사
pip install pip-audit
pip-audit -r services/recommender/requirements.txt
```

- 실행 주기: production 단계에서 CI/CD 파이프라인에 추가 예정
- 임계값: high 이상 발견 시 배포 중단
