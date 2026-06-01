---
description: 기존 프로젝트의 수정·기능 개선을 위한 진입점으로 진행합니다
---

신규 `/a2m_improve` 명령입니다.
기존 코드가 있는 프로젝트의 수정·기능 개선을 위한 진입점입니다.
.harness/docs/*를 직접 수정하지 않습니다. 변경 이력은 release-note로만 남깁니다.

**중요**: `A2M_NO_DOCS_EDIT=1` 환경변수를 설정하여 이 세션에서 .harness/docs/* 직접 수정을 방지하라.

**예외 — `.harness/docs/SCHEMA.md`**:
DB 스키마를 변경하는 step이 포함된 경우, `SCHEMA.md`를 마이그레이션 파일과 **즉시** 직접 수정한다.
`SCHEMA.md`가 오래되면 이후 AI 작업에서 잘못된 JPA 엔티티·쿼리를 생성하기 때문이다.
`guard_paths.py`에 의해 이 파일에 대해 A2M_NO_DOCS_EDIT 차단이 면제된다.

---

## A-0. 인벤토리 (코드베이스 현황 파악)

다음 항목을 확인하라:

1. `git log --oneline -20` — 최근 커밋 이력
2. `git status --short` — 현재 변경사항
3. `python .harness/scripts/analyze_codebase.py --json` — 기술/구조 빠른 파악
4. `python .harness/scripts/find_resumable.py --json` — 미완료 run 확인

미완료 run이 있으면:
> "{task}/{runId} run이 중단되어 있습니다. 이어서 진행할까요?"

---

## A-0b. 기술 선택·템플릿 규칙 반영 (필수)

A-0의 `analyze_codebase.py --json` 결과와 **`CLAUDE.md`**, **`.harness/profile.json`의 `tech`**를 비교하라.

불일치하는 언어·프레임워크, `tech` 누락·구식, `CLAUDE.md`가 기본 Spring/React 템플릿 그대로인 경우가 하나라도 있으면 **B-1 전**에 아래를 완료한다.

1. 리포·분석 결과를 **실제 선택으로 확정**한다 (필요 시 사용자에게 확인).
2. **`.harness/profile.json`의 `tech`**를 실제에 맞게 갱신한다.
3. **`CLAUDE.md`**를 확정 선택에 맞게 상단 준비한다 (`execute.py`가 각 step마다 이 파일을 주입하므로 필수).

**.harness/docs/* 처리 (이 명령은 docs 직접 수정이 금지다):** 선택이 `.harness/docs/*`와 어긋난 경우 사용자에게 **`/a2m_sync_docs`** 또는 docs 전용 세션(**`/a2m_docs`**)으로 반영하도록 안내한다. 이 세션에서는 `A2M_NO_DOCS_EDIT=1`이 적용된다.

---

## A-1. 단계 확인 (현재 및 목표)

`.harness/profile.json` 읽기:
```
현재 단계: {stage}
```

사용자에게 질문:
> "현재 단계는 {stage}입니다.
> 이번 작업 후 단계를 변경하겠습니까? (변경 없음 / prototype / mvp / production)"

단계 이동이 있으면 해당 단계 자격을 위한 보강 항목을 step에 자동 추가:
- **prototype → mvp**: 테스트 추가, 기본 보안 검증, **SCREEN_MAP.md 신설**, docs 11종 정렬 필요
- **mvp → production**: 커버리지 목표, 보안 스캔, 모니터링 추가, **DEPLOYMENT.md 신설**, docs 12종 정렬 필요

단계 이동 직후, docs 보강이 완료되면:
```
python .harness/scripts/review_docs.py --stage <새 단계>
```
를 재실행하여 새 단계의 페르소나 기준을 충족하는지 확인한다.

`.harness/profile.json` 업데이트 (목표 단계 반영).

---

## 참고 프로젝트 입력

**반드시** 아래 질문을 하라:
> "이번 작업에서 참고할 만한 프로젝트가 있나요?
> git URL 또는 로컬 절대 경로를 입력해 주세요. 없으면 '없음'으로 답해주세요."

있으면: `python .harness/scripts/references.py add <url> --purpose "<용도>"`

---

## B-1. 변경 요구 수집

사용자에게 요청:
> "어떤 수정 또는 기능 개선이 필요한가요? 구체적으로 설명해 주세요."

---

## B-2. 영향도 분석

수집된 변경 요구를 바탕으로:

1. **영향을 받는 레이어** 파악 (Controller / Service / Repository / Frontend)
2. **영향 파일 목록** 추정
3. **사이드 이펙트 이슈** 검토
   - 기존 API 시그니처 변경 여부
   - DB 스키마 마이그레이션 필요 여부 — 필요하면 step 계획 시 마이그레이션 파일 생성을 반드시 포함
   - 환경변수 추가/변경 여부
4. **.harness/docs/** 현황과의 괴리 확인:
   - ARCHITECTURE.md의 구조 기술이 현재 코드와 다르면 "/a2m_sync_docs를 통해 싱크 권장" 알림
   - DB 변경이 있으면 SCHEMA.md 업데이트 권고를 release-notes에 포함

---

## C. Step 계획

변경 요구를 step으로 분해하라.

**각 step의 `step{N}.md` frontmatter에 반드시 포함**:
```yaml
---
relevant_docs: ["<관련문서>", "<관련문서>"]
relevant_references: ["<참고프로젝트명>"]
---
```

단계 이동 중이면 "단계 이동 보강" step을 추가:
- 테스트 커버리지 향상
- 보안 스캔 설정
- 모니터링/로깅 추가

각 step은 **기존 시그니처 유지 vs 변경**, **사이드 이펙트**, **마이그레이션 경로** 항목을 포함.

DB 스키마 변경이 있는 step은 반드시 아래를 포함해야 합니다:
- `V{n}__{설명}.sql` 마이그레이션 파일 생성
- `.harness/docs/SCHEMA.md` 해당 테이블·컬럼 정의 업데이트 (A2M_NO_DOCS_EDIT 예외)

사용자 확인 후 D 진행.

---

## D. 파일 생성

> **runId 생성 단일화**: runId는 항상 이 명령(`/a2m_improve`)에서 생성한다.
> `execute.py`가 자동으로 runId를 생성하는 경로는 **deprecated**이다.
> execute.py를 직접 `task`만 인자로 실행하지 않도록 주의.

```python
from datetime import datetime, timezone, timedelta
TZ = timezone(timedelta(hours=9))
run_id = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
```

1. `.harness/phases/<task>/<runId>/` 생성
2. `index.json` 과 `step{N}.md` 생성
3. `.harness/phases/index.json`의 `runs[]`에 append (덮어쓰기 금지!)

---

## E. 실행

```
python .harness/scripts/execute.py <task>/<runId>
```

완료 후:
- `.harness/release-notes/<runId>_<task>.md` 자동 생성됨을 알림
- docs와의 괴리가 적발되었으면 `/a2m_sync_docs` 실행 권장
- 단계 이동이 있었으면 docs 보강 필요 세션을 안내
