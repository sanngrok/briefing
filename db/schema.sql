-- =====================================================================
--  금융/트렌드 AI 시그널 플랫폼 — Supabase(PostgreSQL) 스키마
--  도메인: 국내 주식 + 뉴스 / 시그널 기준: 뉴스 감정 급변
--
--  설계 원칙
--   - 멱등성(idempotency): 잡이 재실행돼도 중복이 안 쌓이도록 UNIQUE + upsert
--   - 읽기/쓰기 분리: 파이프라인 잡이 write, FastAPI는 read-only
--   - 시그널은 sentiment_daily 집계 위에서 규칙으로 생성 (결정론적)
-- =====================================================================

-- 워치리스트 종목. aliases: 뉴스 검색에 쓸 회사명/약칭들
create table if not exists tickers (
    id          bigserial primary key,
    symbol      text not null unique,          -- 예: '005930'
    name        text not null,                 -- 예: '삼성전자'
    aliases     jsonb not null default '[]',   -- 예: ["삼성전자","삼성","Samsung"]
    active      boolean not null default true,
    created_at  timestamptz not null default now()
);

-- 일봉 시세 (차트용). 하루 1행.
create table if not exists prices (
    id          bigserial primary key,
    ticker_id   bigint not null references tickers(id) on delete cascade,
    date        date not null,
    close       numeric,
    change_pct  numeric,
    volume      bigint,
    unique (ticker_id, date)                    -- upsert 충돌 키
);
create index if not exists idx_prices_ticker_date on prices (ticker_id, date);

-- 개별 뉴스. url_hash 로 중복 수집 방지. 감정/태그는 LLM 가공 결과.
create table if not exists news (
    id            bigserial primary key,
    ticker_id     bigint not null references tickers(id) on delete cascade,
    url_hash      text not null unique,         -- sha256(원문 URL)
    title         text not null,
    source        text,
    url           text,
    published_at  timestamptz,
    sentiment     numeric,                      -- -1.0 ~ 1.0 (LLM)
    issue_tags    jsonb default '[]',           -- ["실적","리콜","소송"]
    summary       text,                         -- 한 줄 요약 (LLM)
    created_at    timestamptz not null default now()
);
create index if not exists idx_news_ticker_pub on news (ticker_id, published_at);

-- 종목·일자별 감정 집계. 시그널 판정의 입력.
create table if not exists sentiment_daily (
    id            bigserial primary key,
    ticker_id     bigint not null references tickers(id) on delete cascade,
    date          date not null,
    avg_sentiment numeric,                      -- 그날 뉴스 평균 감정
    news_count    int not null default 0,
    baseline      numeric,                      -- 직전 N일 평균 (판정 시점 기록)
    unique (ticker_id, date)
);
create index if not exists idx_sentiment_ticker_date on sentiment_daily (ticker_id, date);

-- 감정 급변 등 시그널. evidence 에 근거(뉴스 id, delta 등) 저장.
create table if not exists signals (
    id          bigserial primary key,
    ticker_id   bigint not null references tickers(id) on delete cascade,
    date        date not null,
    type        text not null,                  -- 'sentiment_surge_pos' | 'sentiment_surge_neg'
    severity    text not null,                  -- 'low' | 'mid' | 'high'
    evidence    jsonb not null default '{}',    -- {"delta":-0.62,"news_count":5,"news_ids":[...]}
    created_at  timestamptz not null default now(),
    unique (ticker_id, date, type)              -- 같은 날 같은 종목 같은 타입 1건
);
create index if not exists idx_signals_date on signals (date);

-- 일자별 LLM 리포트. body_md 는 그라운딩된 마크다운.
create table if not exists reports (
    id           bigserial primary key,
    date         date not null,
    scope        text not null default 'market',-- 'market' | 종목 symbol
    body_md      text not null,
    model        text,
    source_refs  jsonb default '[]',            -- 근거로 쓴 news/signal id 목록
    created_at   timestamptz not null default now(),
    unique (date, scope)
);
