---
step: 2
name: "최종 추천 레포트 PDF 출력 (TenderRecommendPage)"
relevant_docs: ["PRD", "CODING_CONVENTION"]
relevant_references: []
---

## 목표
TenderRecommendPage (/bids/:id/final-recommend) 에 PDF 출력 버튼을 추가한다.
jsPDF + html2canvas (이미 설치된 패키지) 활용, A4 다중 페이지 지원.

## 구현 상세
- 헤더 우측 "PDF 출력" 버튼 (Printer 아이콘)
- 출력 중 Loader2 스피너 (비활성화)
- printRef div 로 전체 콘텐츠 감싸기
- 파일명: 투찰추천_{bid_id}.pdf
