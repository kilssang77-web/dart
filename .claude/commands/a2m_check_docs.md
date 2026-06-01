---
description: docs 폴더의 플레이스홀더·공란·누락 항목 + AI 페르소나 충실도를 검증합니다
---

신규 `/a2m_check_docs` 명령입니다.
.harness/docs/ 폴더의 문서 충실도를 독립으로 확인합니다.
2단 게이트: syntactic 검증(validate_docs.py) → AI 페르소나 검증(review_docs.py)

---

## Step 1 — 단계 확인

`.harness/profile.json`을 열어 현재 단계를 확인하라.
없으면 사용자에게 단계를 질문하라 (prototype / mvp / production).

---

## Step 2 — 1차 게이트: syntactic 검증

```
python .harness/scripts/validate_docs.py --stage <stage> --json
```

결과를 분류하여 보여주라:

### 오류 (즉시 수정 필요)
- 스켈레톤 배너가 그대로 남아 있는 파일 목록
- 단계별 필수 섹션이 없는 파일 목록

### 경고 (권장 수정)
- 플레이스홀더 `{...}` 잔존 항목
- TODO/TBD 잔존 항목
- 빈 섹션이 있는 파일

### 정보
- 예시 항목(게시판 컨텍스트)이 그대로인 파일

오류가 있으면 사용자에게 내용을 질문하고 파일을 수정한 뒤 재검증. **오류가 0건이 될 때까지 2차 게이트로 진행하지 않는다.**

---

## Step 3 — 2차 게이트: AI 페르소나 충실도 검증

syntactic 오류가 0건이면 페르소나 리뷰를 실행한다:

```
python .harness/scripts/review_docs.py --stage <stage>
```

> 이 단계는 Claude CLI를 사용합니다. 시간이 걸릴 수 있습니다.

결과 표시:
- 페르소나별 점수와 가중 평균
- critical 페르소나 veto 여부
- 갭 목록 (auto_fillable vs needs_decision)

### auto_fillable 갭
코드베이스·CLAUDE.md·profile.json 컨텍스트로 채울 수 있는 항목을 직접 수정하고 diff를 사용자에게 보여준 뒤 승인을 받아 적용한다.

### needs_decision 갭
설계 결정·사용자 선호가 필요한 항목은 Q&A로 종결한다.

보완 후 `review_docs.py`를 재실행하여 점수가 임계점 이상인지 확인한다. 최대 3회 반복.

---

## Step 4 — Q&A 보완 후 재확인

오류/갭 해소 후 검증을 재실행:

```
python .harness/scripts/validate_docs.py --stage <stage>
python .harness/scripts/review_docs.py --stage <stage>
```

---

## Step 5 — 완료

두 게이트 모두 통과하면:
> "✅ docs 충실도 검증 완료 (syntactic + 페르소나 리뷰). 다음 단계: /a2m_start"

경고만 남아 있으면:
> "⚠ {N}건 경고 있음. 계속 진행해도 됩니까?"
