# 진행 상황 정리 (PROGRESS)

> 금융/트렌드 AI 시그널 리포트 플랫폼 — 국내 주식 뉴스 감정 급변 시그널 대시보드
> 최종 업데이트: 2026-09-23 · 리모트: `github.com/sanngrok/briefing` (main)

---

## 1. 한눈에 보기

- **상태**: **M0~M12 전부 완료. 3개 레이어가 실제로 운영 중.**
- **운영 주소**:
  - 프론트: https://briefing-lake.vercel.app
  - API: https://briefing-6pzj.onrender.com
  - 파이프라인: GitHub Actions cron (평일 16:00 KST)
- **LLM**: Anthropic → **Google Gemini 무료 티어**로 전환 (`gemini-3.5-flash` / `-flash-lite`).
- **테스트**: 파이프라인 74개 + API 73개 + 프론트 49개(vitest) + 증권사 동기화 19개, 모두 키 없이 통과.
- **시그널**: 2026-09-21 실행에서 **5건 발화 확인** (아래 §5-A). 기준선이 쌓여 규칙이 실제로 동작한다.

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
│   ├── seed_tickers.py        # 워치리스트 시드 (멱등) + 보유 종목 병합 (M12)
│   ├── check_prices.py        # 시세 검증(키 불필요)
│   ├── requirements.txt / requirements-dev.txt
│   └── tests/                 # test_news_parse / test_signal / test_report / test_generate_text / test_seed_tickers
├── api/                       # 레이어 B (읽기 전용 FastAPI)
│   ├── main.py config.py db.py models.py services.py
│   ├── routers/               # reports / tickers / signals / news / movers / quotes
│   └── tests/test_api.py      # TestClient (DB 불필요)
├── frontend/                  # 레이어 C (Vite + React + TS + Recharts)
│   └── src/                   # App / api / components(SummaryStrip·SignalCard·SentimentChart·ReportView·PortfolioPanel·DisclaimerBadge)
│       └── lib/portfolio.ts   # 내 포트폴리오 계산·저장 순수 함수 + portfolio.test.ts
├── tools/                     # 내 PC 전용 (배포 안 됨)
│   ├── toss_sync.py           # 토스증권 Open API → portfolio.json (M11)
│   └── tests/test_toss_sync.py
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
| **M10** | **내 포트폴리오** | ✅ | 보유 종목 CRUD + 평가손익·수익률·비중 + `/api/quotes` + vitest 30 |
| **M11** | **토스증권 연동** | ✅ | `tools/toss_sync.py` (로컬 전용) — 실계좌 잔고 → portfolio.json → 가져오기 |
| **M12** | **보유 종목 워치리스트 반영** | ✅ | `seed_tickers.py` 가 portfolio.json 을 자동 병합 + 테스트 13 |

---

## 5. 레이어별 완성 내용

### 레이어 A — 파이프라인 (pipeline/)
- 6단계: 시세(pykrx) → 뉴스(네이버) → 감정(`gemini-3.5-flash-lite`) → 일집계 → 시그널 → 리포트(`gemini-3.5-flash`).
- 멱등성: 모든 쓰기는 UNIQUE 키 upsert. 뉴스는 `url_hash` dedup으로 LLM 재호출 방지(비용 방어).
- 순수 함수 분리: 파싱·감정·시그널·리포트 payload를 I/O에서 떼어내 단위 테스트로 고정.
- 외부 클라이언트/의존성은 지연(lazy) 생성 → 키 없이 단계별 검증 가능.

### 레이어 B — FastAPI (api/)
- 읽기 전용(Repository 패턴), CORS는 프론트 도메인만·GET만 허용.
- 엔드포인트: `/api/reports/latest`, `/api/reports/{date}`, `/api/tickers`, `/api/tickers/{symbol}/metrics`,
  `/api/signals`, `/api/news`, `/api/movers`, `/api/quotes`.
- 404/422·`from>to` 검증, Pydantic 응답 모델로 계약 고정.

### 레이어 C — 프론트 (frontend/)
- 요약 우선 대시보드: 상단 KPI 스트립 → 시그널 카드 → 종목 추이 차트 → 일일 리포트.
- 심각도=의미 색(high 빨강/mid 주황/low 회색), 모노 숫자, 라이트/다크 자동.
- "투자 판단 근거 아님" 면책 라벨(상·하단), 백엔드 미연결 시 graceful degrade.
- **내 포트폴리오(M10)**: 보유 종목을 직접 입력/수정/삭제하고 최근 영업일 종가로
  평가금액·평가손익·수익률·비중·전일 대비 손익을 계산. 보유 종목에 시그널이 걸리면 배지로 연결.
  같은 종목 재입력은 수량가중 평단으로 합산(물타기), JSON 내보내기/가져오기로 기기 간 이전.

### 5-A. 시그널 발화 실측 (2026-09-21, run #42)

기준선(직전 5영업일 평균)이 쌓이기 전에는 `baseline == avg` 라 delta 0 → 미발화가 정상이었다.
운영이 누적되면서 규칙이 실제로 동작하는 것을 확인했다.

| 종목 | 방향 | delta | 심각도 |
|---|---|---|---|
| 삼성전기 (009150) | `sentiment_surge_neg` | −1.08 | high |
| 현대모비스 (012330) | `sentiment_surge_pos` | +0.77 | high |
| HD현대중공업 (329180) | `sentiment_surge_pos` | +0.72 | high |
| 삼성전자 (005930) | `sentiment_surge_pos` | +0.57 | mid |
| 하나금융지주 (086790) | `sentiment_surge_neg` | −0.41 | low |

같은 실행의 수집량: 시세 20건 upsert · 신규 뉴스 146건 · 감정 146건 처리 · 리포트 1건.
실행 시간 14분 48초 — 감정 호출이 기사 수 × 4.5초(무료 티어 15 RPM 회피)라 기사가 많은 날은 길어진다.

> 참고: 로그에 뜨는 `KRX 로그인 실패: KRX_ID 또는 KRX_PW ...` 는 pykrx 메시지이고
> 바로 다음 줄에서 시세 20건이 정상 적재된다(공개 엔드포인트 폴백). 무해한 경고다.

---

### M10 — 내 포트폴리오를 왜 localStorage 에 두었나

개인 매매 정보(보유 수량·평단)를 서버에 올리면 **① 읽기/쓰기 분리(하드룰 §4)** 가 깨지고
**② 인증이 없어 누구나 남의 데이터를 고칠 수 있다**. 두 문제를 동시에 풀려면 로그인부터
붙여야 하므로, 이번엔 브라우저 `localStorage` 에만 저장하는 쪽을 택했다.

- 서빙 API 는 계속 GET 전용 — 새로 추가한 `/api/quotes` 도 읽기다(최근 영업일 종가·등락률).
  보유 종목이 N개일 때 `/api/tickers/{symbol}/metrics` 를 N번 부르지 않게 한 번에 받아간다.
- 워치리스트 밖 종목도 담을 수 있다. 시세가 없으면 "시세 없음"으로 표시하고
  **수익률 분모(pricedCost)에서 제외**해 숫자가 왜곡되지 않게 했다.
- 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 앱이 죽지 않고 경고만 띄운다.
- 기기 간 이전은 JSON 내보내기/가져오기. 나중에 인증을 붙이면 이 JSON 형태
  (`{version, holdings}`)를 그대로 DB 로 옮기면 된다.

### M11 — 증권사 연동을 왜 서버가 아니라 내 PC 에서 하나

토스증권 Open API 는 `GET /api/v1/holdings` 로 보유 종목을 주고, 응답 필드가
포트폴리오 형식과 거의 1:1 로 맞는다(`symbol` / `name` / `quantity` / `averagePurchasePrice`).
문제는 **같은 Client ID/Secret 으로 주문도 나간다**는 점이다.

- 이 대시보드는 로그인이 없는 공개 페이지다. 서버가 잔고를 내려주면 누구나 본다.
- 그래서 키는 내 PC 의 `.env` 에만 두고, 스크립트가 만든 JSON 을 '가져오기' 로 넣는다.
  M10 에서 만든 내보내기/가져오기 포맷이 그대로 연동 지점이 됐다.
- 스크립트가 부르는 건 토큰 발급 + `/accounts` + `/holdings` 세 개뿐. 주문 엔드포인트는
  코드에 등장하지 않는다.
- 기본값은 국내(KRW) 종목만. 대시보드 합계·시세가 원화/KRX 기준이라 달러 종목을 섞으면
  매입금액 합계가 통화 뒤섞인 값이 된다. `--include-us` 로 명시적으로만 포함한다.
- 계좌번호는 로그에서 마스킹하고, 키·액세스 토큰은 출력·예외 메시지 어디에도 넣지 않는다.
- 산출물 `portfolio.json` 은 실제 보유 정보라 `.gitignore` 대상이다.

> API 스펙은 토스증권 공식 OpenAPI 1.1.1 문서 기준
> (base `https://openapi.tossinvest.com`, 계좌 API 는 `x-tossinvest-account` 헤더 필요).

### M12 — 보유 종목을 워치리스트에 넣을 때 조심한 것

포트폴리오에 담아도 워치리스트 밖이면 시세·뉴스를 안 모아서 "시세 없음"이 된다.
`seed_tickers.py` 가 `portfolio.json` 을 자동으로 찾아 시드에 합치도록 했다.

- **비활성화 함정**: 이 스크립트는 목록에 없는 종목을 `active=False` 로 내린다.
  보유 종목을 따로 넣었다면 다음 실행 때 꺼진다. 그래서 별도 스크립트를 만들지 않고
  시드 목록 자체에 합쳐서, `keep` 목록에도 같이 들어가게 했다.
- **검색어 오염**: 시드의 aliases 는 실제 검색 결과를 눈으로 확인해 넣은 값이다
  (`기아` → 야구단 기사 때문에 `기아차`). 자동 추출한 종목명은 그 검증을 못 거치므로,
  추가된 종목의 검색어를 콘솔에 찍고 확인하라고 경고한다. 필요하면
  `PORTFOLIO_ALIAS_OVERRIDES` 로 덮어쓴다. **이미 시드에 있는 종목은 시드 쪽을 유지**한다.
- **해외 티커 제외**: 워치리스트는 pykrx 기반이라 KRX 6자리 코드만 받는다. `AAPL` 을
  넣으면 파이프라인이 매일 시세 조회에 실패한다.
- 반영 직후에는 시세 이력이 없다. 다음 파이프라인 실행 후부터 쌓이고, 시그널은
  기준선(직전 5영업일)이 생긴 뒤 발화한다.

---

## 6. 하드 룰 준수 체크

- ✅ 공개 데이터만 사용 · ✅ 투자 자문 아님 라벨(UI+리포트)
- ✅ 개인 매매정보 비전송(포트폴리오는 브라우저 로컬 저장)
- ✅ 증권사 자격증명은 로컬 `.env` 에만 · 동기화 스크립트는 조회(GET) 전용
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
   자기검증 메모만 저장되는 현상. 한 번 고쳤다가 되돌아왔고(§8-A), 현재는
   리포트 호출만 `thinking_config=ThinkingConfig(thinking_budget=0)`으로 생각을 끄고,
   `finish_reason == MAX_TOKENS`(잘린 응답)과 리포트 형태가 아닌 응답은 저장 전에 막는다.
   `gemini-3.5-flash-lite`는 `thinking_budget=0`을 400으로 거부하므로, 거부되면 설정 없이
   재시도하는 폴백을 뒀다(감정분석 경로는 생각을 켠 기본값 유지).
5. **Supabase 자동 RLS** — 프로젝트 생성 시 "Enable automatic RLS"가 켜져 있으면 모든 테이블에
   RLS가 걸리고 정책이 없어 **anon 키로는 전 테이블 0건**이 된다(service_role은 우회하므로 눈치채기 어려움).
   공개 데이터만 다루므로 `alter table ... disable row level security`로 해제.
6. **Vercel Deployment Protection** — 기본 활성 시 비로그인 방문자가 SSO 로그인으로 리다이렉트된다. 공개 대시보드이므로 해제 필요.
7. **Vercel 환경변수 자동 제안** — 루트 `.env.example`을 읽어 백엔드 키까지 제안하지만,
   프론트에 필요한 건 `VITE_API_BASE` 하나뿐. 나머지는 넣지 말 것(불필요한 시크릿 확산).

---

## 8-C. 해외 종목 준실시간 (2026-09-23)

마지막 빈틈이었다. 해외 종목은 토스 동기화 시점의 `importedClose` 에 박제돼 있어서,
마지막 동기화가 일주일 전이면 일주일 전 가격을 보고 있었다.

### 왜 네이버 비공식 worldstock 을 골랐나

세 가지를 비교했다.

| | 네이버 worldstock(비공식) | 한국투자증권 KIS | Finnhub 등 |
|---|---|---|---|
| 비용·절차 | 무료, 키·신청 없음 | 계좌+앱키+신청, 해외 실시간 유무료 미확인 | 무료 한도, 키 발급 |
| 서버에 둘 수 있나 | 가능 | **불가** — 주문까지 나가는 자격증명 | 가능(읽기 전용 키) |
| 구현 비용 | 기존 국내 코드와 같은 패턴 | 새 클라이언트 | 새 클라이언트 |
| 덤 | marketStatus·프리/애프터마켓·한글 종목명 | WebSocket 푸시 | — |

KIS 는 **토스와 같은 문제가 재발**해서 탈락했다. 주문까지 나가는 자격증명이라 로그인 없는
공개 서버에 둘 수 없고, 로컬 스크립트로 빠지면 애초에 준실시간이 안 된다. Finnhub 은
네이버가 막혔을 때의 백업으로 남겨둔다.

### 구현에서 걸린 것

- **조회 키가 로이터 코드다.** 나스닥은 `AAPL.O`, 뉴욕은 접미사 없는 평문 `JPM` 이다
  (`.N`·`.K`·`.NYS` 는 모두 빈 응답이었다). 토스가 주는 건 평문 티커뿐이라 어느 거래소인지
  알 수 없어서, `X.O` 와 `X` 를 **둘 다 후보로 넣어 한 번에 묻고** 응답의 `symbolCode` 로
  되맞춘다. 없는 키는 응답에서 그냥 빠진다.
- **통화가 섞이면 안 된다.** 대시보드 금액은 전부 원화다(토스 동기화도 평단을 원화로 환산해
  넣는다). 달러 시세를 그대로 내리면 평단과 통화가 뒤섞여 평가손익이 엉터리가 된다. 그래서
  서버가 당일 USD/KRW 로 환산해서 내리고, **환율을 못 구하면 아예 내리지 않는다**(가져오기
  스냅샷으로 폴백). `toss_sync.py --include-us` 와 같은 판단이다.
  등락률은 종목 자체의 달러 기준 값이라 환율 변동은 반영되지 않는다.
- **미국 장은 한국 새벽이다.** 국내처럼 시간대로 거르면 낮에는 아무것도 못 내린다. 그래서
  해외는 시간대로 거르지 않고 늘 묻는다 — 장이 닫혀 있어도 직전 종가가 스냅샷보다 최신이다.
  다만 `live`(실시간) 로 표시하는 것은 실제로 장이 열려 있을 때뿐이다.
- **서머타임.** 한국 기준 미국 개장 시각이 겨울 22:30 / 여름 21:30 으로 계절마다 밀린다.
  서버는 네이버 응답의 `marketStatus` 를 그대로 믿어서 계산 자체를 피했고, 프론트는 폴링
  여부를 정해야 해서 `America/New_York` 표준시 이름으로 판정한다(브라우저의 표준시
  데이터가 서머타임을 처리한다). 09:30~16:00 ET 를 본다.
- **폴링은 해외 종목을 보유 중일 때만** 미국 장 시간대로 확장한다. 국내 종목만 있으면 새벽에
  깨울 이유가 없다. 둘 다 있으면 하루 15.5시간(국내 9 + 미국 6.5) → 월 약 340시간으로
  Render 무료 한도(750시간) 안에 들어간다.

### 환율 API 도메인 이동

`frankfurter.app` 이 `api.frankfurter.dev/v1` 로 301 리다이렉트한다. `requests` 는 GET
리다이렉트를 기본으로 따라가므로 `tools/toss_sync.py` 는 그대로 동작하지만, 서버 쪽은 새
주소를 직접 쓴다(왕복 한 번을 아낀다). 둘 다 `FX_API_URL` 환경변수로 덮을 수 있다.

실측(2026-09-23 14:2x KST, 한국 장중·미국 마감):
`005930` 284,250원(국내 실시간) · `035720` 33,700원(워치리스트 밖, 채움) ·
`AAPL` 460,752원(339.75 USD × 1,356.15) · `JPM` 461,091원(340.00 USD) · `NOPE` 제외.

---

## 8-B. 준실시간 빈틈 메우기 + 503 재시도 (2026-09-23)

M13(장중 준실시간, PR #3) 을 실제로 굴려 보니 세 가지가 남아 있었다.

### 1. 폴링이 장 시간과 무관하게 24시간 돌았다

프론트가 `setInterval(loadQuotes, 15000)` 로 조건 없이 폴링했다. 장 시간 밖에는 서버가 같은
DB 값을 돌려줄 뿐이라 값이 변하지도 않는데, **Render 무료 인스턴스는 요청이 계속 오면 잠들지
않는다.** 무료 티어가 월 750 인스턴스-시간이라 탭 하나를 하루 종일 열어두면 한 달치(약 744시간)를
거의 다 쓴다. 장중(9시간 × 22일 ≈ 200시간)만 돌면 여유롭다.

- `frontend/src/lib/market.ts` 의 `isMarketLiveWindow()` 로 프론트도 같은 창(평일 09:00~18:00
  KST)을 판정한다. 서버(`api/live_quotes.py`)와 판정 기준이 같아야 해서 로직이 양쪽에 있다.
- `setInterval` 대신 `setTimeout` 루프로 바꿔, 장중+탭 활성이면 15초, 아니면 60초마다 **조건만**
  다시 본다(조건 확인은 네트워크 호출이 아니라 서버로는 아무것도 가지 않는다).
- 탭으로 돌아오면(`visibilitychange`) 다음 틱을 기다리지 않고 즉시 한 번 갱신한다.
- 최초 1회는 장 시간 밖이어도 부른다 — 전일 종가는 보여줘야 하므로.
- 브라우저 표준시와 무관하게 KST 로 판정하도록 `Intl.DateTimeFormat(timeZone: 'Asia/Seoul')`
  을 쓴다. 공휴일은 모른다(서버도 마찬가지). 휴장일엔 네이버가 직전 거래일 종가를 주므로 값은
  맞고 라벨만 "실시간(장중)"으로 뜬다.

### 2. 워치리스트 밖 보유 종목은 장중에도 "시세 없음"이었다

`build_quotes()` 가 DB 시세 행에서 목록을 만들기 때문에, 시세 행이 없는 종목은 조용히 빠지고
**네이버에 물어보지도 않았다.** 네이버는 그 종목의 현재가를 알고 있는데도. M12 로 워치리스트에
넣어도 첫 파이프라인 실행 전까지는 여전히 비어 보였다.

- 라우터가 요청받은 종목 **전부**를 네이버에 묻고, `merge_live_quotes()`(순수 함수)가 DB 행이
  없는 종목을 실시간 값만으로 채운다. 종목명도 네이버 응답(`stockName`)에서 가져온다.
- 새로 만든 행의 날짜는 기준일이 아니라 **오늘**이다. 실시간 값은 오늘 것이기 때문.
- 해외 티커(`AAPL`)는 이 엔드포인트가 모르므로 호출 전에 6자리 코드만 남긴다.
- 실시간 값도 DB 행도 없는 종목은 그대로 빠진다(404 아님) — "시세 없음" 표시는 프론트 책임.
- 장 시간 밖에는 여전히 DB 가 유일한 출처라 "시세 없음"이 맞다.

실측(2026-09-23 장중): 워치리스트 밖인 카카오(035720)·LG화학(051910)이 네이버 값과 정확히
일치하는 시세로 채워졌고, 같이 요청한 `AAPL`·`999999` 는 빠졌다.

### 3. 2026-09-22 파이프라인이 Gemini 503 으로 죽어 리포트가 없었다

시세 20건·뉴스 159건·감정 159건·시그널 5건까지 다 적재한 뒤, **마지막 리포트 호출 하나가
`503 UNAVAILABLE: This model is currently experiencing high demand` 로 실패**해 잡 전체가
실패했다(§8-A 의 수정과는 무관한 별개 원인 — 검증 로직은 실행되지도 못했다).

- `_is_transient()` 로 재시도 가치가 있는 오류(429·500·503·504)를 가린다. google-genai 의
  APIError 는 HTTP 상태를 `code` 로 들고 있어서, 우리가 직접 올린 RuntimeError(잘림·빈 응답)는
  `code` 가 없어 자연히 제외된다 — 그건 다시 불러도 같은 이유로 실패할 종류다.
- 리포트 생성 루프를 총 4회로 늘리고, 일시적 오류에는 지수 백오프(10 → 20 → 40초)를 둔다.
- **감정분석 경로에는 재시도를 넣지 않았다.** 기사 수만큼(어제 159건) 호출하는 경로라 재시도를
  곱하면 실행 시간이 폭발한다. 게다가 google-genai SDK 가 내부적으로 이미 tenacity 로 재시도하고,
  감정분석은 실패해도 중립 처리로 이어지므로 잡을 죽이지 않는다.
  (2026-09-21 실행이 6시간 만에 cancel 된 적이 있는데, 이런 재시도 누적이 의심된다.)

### 로컬 검증 환경

`api/` 코드가 `list | None`(3.10+) 문법을 써서 macOS 기본 파이썬(3.9)으로는 api 테스트가
import 조차 되지 않았다. 관리자 권한 없이 `uv` 로 Python 3.12 를 깔고 `.venv` 를 만들어 해결했다
(`.venv/` 는 이미 `.gitignore` 대상). 실행 방법:

```bash
uv venv --python 3.12 .venv
uv pip install -r api/requirements-dev.txt -r pipeline/requirements-dev.txt
.venv/bin/python -m pytest api/tests tools/tests -q     # 루트에서
cd pipeline && ../.venv/bin/python -m pytest tests -q   # 파이프라인은 이 디렉터리에서
```

---

## 8-A. 리포트 오염 재발과 실제 원인 (2026-09-22 수정)

`/api/reports/latest` 가 2026-09-21 자 리포트로 **모델의 자기검증 메모 698자**를 내려주고 있었다
(`* Note about "각 언급 끝에 ..." -> ... Let's double check the rules.`). 본문은 한 줄도 없었다.

§7-B 4번에 "`thinking_budget=0`으로 해결"로 적혀 있었지만, 실제 코드는 그 설정을 쓰지 않고
"출력 한도를 넉넉히(6000) 잡는" 방식으로 되돌아와 있었다. `flash-lite`가 `budget=0`을 400으로
거부한 것이 계기였던 것으로 보이는데, 두 모델에 같은 헬퍼를 쓰다 보니 리포트 모델까지 생각이
켜진 상태로 남았다.

**왜 한도만 늘리면 안 되는가** — `google-genai`의 `resp.text`는 `thought=True` 파트를 이미
걸러낸다(SDK 1.47 `_get_text`). 그런데 생각 도중 `max_output_tokens`에 걸리면, 끊긴 생각 텍스트가
`thought` 표시 없이 **일반 본문으로** 내려온다. 저장된 본문이 `기준선은 0.0019047`에서 끊겨 있던
것이 그 증거다. 기존 헬퍼는 **빈 응답만** 예외로 올렸기 때문에, 잘린 메모는 정상 응답으로
취급돼 그대로 upsert 됐다.

**수정 (3중 방어)**
1. 리포트 호출은 `disable_thinking=True` — 생각 자체를 끈다(원인 제거). 모델이 거부하면
   설정 없이 재시도하는 폴백.
2. `finish_reason == MAX_TOKENS` 면 예외 — 잘린 응답을 호출부가 정상으로 오인하지 못하게.
   감정분석 경로에도 함께 적용된다(기존엔 잘린 JSON이 파싱 실패로 조용히 중립 처리됐다).
3. `is_valid_report()` — 마크다운 제목으로 시작하고 본문 길이가 있는지 확인. 통과하지 못하면
   한 번 재시도하고, 그래도 아니면 **저장하지 않고 예외로 중단**한다. 쓸 수 없는 본문으로
   전날 리포트를 덮어쓰는 것보다 잡이 실패해 눈에 띄는 쪽이 낫다.

프롬프트에도 "리포트 본문만 출력", "`## 오늘의 뉴스 감정 브리핑` 제목으로 시작"을 명시해
3번 검증과 짝을 맞췄다.

> 이 현상은 **확률적**이다. 같은 프롬프트로 생각을 켜고 호출해도 깨끗한 리포트가 나오는 날이
> 있다(검증 중 실제로 그랬다). 생각이 길어진 날에만 한도에 걸린다. 그래서 원인 제거(1)만으로
> 끝내지 않고 저장 직전 검증(2·3)을 함께 뒀다.

**DB에 남은 2026-09-21 리포트는 그대로 둔다.** 파이프라인은 날짜별 upsert(`date,scope`)라
과거 날짜를 다시 쓰려면 수동 개입이 필요하고, 쓰기는 파이프라인의 책임이다(하드룰 §4).
다음 실행(평일 16:00 KST)에서 2026-09-22 리포트가 생기면 `/api/reports/latest`가 그걸 내려준다.

---

## 8. 다음에 할 만한 것 / 주의사항

### 다음 후보
- **동기화 자동화**: 지금은 수동 실행 + 가져오기. 내 PC 스케줄러(cron/작업스케줄러)로
  장마감 후 `toss_sync.py` 를 돌리게 하면 파일은 갱신되지만, 브라우저 반영은 여전히 수동이다.
  완전 자동화는 로그인이 생긴 뒤에 다루는 게 맞다.
- **포트폴리오 기기 간 동기화**: 지금은 브라우저 로컬 저장. 동기화하려면 인증(Supabase Auth) +
  RLS 정책 + 쓰기 엔드포인트가 함께 필요하다. 현재 내보내기 JSON 형태가 그대로 스키마 후보.
- **keep-alive 워크플로우**: Render 무료 티어는 15분 미사용 시 슬립 → 첫 요청 30~60초 지연.
  `.github/workflows/keepalive.yml`로 주기적 핑을 넣으면 완화 가능.
- **Actions 워크플로우 액션 버전**: `actions/checkout@v4`, `setup-python@v5`가 Node 20 지원 종료 경고.
  동작에는 지장 없으나 추후 상위 버전으로 갱신 여지.

### 주의사항
- pykrx는 주말/공휴일에도 최근 영업일 데이터를 가져오지만, 네이버 뉴스는 당일 검색이라 초기 시그널 발화가 적을 수 있음.
- 프론트 번들이 recharts로 약 650KB(gzip 190KB) — 필요 시 code-splitting 여지.
- npm audit 취약점 2건(대부분 dev 의존성 추이).
- 뉴스 감정 호출이 기사 수에 비례해 느려짐(4.5초 × N). 워치리스트를 늘리면 실행 시간도 함께 증가.
