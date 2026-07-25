# 레이어 C — 프론트엔드 (Vercel)

Vite + React + TypeScript + Recharts.

## 구성
- `src/api/client.ts` — 백엔드 호출 + 응답 타입(Pydantic 계약과 일치)
- `src/components/SentimentChart.tsx` — 종가·평균 감정 이중축 시계열 차트
- `src/components/SignalCard.tsx` — severity(high/mid/low) 색상 카드
- `src/components/ReportView.tsx` — react-markdown 리포트
- `src/components/DisclaimerBadge.tsx` — "투자 판단 근거 아님" 라벨(§2)
- `src/App.tsx` — 종목 탭 전환 + 데이터 로딩/에러 처리

## 실행
```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 타입체크 + dist/
```
환경변수 `VITE_API_BASE`(기본 `http://127.0.0.1:8000`).
