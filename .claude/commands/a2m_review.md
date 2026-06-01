---
description: 변경된 코드를 체크리스트 기반으로 리뷰합니다
---

이 프로젝트의 변경 사항을 리뷰하라.

먼저 다음 문서들을 읽어라:
- `/CLAUDE.md`
- `/.harness/docs/ARCHITECTURE.md`
- `/.harness/docs/ADR.md`
- `/.harness/docs/CODING_CONVENTION.md`
- `/.harness/docs/SCHEMA.md` (존재하는 경우)

> **production 단계라면**: `.harness/docs/.review/` 디렉토리에서 최신 `production_*.json` 파일을 확인하여 `verdict`와 `average` 점수를 리뷰 결과에 반영하라 (선택).
> 예: `average: 88`, `verdict: fail`, `gaps: [...]` 가 있다면 해당 갭 항목을 체크리스트에 추가한다.

그런 다음 변경된 파일을 다음 순서로 확인하고, 아래 체크리스트로 검증하라:

1. `git merge-base origin/main HEAD` 로 merge-base를 구한 뒤 `git diff <merge-base>..HEAD` 를 실행한다.
2. 위가 실패하면 (remote 없음 / single-commit 브랜치) `git diff HEAD~1..HEAD` 로 fallback한다.

## 체크리스트
1. **아키텍처 준수**: ARCHITECTURE.md에 정의된 레이어 구조를 따르는가?
   - Controller에 비즈니스 로직이 없는가?
   - Repository를 Service 밖에서 직접 호출하지 않는가?
2. **기술 선택 준수**: ADR에 정의된 기술 선택을 벗어나지 않았는가?
3. **코딩 컨벤션**: CODING_CONVENTION.md의 네이밍·구조 규칙을 따르는가?
4. **스키마 마이그레이션**: DB 관련 변경이 있는 경우
   - 새 테이블·컬럼 추가 시 마이그레이션 파일(`V{n}__...sql`)이 함께 생성되었는가?
   - 기존 마이그레이션 파일을 수정하지 않았는가? (수정은 금지, 새 파일 추가만 허용)
   - SCHEMA.md의 테이블 설계가 실제 엔티티·마이그레이션과 일치하는가?
   - NOT NULL 컬럼 추가 시 기본값 또는 backfill이 포함되어 있는가?
5. **테스트 존재**: 새로운 기능에 대한 테스트가 생성되어 있는가? (단계별 기준 적용)
6. **CRITICAL 규칙**: CLAUDE.md의 CRITICAL 규칙을 위반하지 않았는가?
7. **보안 기초**: 외부 입력 검증 있음, 비밀값 하드코딩 없음, 로그에 민감정보 없음?
8. **빌드/테스트 결과**: 빌드 명령이 오류 없이 통과하는가?

## 출력 형식

| 항목 | 결과 | 비고 |
|------|------|------|
| 아키텍처 준수 | ✅/❌/N/A | {세부} |
| 기술 선택 준수 | ✅/❌/N/A | {세부} |
| 코딩 컨벤션 | ✅/❌/N/A | {세부} |
| 스키마 마이그레이션 | ✅/❌/N/A | {세부 — DB 변경 없으면 N/A} |
| 테스트 존재 | ✅/❌/N/A | {세부} |
| CRITICAL 규칙 | ✅/❌/N/A | {세부} |
| 보안 기초 | ✅/❌/N/A | {세부} |
| 빌드/테스트 | ✅/❌/N/A | {세부} |

위반 항목이 있으면 수정 방안을 구체적으로 제시하라.
위반 항목이 없으면 "✅ 리뷰 완료" 한 줄로 마무리하라.
