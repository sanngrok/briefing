# 레이어 B — FastAPI 서빙 (읽기 전용)

M6 에서 구현합니다. Supabase 를 **읽기만** 합니다 (쓰기 금지).

예정 엔드포인트:
- `GET /api/reports/latest`
- `GET /api/reports/{date}`
- `GET /api/tickers/{symbol}/metrics?from=&to=`
- `GET /api/signals?date=&severity=`

CORS 는 프론트 도메인만 허용, 응답은 Pydantic 모델로 고정합니다.
