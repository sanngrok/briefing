# 레이어 B — FastAPI 서빙 (읽기 전용)

Supabase 를 **읽기만** 한다(쓰기 금지, 하드룰 §4). CORS 는 프론트 도메인만, GET 만 노출.

## 구조
```
api/
├── main.py         # 앱 진입점 + CORS + 라우터 등록
├── config.py       # 환경변수(SUPABASE_URL/KEY, CORS_ORIGINS)
├── db.py           # ReadRepo (읽기 전용 Repository) + get_repo 의존성
├── models.py       # Pydantic 응답 모델 (API 계약)
├── services.py     # 순수 변환 로직 (row → 응답)
├── routers/        # reports / tickers / signals
└── tests/          # TestClient + dependency_overrides (DB 불필요)
```

## 엔드포인트
- `GET /api/reports/latest`
- `GET /api/reports/{date}`
- `GET /api/tickers/{symbol}/metrics?from=&to=`
- `GET /api/signals?date=&severity=`

## 실행 / 테스트 (repo 루트에서)
```bash
pip install -r api/requirements-dev.txt
uvicorn api.main:app --reload
python -m pytest api/tests -v
```
