# 진행 상황 정리 (PROGRESS)

> 금융/트렌드 AI 시그널 리포트 플랫폼 — 국내 주식 뉴스 감정 급변 시그널 대시보드
> 최종 업데이트: 2026-07-25 · 리모트: `github.com/sanngrok/briefing` (main)

---

## 1. 한눈에 보기

- **상태**: M0~M8 + UI 리디자인 완료. 코드/구조는 전부 준비됨.
- **일시 중지 지점**: 실제 API 키(Supabase / Anthropic / 네이버) 연결 대기 중.
- **방식**: "구조 우선, 키 연동 나중" — 키 없이 순수 함수·목(mock)으로 검증하며 진행.
- **테스트**: 파이프라인 단위 테스트 36개 + API 테스트 13개, 모두 키 없이 통과.

---

## 2. 아키텍처 (읽기/쓰기 2-레이어 분리)

```
[레이어 A] GitHub Actions cron (평일 16:00 KST)
   시세·뉴스 수집 → LLM 감정/태그 → 감정 집계 → 급변 시그널 → LLM 리포트
        │ write
        ▼
   Supabase (Postgres)
        ▲ read only
        │
[레이어 B] FastAPI (읽기 전용) ── JSON
        ▼
[레이어 C] Vercel 프론트 (KPI · 시그널 카드 · 차트 · 리포트)
```

파이프라인(쓰기)과 서빙 API(읽기)를 분리해, 무료 인스턴스가 슬립해도 스케줄 잡이 독립 실행된다.

---

## 3. 저장소 구조

```
briefing/
├── db/schema.sql              # 6개 테이블 DDL (tickers/prices/news/sentiment_daily/signals/reports)
├── pipeline/                  # 레이어 A (쓰기)
│   ├── pipeline.py            # 수집→감정→집계→시그널→리포트 오케스트레이터 + 순수 함수
│   ├── seed_tickers.py        # 워치리스트 시드 (멱등)
│   ├── check_prices.py        # 시세 검증(키 불필요)
│   ├── requirements.txt / requirements-dev.txt
│   └── tests/                 # test_news_parse / test_signal / test_report
├── api/                       # 레이어 B (읽기 전용 FastAPI)
│   ├── main.py config.py db.py models.py services.py
│   ├── routers/               # reports / tickers / signals
│   └── tests/test_api.py      # TestClient (DB 불필요)
├── frontend/                  # 레이어 C (Vite + React + TS + Recharts)
│   └── src/                   # App / api / components(SummaryStrip·SignalCard·SentimentChart·ReportView·DisclaimerBadge)
├── .github/workflows/pipeline.yml   # cron + workflow_dispatch
├── .env.example               # 환경변수 문서
└── README.md / PROGRESS.md
```

---

## 4. 마일스톤 진행 현황

| # | 내용 | 상태 | 핵심 산출물 |
|---|---|---|---|
| M0 | 스캐폴딩 & 시크릿 골격 | ✅ | 폴더 구조, .env.example, .gitignore, README |
| M1 | 스키마 적용 & 워치리스트 시드 | ✅ | `seed_tickers.py`(멱등 upsert), DB 준비 절차 |
| M2 | 시세 슬라이스 (pykrx) | ✅ | `fetch_latest_price`, 비영업일/체결일 버그 수정 |
| M3 | 뉴스 + 감정 슬라이스 | ✅ | `parse_news_item`/`parse_sentiment` + 테스트 11 |
| M4 | 집계 & 시그널 (+단위테스트) | ✅ | `decide_signal`/`classify_severity` + 경계값 테스트 18 |
| M5 | 리포트 (그라운딩) | ✅ | `build_report_payload/prompt` + 면책 라벨 + 테스트 7 |
| M6 | FastAPI 서빙 레이어 | ✅ | 엔드포인트 4종 + Pydantic 모델 + 테스트 13 |
| M7 | 프론트엔드 (Recharts) | ✅ | 대시보드, npm build 통과 |
| M8 | GitHub Actions 워크플로우 | ✅ | `pipeline.yml`(cron 16:00 KST + 수동) |
| — | UI 리디자인 (옵션 A) | ✅ | 요약 우선 KPI 대시보드, 라이트/다크 지원 |
| **M9** | **배포** | ⬜ | **다음 단계 (아래 §7)** |

---

## 5. 레이어별 완성 내용

### 레이어 A — 파이프라인 (pipeline/)
- 6단계: 시세(pykrx) → 뉴스(네이버) → 감정(Haiku) → 일집계 → 시그널 → 리포트(Sonnet).
- 멱등성: 모든 쓰기는 UNIQUE 키 upsert. 뉴스는 `url_hash` dedup으로 LLM 재호출 방지(비용 방어).
- 순수 함수 분리: 파싱·감정·시그널·리포트 payload를 I/O에서 떼어내 단위 테스트로 고정.
- 외부 클라이언트/의존성은 지연(lazy) 생성 → 키 없이 단계별 검증 가능.

### 레이어 B — FastAPI (api/)
- 읽기 전용(Repository 패턴), CORS는 프론트 도메인만·GET만 허용.
- 엔드포인트: `/api/reports/latest`, `/api/reports/{date}`, `/api/tickers/{symbol}/metrics`, `/api/signals`.
- 404/422·`from>to` 검증, Pydantic 응답 모델로 계약 고정.

### 레이어 C — 프론트 (frontend/)
- 요약 우선 대시보드: 상단 KPI 스트립 → 시그널 카드 → 종목 추이 차트 → 일일 리포트.
- 심각도=의미 색(high 빨강/mid 주황/low 회색), 모노 숫자, 라이트/다크 자동.
- "투자 판단 근거 아님" 면책 라벨(상·하단), 백엔드 미연결 시 graceful degrade.

---

## 6. 하드 룰 준수 체크

- ✅ 공개 데이터만 사용 · ✅ 투자 자문 아님 라벨(UI+리포트)
- ✅ 멱등성(UNIQUE+upsert) · ✅ 읽기/쓰기 분리(FastAPI는 SELECT만)
- ✅ 비밀키 코드 미포함(.env / Secrets) · ✅ LLM 그라운딩(실데이터 JSON만 근거)
- ✅ 비용 방어(url_hash dedup) · ✅ 작은 커밋, 항상 실행 가능 상태 유지

---

## 7. 다음에 진행할 것

### 7-A. (지금) API 연결 — 사용자 작업
데이터가 실제로 흐르게 하려면 아래 순서로 연결:

1. **Supabase**: 프로젝트 생성 → SQL Editor에 `db/schema.sql` 실행 → `Project URL`·`service_role` 키 확보.
2. **키 발급**: 네이버 개발자센터(Client ID/Secret), Anthropic 콘솔(API Key).
3. **파이프라인 실행** (`pipeline/.env` 작성 후):
   ```bash
   cd pipeline && pip install -r requirements.txt
   python seed_tickers.py     # 종목 4개
   python pipeline.py         # 데이터 적재
   ```
   env: `SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
4. **FastAPI 기동** (`api/.env` 작성 후):
   ```bash
   uvicorn api.main:app --reload
   ```
   env: `SUPABASE_URL`, `SUPABASE_KEY`(읽기=anon 권장), `CORS_ORIGINS=http://localhost:5173`
5. **프론트 연결** (`frontend/.env`에 `VITE_API_BASE=http://127.0.0.1:8000`):
   ```bash
   cd frontend && npm run dev
   ```

> 각 `.env`는 해당 폴더 `.env.example` 복사해서 채움(`.env`는 gitignore).

### 7-B. 연결 후 확인
- 실제 데이터로 대시보드 채워진 화면 확인(시그널 카드 색·차트·리포트).
- 초기엔 감정 기준선 히스토리가 부족해 시그널이 잘 안 뜨는 게 정상.
- 파이프라인 로그로 각 단계 건수 확인(`[price] N건` 등).

### 7-C. M9 — 배포 (다음 마일스톤)
- **FastAPI → Render/Fly**: `render.yaml`(또는 fly.toml) 작성, 환경변수 등록.
- **프론트 → Vercel**: 빌드 설정, `VITE_API_BASE`를 배포된 API 주소로.
- **GitHub Actions Secrets** 등록 후 `workflow_dispatch`로 파이프라인 1회 수동 실행.
- **keep-alive**: Render 무료 슬립 대비 핑용 cron 워크플로우(`.github/workflows/keepalive.yml`).
- CORS를 실제 프론트 도메인으로 갱신.

---

## 8. 확인 필요 / 주의사항

- `pipeline/pipeline.py`의 모델명(`claude-sonnet-5`, `claude-haiku-4-5-20251001`)이 실제 사용 가능한 값인지 첫 실행 시 확인.
- pykrx는 주말/공휴일에도 최근 영업일 데이터를 가져오지만, 네이버 뉴스는 당일 검색이라 초기 시그널 발화가 적을 수 있음.
- 프론트 번들이 recharts로 약 650KB(gzip 190KB) — 필요 시 code-splitting 여지.
- npm audit 취약점 2건(대부분 dev 의존성 추이) — 배포 전 판단.
