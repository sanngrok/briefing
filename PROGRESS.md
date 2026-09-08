# 진행 상황 정리 (PROGRESS)

> 금융/트렌드 AI 시그널 리포트 플랫폼 — 국내 주식 뉴스 감정 급변 시그널 대시보드
> 최종 업데이트: 2026-09-08 · 리모트: `github.com/sanngrok/briefing` (main)

---

## 1. 한눈에 보기

- **상태**: **M0~M9 전부 완료. 3개 레이어가 실제로 운영 중.**
- **운영 주소**:
  - 프론트: https://briefing-lake.vercel.app
  - API: https://briefing-6pzj.onrender.com
  - 파이프라인: GitHub Actions cron (평일 16:00 KST)
- **LLM**: Anthropic → **Google Gemini 무료 티어**로 전환 (`gemini-3.5-flash` / `-flash-lite`).
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
| **M9** | **배포** | ✅ | Render(API) + Vercel(프론트) + Actions Secrets 등록·실행 검증 |

---

## 5. 레이어별 완성 내용

### 레이어 A — 파이프라인 (pipeline/)
- 6단계: 시세(pykrx) → 뉴스(네이버) → 감정(`gemini-3.5-flash-lite`) → 일집계 → 시그널 → 리포트(`gemini-3.5-flash`).
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

## 7. 배포 구성 (M9 완료 상태)

### 7-A. 레이어별 배포 위치·환경변수

| 레이어 | 플랫폼 | 환경변수 |
|---|---|---|
| A. 파이프라인 | GitHub Actions (repo Secrets) | `SUPABASE_URL`, `SUPABASE_KEY`(service_role), `GEMINI_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |
| B. API | Render (Web Service, Free) | `SUPABASE_URL`, `SUPABASE_KEY`(**anon**), `CORS_ORIGINS` |
| C. 프론트 | Vercel (Root Directory=`frontend`) | `VITE_API_BASE` |

- Render Build: `pip install -r api/requirements.txt` / Start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Python 버전은 `runtime.txt`(3.12)로 고정 — Render 기본값이 최신 Python이라 호환성 이슈 방지.
- `CORS_ORIGINS`에는 Vercel production + git 프리뷰 도메인을 콤마로 함께 등록.

### 7-B. 연동 중 실제로 막혔던 지점 (재구축 시 참고)

1. **네이버 검색 API가 NCP로 이관됨** — 구 `developers.naver.com`의 `openapi.naver.com` +
   `X-Naver-Client-Id/Secret` 방식이 아니라, NCP *Naver API Hub*는
   `naverapihub.apigw.ntruss.com/search/v1/news` + `X-NCP-APIGW-API-KEY-ID/KEY` 헤더를 쓴다.
   또한 애플리케이션에 "뉴스" API를 개별로 추가 신청해야 한다.
2. **Gemini 2.5 계열은 신규 사용자에게 제공 종료** — `models.list()`에는 보이지만 호출 시 404.
   현재는 3.5 계열 사용.
3. **무료 티어 15 RPM 제한** — 뉴스 40건을 연속 호출하면 대부분 429. `SENTIMENT_CALL_INTERVAL`(4.5초)로 간격 확보.
4. **Gemini 3.x의 thinking 토큰이 `max_output_tokens`를 소진** — 리포트 본문이 잘리고 모델의
   자기검증 메모만 저장되는 현상. `thinking_config=ThinkingConfig(thinking_budget=0)`으로 해결.
5. **Supabase 자동 RLS** — 프로젝트 생성 시 "Enable automatic RLS"가 켜져 있으면 모든 테이블에
   RLS가 걸리고 정책이 없어 **anon 키로는 전 테이블 0건**이 된다(service_role은 우회하므로 눈치채기 어려움).
   공개 데이터만 다루므로 `alter table ... disable row level security`로 해제.
6. **Vercel Deployment Protection** — 기본 활성 시 비로그인 방문자가 SSO 로그인으로 리다이렉트된다. 공개 대시보드이므로 해제 필요.
7. **Vercel 환경변수 자동 제안** — 루트 `.env.example`을 읽어 백엔드 키까지 제안하지만,
   프론트에 필요한 건 `VITE_API_BASE` 하나뿐. 나머지는 넣지 말 것(불필요한 시크릿 확산).

---

## 8. 다음에 할 만한 것 / 주의사항

### 다음 후보
- **keep-alive 워크플로우**: Render 무료 티어는 15분 미사용 시 슬립 → 첫 요청 30~60초 지연.
  `.github/workflows/keepalive.yml`로 주기적 핑을 넣으면 완화 가능.
- **시그널 발화 관찰**: `baseline`은 직전 5영업일 평균이라, 히스토리가 쌓이기 전(초기 며칠)에는
  `baseline == avg`가 되어 delta 0 → 시그널 미발화가 정상. 며칠 운영 후 실제 발화 확인 필요.
- **Actions 워크플로우 액션 버전**: `actions/checkout@v4`, `setup-python@v5`가 Node 20 지원 종료 경고.
  동작에는 지장 없으나 추후 상위 버전으로 갱신 여지.

### 주의사항
- pykrx는 주말/공휴일에도 최근 영업일 데이터를 가져오지만, 네이버 뉴스는 당일 검색이라 초기 시그널 발화가 적을 수 있음.
- 프론트 번들이 recharts로 약 650KB(gzip 190KB) — 필요 시 code-splitting 여지.
- npm audit 취약점 2건(대부분 dev 의존성 추이).
- 뉴스 감정 호출이 기사 수에 비례해 느려짐(4.5초 × N). 워치리스트를 늘리면 실행 시간도 함께 증가.
