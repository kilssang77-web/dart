---
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCREEN_MAP"]
relevant_references: ["info21c"]
---

# Step 4: 관리자 UI — 수집 현황 패널

## 목표
AdminPage에 수집 현황 탭 추가, 수동 트리거 버튼 구현

## 작업 내용
1. `bid-system/frontend/src/types/index.ts` — `CollectionLogOut` 타입 추가
2. `bid-system/frontend/src/api/index.ts`
   - `getCollectionLogs()` 함수 추가
   - `triggerCollect(collectType: 'all' | 'notices' | 'results')` 함수 추가
3. `bid-system/frontend/src/pages/AdminPage.tsx`
   - "수집 현황" 탭 추가
   - 수집 로그 테이블 (수집일시, 유형, 성공건수, 실패건수, 소요시간)
     - 성공건수 > 0: 초록색, 실패건수 > 0: 빨간색
   - "지금 수집" 드롭다운 버튼 (전체/공고만/결과만)
     - 클릭 시 로딩 스피너 → 완료 후 toast 메시지 + 로그 목록 자동 갱신
   - TanStack Query `useQuery` + `useMutation` 사용

## Acceptance Criteria (mvp)
- [ ] 빌드 통과 (TypeScript 오류 없음, `any` 타입 없음)
- [ ] "지금 수집" 버튼 클릭 → 로딩 상태 → 완료 toast → 로그 갱신
- [ ] 성공/실패 건수 색상 구분 렌더링
- [ ] admin 역할 사용자만 탭 접근 가능
