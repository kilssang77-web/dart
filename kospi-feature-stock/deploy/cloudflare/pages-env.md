# Cloudflare Pages 환경변수 설정 가이드

## 설정 경로
Cloudflare Dashboard → Pages → quant-eye → Settings → Environment variables

## 등록할 환경변수

| 변수명 | 값 | 환경 |
|---|---|---|
| `VITE_API_URL` | `https://quant-eye-api.fly.dev` | Production |
| `VITE_API_URL` | `http://localhost:8000` | Preview |

## Build 설정

| 항목 | 값 |
|---|---|
| Framework preset | None (직접 설정) |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `kospi-feature-stock/frontend` |
| Node.js version | `20` |

## 자동 배포 트리거
- `main` 브랜치 push → Production 자동 배포
- PR 생성 → Preview 자동 배포

## 커스텀 도메인 (선택)
1. Pages → Custom domains → Add custom domain
2. 보유 도메인 입력 → Cloudflare DNS에 CNAME 자동 등록
3. SSL: Cloudflare가 자동 발급

## 배포 확인 URL
https://quant-eye.pages.dev
