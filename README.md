# 금융/트렌드 AI 시그널 리포트 플랫폼

국내 주식 시세와 뉴스를 평일 장마감 후 자동 수집하고, LLM으로 뉴스 감정을 분석해
**감정 급변 시그널**을 탐지한 뒤, 일일 리포트를 생성해 대시보드로 보여주는
백그라운드 데이터 파이프라인 플랫폼입니다.

> ⚠️ **정보 제공 목적이며 투자 판단의 근거가 아닙니다.** 공개 데이터만 사용합니다.

---

## 아키텍처 (읽기/쓰기 2-레이어 분리)

```
[레이어 A] GitHub Actions cron (평일 장마감 후)
   fetch(시세·뉴스) → LLM 감정/태그 → 감정 집계 → 급변 시그널 → LLM 리포트
        │ write
        ▼
   Supabase (Postgres)
        ▲ read only
        │
[레이어 B] FastAPI (Fly/Render) ── 읽기 전용
        │ JSON
        ▼
[레이어 C] Vercel 프론트 (차트·시그널 카드·리포트)
```

- **파이프라인(쓰기)** 과 **서빙 API(읽기)** 는 분리된 서비스로 배포합니다.
- 무료 인스턴스가 슬립해도 스케줄 잡은 독립적으로 실행됩니다.

---

## 저장소 구조

```
briefing/
├── db/
│   └── schema.sql          # Supabase DDL (tickers/prices/news/sentiment_daily/signals/reports)
├── pipeline/               # 레이어 A — 쓰기 전용 파이프라인 잡
│   ├── pipeline.py         # 수집 → 감정 → 집계 → 시그널 → 리포트 오케스트레이터
│   └── requirements.txt
├── api/                    # 레이어 B — 읽기 전용 FastAPI (M6)
├── frontend/               # 레이어 C — Vercel React(TS) 대시보드 (M7)
├── .github/workflows/      # cron 파이프라인 워크플로우 (M8)
├── .env.example            # 환경변수 문서 (실제 값 없음)
└── README.md
```

---

## 환경변수

| 이름 | 용도 | 발급처 |
|---|---|---|
| `SUPABASE_URL` / `SUPABASE_KEY` | DB 저장/조회 | Supabase (파이프라인=service_role) |
| `ANTHROPIC_API_KEY` | 감정분석/리포트 | Anthropic |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 뉴스 검색 | 네이버 개발자센터 |

- 로컬: `.env.example` → `.env` 복사 후 값 입력 (`.env` 는 커밋 금지).
- 잡: GitHub repo Secrets. 서빙: Fly/Render 환경변수. 프론트: Vercel 환경변수.

---

## DB 준비 (M1)

1. **스키마 적용** — Supabase 프로젝트에서 아래 중 한 방법으로 [db/schema.sql](db/schema.sql) 실행:
   - Supabase 대시보드 → **SQL Editor** → `schema.sql` 내용 붙여넣기 → Run
   - 또는 psql: `psql "<connection-string>" -f db/schema.sql`
   - `create table if not exists` 라서 여러 번 실행해도 안전합니다.
2. **워치리스트 시드** — 환경변수(`SUPABASE_URL`, `SUPABASE_KEY`) 설정 후:
   ```bash
   cd pipeline
   python seed_tickers.py
   ```
   - `symbol` UNIQUE 기준 upsert → **재실행해도 중복이 쌓이지 않습니다**(멱등).
   - 기본 시드: 삼성전자(005930) · SK하이닉스(000660) · NAVER(035420) · 카카오(035720).
   - 종목을 바꾸려면 `seed_tickers.py` 의 `SEED_TICKERS` 를 수정하세요.

---

## 로컬 실행 (파이프라인)

```bash
cd pipeline
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS/Linux:         source .venv/bin/activate
pip install -r requirements.txt

# 환경변수 로드 후 실행
python pipeline.py
```

> 외부 클라이언트(Supabase/Anthropic)는 **지연 생성**되므로, 키가 없어도 개별 단계를
> 검증할 수 있습니다. 예: 시세 수집은 키 없이 아래로 확인 가능합니다.

**시세 수집 검증 (키 불필요, M2)**
```bash
cd pipeline
pip install pykrx
python check_prices.py              # 시드 종목 전체의 최근 영업일 시세 출력
python check_prices.py 005930       # 특정 종목만
```
주말·공휴일에도 최근 영업일 데이터를 실제 체결일 기준으로 가져옵니다.

**단위 테스트 (키 불필요, M3~)**
```bash
cd pipeline
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
뉴스 파싱(`parse_news_item`)·감정 JSON 파싱(`parse_sentiment`)과
시그널 판정(`decide_signal`/`classify_severity`/`compute_baseline`, §7 규칙)을
순수 함수로 검증합니다. 경계값(임계치·최소 기사 수·심각도 구간)을 포함합니다.
(네이버/Anthropic 실제 호출은 키 연동 후 파이프라인 전체 실행으로 확인)

---

## 서빙 API (레이어 B, 읽기 전용)

FastAPI. Supabase 를 **읽기만** 하며 CORS 는 프론트 도메인만, GET 만 노출합니다.

**엔드포인트**
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 헬스체크 |
| GET | `/api/reports/latest` | 최신 리포트 |
| GET | `/api/reports/{date}` | 특정일 리포트 |
| GET | `/api/tickers/{symbol}/metrics?from=&to=` | 종목 시세·감정 시계열 |
| GET | `/api/signals?date=&severity=` | 시그널 목록(필터) |

**로컬 실행 / 테스트**
```bash
pip install -r api/requirements-dev.txt
uvicorn api.main:app --reload      # http://127.0.0.1:8000/docs (Swagger)
python -m pytest api/tests -v      # Supabase 없이 라우팅·검증·404/422 검증
```
> 환경변수: `SUPABASE_URL`, `SUPABASE_KEY`(읽기=anon 권장), `CORS_ORIGINS`(콤마 구분).
> 테스트는 `dependency_overrides` 로 가짜 repo 를 주입해 실제 DB 없이 돌아갑니다.

---

## 개발 로드맵 (마일스톤)

| # | 내용 | 상태 |
|---|---|---|
| M0 | 프로젝트 스캐폴딩 & 시크릿 골격 | ✅ |
| M1 | 스키마 적용 & 워치리스트 시드 | ✅ |
| M2 | 시세 슬라이스 (pykrx 검증) | ✅ |
| M3 | 뉴스 + 감정 슬라이스 | ✅ |
| M4 | 집계 & 시그널 + 단위테스트 | ✅ |
| M5 | 리포트 (그라운딩) | ✅ |
| M6 | FastAPI 서빙 레이어 | ✅ |
| M7 | 프론트엔드 (Recharts) | ⬜ |
| M8 | GitHub Actions 워크플로우 | ⬜ |
| M9 | 배포 (Fly/Render + Vercel) | ⬜ |

---

## 시그널 정의 (뉴스 감정 급변)

- 종목별 그날 뉴스 **평균 감정(-1~1)** 계산.
- **기준선** = 직전 `BASELINE_DAYS`(기본 5)일 평균 감정.
- 그날 기사 수 ≥ `MIN_NEWS`(기본 3) **AND** |오늘 - 기준선| ≥ `THRESHOLD`(기본 0.40) → 시그널 발화.
- 방향: delta>0 → `sentiment_surge_pos`, delta<0 → `sentiment_surge_neg`.
- 심각도: |delta| ≥0.7 `high`, ≥0.5 `mid`, 그 외 `low`.
