---
description: 신규 프로젝트 또는 기존 프로젝트를 분석해 개발 워크플로를 시작합니다
---

신규 `atom-harness` 프레임워크의 진입점 명령 `/a2m_start`입니다.
아래 순서에 따라 단계를 진행하되, 사용자 답변에 따라 분기하라.

---

## Step 0 — 미완료 run 확인

먼저 `python .harness/scripts/find_resumable.py --json`을 실행하라.

결과의 `resumable` 배열이 1개 이상이면:
- 사용자에게 목록을 표시하라 (본인 run만 — `current_author` 기준)
- "이어서 진행하시겠습니까? (run 번호 선택 / 새로 시작)" 질문

> **Author 격리**: 기본적으로 본인(`current_author`)의 run만 표시된다.
> 타인 run 포함 전체 목록은 `find_resumable.py --show-all`로 확인할 수 있다.
> 타인 run을 선택하면 다음 안내를 보여라:
> "이 run은 {author}가 시작했습니다. 본인이 이어받으시겠습니까? (Y로 confirm 시 ownership을 본인에게 이전합니다)"
> 확인되면 `execute.py {task}/{runId} --takeover {author_email}` 로 실행.

이어서 진행 선택 시:
```
python .harness/scripts/execute.py <task>/<runId>
```
새로 시작 선택 시 → Step 1로
미완료 run 없음: → Step 1로

---

## Step 1 — 프로젝트 감지

다음 지표로 확인하여 **NEW** 또는 **EXISTING**을 자동 판단하라:
- `package.json`, `pom.xml`, `build.gradle`, `src/main/`, `frontend/` 존재
- `git log --oneline -1` 커밋이 1개 이상

**EXISTING 감지 시** 사용자에게 명시적으로 확인:
> "기존 코드가 감지되었습니다. EXISTING(기존 프로젝트 분석)으로 진행할까요? NEW(처음부터 시작)로 진행할까요?"

---

## Step 2A — EXISTING 모드: 코드베이스 자동 분석 (EXISTING 선택 시)

```
python .harness/scripts/analyze_codebase.py --json
```

분석 결과를 보여주고:
> "코드베이스를 분석했습니다. .harness/docs/*를 자동 생성하시겠습니까?"

- **예**: 분석 결과로 docs 초안을 생성하고 파일별로 확인 받아 저장
- **아니오**: `/a2m_docs` 명령 호출 안내

---

## Step 2A-1 — 기술 선택·템플릿 규칙 반영 (EXISTING 필수)

`analyze_codebase.py --json` 결과(또는 리포 지표)와 **`CLAUDE.md` 상단 제목**, **`.harness/profile.json`의 `tech`**를 비교하라.

다음 중 하나라도 해당되면 **Step 3 전**에 반영을 완료한다:

- 감지된 기술이 Spring Boot + React 기본 템플릿과 다른 경우
- `CLAUDE.md`에 실제 리포와 맞지 않는 언어·프레임워크 사용 규칙이 남아 있다.
- `profile.json`의 `tech`가 비어 있거나 분석 결과와 다른 경우

**반영 절차:**

1. 분석 JSON·리포에서 **실제 선택을 한 줄로 확정**하고 사용자에게 필요 시 확인한다.
2. **`.harness/profile.json`**의 `tech`를 실제 선택에 맞게 갱신한다.
3. **`CLAUDE.md`**를 확정 선택에 맞게 상단 준비한다 (CRITICAL·코딩 규칙·금지 사항 포함).
4. docs 초안이 이미 생성되었다면 **`ADR.md`·`ARCHITECTURE.md`·`PROJECT_STRUCTURE.md`·`CODING_CONVENTION.md`** 의 선택 의존 문서를 같은 세션에서 수정한다. 아직 없으면 이후 Step 5 검증까지 생성·정렬한다.
5. 반영 후 `python .harness/scripts/validate_docs.py --stage <stage> --json`을 돌려 플레이스홀더·오류를 조기에 잡는 것을 권장한다.

---

## Step 2B — NEW 모드 (NEW 선택 시)

별도 분석 없이 Step 3으로 진행.

---

## Step 3 — 프로젝트 단계 확인

`.harness/profile.json`이 이미 존재하면 현재 단계를 보여주고:
> "현재 단계: {stage}. 변경하겠습니까?"

없으면 아래 질문:
> "프로젝트 단계를 선택해 주세요.
> 1. prototype — 빠른 검증·데모. 가볍게 시작.
> 2. mvp — 실사용자 대상 출시 가능 목표.
> 3. production — 운영 목표. 가용성·보안·관리 필수."

선택 후 `.harness/profile.json`을 업데이트하라:
```json
{
  "stage": "<선택>",
  "project_name": "<프로젝트명>",
  "tech": { "backend": "<백엔드>", "frontend": "<프론트엔드>" },
  "updated_at": "<ISO8601>"
}
```

> **명칭 vs 디렉터리 안내:** `project_name`은 PRD·문서·release-note 등 메타데이터에 쓰이는 **표시 이름**이다. 실제 소스 디렉터리는 모노레포 기본 레이아웃(`backend/`, `frontend/`)을 사용하며, 에이전트가 Step 5 이후 코드를 생성할 때 해당 경로에 직접 파일을 생성한다. `tech.backend`·`tech.frontend` 값은 폴더명이 아니라 **기술 스택 식별자**(`spring-boot-3`, `react-18` 등)이다.

---

## Step 3-1 — CLAUDE.md·문서와 `tech` 통합 (필수)

Step 3에서 반영된 **`tech`와 `CLAUDE.md` 제목**이 다르거나, `CLAUDE.md`가 완전히 하네스 기본(Spring Boot + React) 템플릿 그대로이면 **Step 4 전**에 아래를 수행한다.

1. `profile.json`의 `tech`를 단일 출처로 삼아 선택을 확정한다.
2. **`CLAUDE.md`**를 확정 선택에 맞게 상단 준비한다.
3. 이미 존재하는 **`.harness/docs/*`** 중 선택에 의존하는 파일이 있으면 같은 세션에서 맞춘다 (없으면 이후 생성 시 반영).

EXISTING에서 Step 2A-1을 이미 수행했다면 중복은 생략하고 **변경된 내용만** 보완한다.

---

## Step 4 — 참고 프로젝트 입력

**반드시** 아래 질문을 하라:
> "이 프로젝트에는 비슷한 라이브러리·코드/문서 등 참고할 만한 프로젝트가 있나요?
> git URL 또는 로컬 절대 경로를 입력해 주세요. 없으면 '없음'이라고 답해주세요."

URL/경로가 주어지면:
```
python .harness/scripts/references.py add <url-or-path> --purpose "<입력한 용도>"
```
없으면 메모에 "참고 프로젝트 없음"으로 기록하고 계속 진행.

---

## Step 5 — 문서 충실도 검증 (2단 게이트)

**1단 — syntactic 검증:**
```
python .harness/scripts/validate_docs.py --stage <stage> --json
```

결과에 errors > 0이면:
- 오류 목록을 사용자에게 표시
- 항목별로 수정 방법을 안내하고 Q&A로 내용 보완
- 보완 후 검증 재실행

경고가 있으면: 목록 표시 후 계속 진행 여부 확인.
오류 0건 통과 후 → **2단 게이트 진행**:

**2단 — AI 페르소나 검증:**
```
python .harness/scripts/review_docs.py --stage <stage>
```

- auto_fillable 갭: AI가 자동 보완 (diff 확인)
- needs_decision 갭: Q&A로 사용자 결정 유도
- 임계점수 도달 시: "✅ 페르소나 리뷰 통과 (평균 {score}점)"
- 미통과 시: 남은 갭 목록과 함께 안내 (사람의 결단 필요 영역 인계)

> 두 게이트 모두 통과해야 Step 6으로 진행한다.
> 오류/미통과 시 처리 절차는 `/a2m_check_docs` 명령과 동일하다.

---

## Step 6 — B. 기술 설계

사용자가 제시한 기능/수정 요구를 받아 기술적으로 설계하라:
- 구현 방식 선택지 제시
- 트레이드오프 설명
- 단계(stage)에 맞는 깊이로 설계

---

## Step 7 — C. Step 계획

설계된 내용을 step으로 분해하라.

각 step을 다음 형식으로 계획하라:
```markdown
---
relevant_docs: ["ARCHITECTURE", "CODING_CONVENTION"]
relevant_references: ["<참고프로젝트명>"]
---

# Step N: <이름>

## 목표
<한 줄 목표>

## 작업 내용
1. <작업 1>
2. <작업 2>

## Acceptance Criteria (단계별 강도 적용)
- [ ] <AC 1>
- [ ] <AC 2>
```

**단계별 AC 기준**:
- prototype: 빌드 통과 + 핵심 기능 작동
- mvp: 빌드 + 단위 테스트 + 입력 검증
- production: 빌드 + 단위/통합 테스트 + 커버리지 + 보안 스캔

사용자 확인 후 Step 8

---

## Step 8 — D. 파일 생성

> **runId 생성 단일화**: runId는 항상 이 명령(`/a2m_start`)에서 생성한다.
> `execute.py`가 자동으로 runId를 생성하는 경로는 **deprecated**이며 다음 메이저 버전에서 제거될 예정이다.
> execute.py를 직접 `task`만 인자로 실행하지 않도록 주의.

```python
# runId 생성 (KST 기준)
from datetime import datetime, timezone, timedelta
TZ = timezone(timedelta(hours=9))
run_id = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
```

1. `.harness/phases/<task>/<runId>/` 디렉토리 생성
2. `.harness/phases/<task>/<runId>/index.json` 생성 (step 목록, status=pending)
3. `.harness/phases/<task>/<runId>/step{N}.md` 각 파일 생성
4. `.harness/phases/index.json`의 `runs[]`에 **append** (덮어쓰기 금지!)

index.json 형식:
```json
{
  "project": "<프로젝트명>",
  "phase": "<task>",
  "branch": "feat/<task>-<runId>",
  "stage": "<stage>",
  "steps": [
    { "step": 0, "name": "<이름>", "status": "pending" }
  ]
}
```

---

## Step 9 — E. 실행

```
python .harness/scripts/execute.py <task>/<runId> [--auto-review] [--pr]
```

production 단계는 `--auto-review` 자동 추가 권장.
완료 후 `.harness/release-notes/` 폴더의 생성 파일을 안내하라.
