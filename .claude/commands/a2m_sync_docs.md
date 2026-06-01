---
description: 축적된 release-notes를 모아 .harness/docs/에 반영합니다
---

신규 `/a2m_sync_docs` 명령입니다.
여러 run에 걸쳐 축적된 release-notes를 분석하고,
변경 이력을 .harness/docs/*에 일괄 반영합니다.

이 명령은 명시적으로 호출하는 milestone 작업입니다.
권장 사용 시점: 분기·릴리스 마일스톤, 단계 이동 직후, 신규 팀원 합류 직전.

> **참고**: `.harness/docs/SCHEMA.md`는 improve 중에 마이그레이션 파일과 함께 즉시 갱신합니다.
> 이 명령의 sync 대상에서 SCHEMA.md를 포함할 필요가 없습니다. (이미 최신 상태)

---

## Step 1 — 미반영 release-notes 수집

`.harness/release-notes/INDEX.md`를 열어 **❌ 마커**가 붙은 행을 찾아라.

INDEX.md의 표 형식 예시:
```
| release-note 파일 | 태스크 | 완료일 | 반영 |
|---|---|---|---|
| run-2026-05-14_auth.md | auth | 2026-05-14 | ✅ |
| run-2026-05-15_post.md | post | 2026-05-15 | ❌ |
```
- `✅` = 이미 반영됨 (건너뜀)
- `❌` = 미반영 (이번 sync 대상)

❌ 행이 없으면:
> "모든 release-notes가 이미 docs에 반영되어 있습니다."
종료.

있으면 목록을 보여주고:
> "다음 {N}개의 release-notes가 docs에 미반영되어 있습니다:
> {목록}
> 모두 이번에 반영할까요? 일부만 선택해도 됩니다."

---

## Step 2 — docs 갱신 권고 수집

선택된 release-notes 파일의 "관련 docs 갱신 권고" 섹션을 모두 읽어라.

파일별로 정리:
```
.harness/docs/ARCHITECTURE.md:
  - [run1] 디렉토리 구조 변경 (frontend/features/auth/ 추가)
  - [run2] 시퀀스 다이어그램 Redis 캐시 추가 반영 필요

.harness/docs/API_GUIDE.md:
  - [run2] /api/auth/refresh 엔드포인트 추가
  - [run3] 페이지네이션 응답 형식 변경

.harness/docs/SECURITY.md:
  - [run2] JWT refresh token 정책 추가
```

---

## Step 3 — AI 갱신 초안 생성

각 docs 파일에 대해 변경이 필요한 섹션을 파악하고 갱신 내용을 diff 형식으로 제안하라.

제시 형식:
```markdown
## .harness/docs/API_GUIDE.md 변경 제안

### 주요 API 목록 섹션에 추가:
| POST | `/api/auth/refresh` | access 토큰 재발급 | refresh token |

### 페이지네이션 섹션 수정:
- 기존: ...
- 변경: ...
```

---

## Step 4 — 사용자 확인

파일별로 확인을 받아라:
> ".harness/docs/API_GUIDE.md 갱신안을 반영하시겠습니까? (예 / 아니오 / 수정)"

- **예**: 파일 수정 즉시 적용
- **아니오**: 건너뜀 (INDEX.md에 "사용자가 거부"로 기록)
- **수정**: 사용자 의견 반영 후 재제안

---

## Step 5 — 반영 완료 마킹

반영된 release-notes 파일의 **per-note 메타 파일**을 업데이트하라:
```
.harness/release-notes/<run_id>_<task>.meta.json
```
해당 파일의 `synced` 필드를 `true`로 변경하라:
```json
{ "synced": true }
```

`INDEX.md`는 직접 수정하지 않는다 — `python .harness/scripts/release_notes.py --rebuild-index` 로 자동 재생성된다.

---

## Step 6 — 페르소나 검증

sync 완료 후 충실도를 재확인한다. **단계별로 강제/선택이 다르다:**

| 단계 | 정책 | 명령 |
|---|---|---|
| **production** | **강제** — 미통과 시 sync 커밋 중단 권고 | `python .harness/scripts/review_docs.py --stage production --no-autofill` |
| mvp | 선택 (권장) | `python .harness/scripts/review_docs.py --stage mvp --no-autofill` |
| prototype | 선택 | `python .harness/scripts/review_docs.py --stage prototype --no-autofill` |

> `--no-autofill`: sync에서 이미 반영한 내용에 대한 평가만. 자동 보완은 별도 PR.

결과를 사용자에게 요약 표시. 점수 미달 항목은 별도 이슈/PR 안내.

**production에서 미통과 시**: Step 7 커밋을 보류하고 갭 목록을 출력한다. 보완 후 review_docs를 재실행하여 통과 확인 후 커밋을 진행하라.

---

## Step 7 — 커밋

```
docs: sync release-notes to docs (runs: <run_id_목록>)
```
