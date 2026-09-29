"""
pipeline.py — 일일 파이프라인 (GitHub Actions cron 에서 실행)

흐름:
  1) 시세 수집 (pykrx)            -> prices upsert
  2) 뉴스 수집 (네이버 검색 API)  -> url_hash 로 dedup, 새 기사만
  3) LLM 감정/태그 (Haiku)        -> news upsert
  4) 감정 일집계                  -> sentiment_daily upsert
  5) 감정 급변 시그널(규칙)       -> signals upsert
  6) LLM 리포트(그라운딩, Sonnet) -> reports upsert

환경변수 (GitHub repo secrets 로 주입):
  SUPABASE_URL, SUPABASE_KEY        (service_role 키)
  GEMINI_API_KEY                    (Google AI Studio, 무료 티어)
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

의존성: supabase, google-genai, pykrx, requests  (requirements.txt 참고)

주의: pykrx / 네이버 API 응답 필드는 버전·정책에 따라 바뀔 수 있으니
      처음엔 종목 1~2개로 실제 응답을 print 해서 확인 후 매핑하세요.
"""

import os
import re
import json
import html
import time
import hashlib
from datetime import date, datetime, timedelta

# third-party(requests/supabase/anthropic/pykrx) 는 각 사용처에서 지연 import 한다.
# 덕분에 시세만 검증(pykrx만 필요)하는 등 일부 단계만 독립 실행할 수 있다.

# ---- 튜닝 파라미터 -----------------------------------------------------
BASELINE_DAYS = 5        # 감정 기준선 계산에 쓸 직전 일수
MIN_NEWS      = 3        # 시그널 발화 최소 기사 수
# 감정 기준표(SENTIMENT_SCALE) 도입으로 점수 눈금이 좁아져서 함께 낮췄다.
# 같은 기사 154건을 두 프롬프트로 채점해 재 보니 표준편차가 0.459 -> 0.305,
# 압축비 0.665 였다. 옛 값(0.40/0.50/0.70)에 그 비율을 곱하면 0.27/0.33/0.47 이고,
# 재계산한 실제 |delta| 분포(0.66 0.53 0.49 0.46 0.33 0.29 ...)에 맞춰 다듬었다.
THRESHOLD     = 0.25     # |오늘 감정 - 기준선| 이 값 이상이면 급변
SEVERITY_HIGH = 0.50     # |delta| 가 이 값 이상이면 high
SEVERITY_MID  = 0.35     # 이 값 이상이면 mid
NEWS_PER_TICKER = 10     # 종목당 수집할 뉴스 개수
PRICE_LOOKBACK_DAYS = 10 # 주말/공휴일 대비: 최근 영업일을 찾기 위한 조회 범위
CHEAP_MODEL   = "gemini-3.5-flash-lite"   # 감정/태그용 (무료 티어)
REPORT_MODEL  = "gemini-3.5-flash"        # 리포트용 (무료 티어)
SENTIMENT_CALL_INTERVAL = 4.5  # 초. 무료 티어 분당 15회 제한 대응(호출 간 최소 간격)
# 최근 다섯 번 중 두 번이 리포트 단계의 503 만으로 죽었다. 4회/70초로는 무료 티어의
# 지속형 과부하를 못 넘긴다(2026-09-28 실행이 10·20·40초를 다 쓰고도 실패).
# 5회/225초로 늘렸다 — 감정분석과 달리 하루 한 번뿐이라 길게 기다려도 된다.
REPORT_ATTEMPTS = 5     # 리포트 생성 총 시도 횟수(형태 불량·일시적 오류 공통)
SENTIMENT_ATTEMPTS = 2      # 감정 분석 총 시도 횟수. 기사 수만큼 도는 경로라 짧게 잡는다
SENTIMENT_RETRY_SECONDS = 5 # 감정 분석 재시도 대기
REPORT_RETRY_SECONDS = 15   # 지수 백오프(15 -> 30 -> 60 -> 120초, 합 225초)

# Gemini 호출 타임아웃(밀리초). google-genai 2.25 의 HttpOptions.timeout 은
# 기본값이 None = 무제한이라, 응답이 오지 않으면 영원히 매달린다. 2026-09-21 과
# 09-28 실행이 각각 러너 한도 6시간을 다 태우고 cancelled 로 끝난 원인이다.
#
# 매달림은 예외를 올리지 않기 때문에 아래 재시도 경로에도 걸리지 않는다 —
# 재시도를 아무리 늘려도 손이 닿지 않는다. 시간을 잘라 예외로 바꿔야 비로소
# 재시도가 시작된다.
#
# 값은 단계별로 다르게 잡는다. 감정분석은 기사 수만큼 도는 경로라(45건 × 2회)
# 길게 잡으면 최악의 경우 워크플로 한도(timeout-minutes: 45)를 넘겨 버린다.
# 감정분석은 짧은 JSON 이라 정상이면 수 초다. 20초면 넉넉하고, 전부 매달리는
# 최악의 경우에도 45건 × 2회 × 20초 = 30분으로 워크플로 한도 안에 남는다.
SENTIMENT_TIMEOUT_MS = 20_000
# 리포트는 본문이 길어 느리고, 하루 한 번뿐이라 넉넉히 준다.
REPORT_TIMEOUT_MS = 120_000

TODAY = date.today()

# 외부 클라이언트는 지연(lazy) 생성한다.
# 이렇게 하면 시세만 검증할 때(키 불필요)처럼 일부 단계만 import/실행할 수 있다.
_sb = None
_ai = None

def get_sb():
    """Supabase 클라이언트(쓰기: service_role). 최초 호출 시 생성."""
    global _sb
    if _sb is None:
        from supabase import create_client
        _sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _sb

def get_ai():
    """Gemini 클라이언트. 최초 호출 시 생성."""
    global _ai
    if _ai is None:
        from google import genai
        _ai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _ai


def _finish_reason(resp):
    """응답의 finish_reason 이름. 없으면 None. (잘림 판정·진단용)"""
    if not resp.candidates:
        return None
    fr = getattr(resp.candidates[0], "finish_reason", None)
    if fr is None:
        return None
    return getattr(fr, "name", None) or str(fr)


# 잠시 뒤 다시 하면 될 법한 HTTP 상태. 429=레이트리밋, 503=모델 과부하.
TRANSIENT_STATUS = {429, 500, 503, 504}


def _is_timeout(err) -> bool:
    """호출이 시간 안에 안 끝나서 잘린 것인지.

    google-genai 는 내부적으로 httpx 를 쓰고, 타임아웃이면 httpx 예외가 그대로
    올라온다(응답 자체가 없어 APIError 로 감싸이지 않는다). httpx 를 직접
    의존성으로 선언하지 않았으므로 import 대신 예외 사슬의 타입 이름으로 본다.
    """
    seen = set()
    e = err
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if "Timeout" in type(e).__name__:
            return True
        e = e.__cause__ or e.__context__
    return False


def _is_transient(err) -> bool:
    """재시도할 가치가 있는 일시적 오류인지.

    2026-09-22 실행이 `503 UNAVAILABLE: This model is currently experiencing high
    demand` 로 죽어 그날 리포트가 통째로 없었다. 시세·뉴스·감정·시그널은 이미
    적재된 뒤였는데 마지막 한 번의 호출 때문에 잡이 실패했다.

    google-genai 의 APIError 는 HTTP 상태를 `code` 로 들고 있다. 우리가 직접 올린
    RuntimeError(잘림·빈 응답)에는 code 가 없으므로 자연히 제외된다 — 그건 다시
    불러도 같은 이유로 실패할 종류의 오류가 아니라, 응답 내용의 문제다.

    타임아웃도 여기 포함한다. 타임아웃 예외에는 code 가 없어서 넣어 주지 않으면
    "잘라 놓고 재시도는 안 하는" 상태가 된다 — 매달림이 즉시 실패로 바뀔 뿐이다.
    """
    return getattr(err, "code", None) in TRANSIENT_STATUS or _is_timeout(err)


def _thinking_rejected(err) -> bool:
    """모델이 thinking_config 자체를 거부했는지(flash-lite 는 budget=0 을 400 으로 거부)."""
    msg = str(err).lower()
    return "thinking" in msg or "budget" in msg


def _generate_text(model: str, prompt: str, max_tokens: int,
                   disable_thinking: bool = False,
                   timeout_ms: int = REPORT_TIMEOUT_MS) -> str:
    """Gemini generate_content 호출 후 텍스트만 반환. (호출부 공통 헬퍼)

    Gemini 3.x 는 내부 '생각(thinking)' 토큰도 max_output_tokens 를 함께 소진한다.
    한도에 걸리면 생각 도중 끊긴 텍스트가 `thought` 표시도 없이 본문으로 내려오기
    때문에(실제로 2026-09-21 리포트가 모델의 자기검증 메모로 저장됐다) 출력 한도를
    넉넉히 잡는 것만으로는 막히지 않는다. 그래서 두 가지를 둔다.

    - 본문 품질이 중요한 호출은 `disable_thinking=True` 로 생각 자체를 끈다.
      thinking_config 지원은 모델마다 갈리므로(flash-lite 는 budget=0 을 400 으로
      거부) 거부되면 설정 없이 한 번 더 시도한다.
    - finish_reason 이 MAX_TOKENS 면 잘린 응답이므로 예외로 올린다. 잘린 텍스트를
      호출부가 정상 응답으로 오인해 저장하는 일을 막는다.

    `timeout_ms` 는 호출마다 건다(클라이언트 전역이 아니라). 감정분석은 기사 수만큼
    도는 경로라 리포트보다 짧게 잡아야 하기 때문이다.
    """
    from google.genai import types

    def _call(thinking_off: bool):
        return get_ai().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                thinking_config=(types.ThinkingConfig(thinking_budget=0)
                                 if thinking_off else None),
                http_options=types.HttpOptions(timeout=timeout_ms),
            ),
        )

    try:
        resp = _call(disable_thinking)
    except Exception as e:
        if not disable_thinking or not _thinking_rejected(e):
            raise
        print(f"[llm] {model} 이 thinking_config 를 거부함, 설정 없이 재시도: {e}")
        resp = _call(False)

    reason = _finish_reason(resp)
    text = resp.text
    if not text or not text.strip():
        raise RuntimeError(f"빈 응답 (finish_reason={reason}, model={model})")
    if reason == "MAX_TOKENS":
        raise RuntimeError(
            f"출력이 max_output_tokens={max_tokens} 에서 잘림 (model={model})")
    return text


# ======================================================================
# 1) 시세 수집
# ======================================================================
def fetch_latest_price(symbol: str):
    """pykrx 로 최근 영업일 일봉 1건을 반환. (DB 접근 없음 — 단독 검증 가능)

    주말·공휴일에는 당일 데이터가 없으므로 최근 PRICE_LOOKBACK_DAYS 일을
    조회해 마지막(가장 최근) 영업일 행을 사용한다. 날짜는 TODAY 가 아니라
    실제 체결일(DataFrame 인덱스)을 쓴다.
    반환: {"date","close","change_pct","volume"} 또는 None(데이터 없음).
    """
    from pykrx import stock
    frm = (TODAY - timedelta(days=PRICE_LOOKBACK_DAYS)).strftime("%Y%m%d")
    to  = TODAY.strftime("%Y%m%d")
    df = stock.get_market_ohlcv(frm, to, symbol)
    if df is None or df.empty:
        return None
    r = df.iloc[-1]
    trade_date = df.index[-1].date()   # 실제 체결일 (당일이 아닐 수 있음)
    return {
        "date":       trade_date.isoformat(),
        "close":      float(r["종가"]),
        "change_pct": float(r.get("등락률", 0.0)),
        "volume":     int(r["거래량"]),
    }


def collect_prices(tickers):
    """각 종목의 최근 영업일 일봉을 prices 에 upsert."""
    rows = []
    for t in tickers:
        try:
            price = fetch_latest_price(t["symbol"])
            if price is None:
                print(f"[price] {t['symbol']} 데이터 없음(휴장/미상장) 스킵")
                continue
            rows.append({"ticker_id": t["id"], **price})
        except Exception as e:
            print(f"[price] {t['symbol']} 실패: {e}")
    if rows:
        get_sb().table("prices").upsert(rows, on_conflict="ticker_id,date").execute()
    print(f"[price] {len(rows)}건 upsert")


# ======================================================================
# 2) 뉴스 수집 (네이버 검색 API)
# ======================================================================
def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()

def _strip_tags(s: str) -> str:
    """HTML 태그 제거 + 엔티티 복원 (&amp; &quot; &#39; 등). 네이버 응답 정규화."""
    s = re.sub(r"<[^>]+>", "", s or "")
    return html.unescape(s).strip()

def _parse_pubdate(s):
    try:
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z").isoformat()
    except Exception:
        return None

def parse_news_item(ticker_id, item: dict):
    """네이버 뉴스 API item 1건을 news 행 형태로 변환. (순수 함수 — 네트워크/DB 없음)

    - url 은 originallink(원문) 우선, 없으면 link.
    - url 이 없으면 None 반환(스킵).
    - _desc 는 감정분석 입력용 임시 필드로, DB 저장 전 제거된다.
    """
    url = item.get("originallink") or item.get("link")
    if not url:
        return None
    return {
        "ticker_id":    ticker_id,
        "url_hash":     _hash(url),
        "title":        _strip_tags(item.get("title", "")),
        "url":          url,
        "source":       "naver",
        "published_at": _parse_pubdate(item.get("pubDate")),
        "_desc":        _strip_tags(item.get("description", "")),
    }

def collect_news(tickers):
    """종목 aliases 로 뉴스 검색, url_hash 로 dedup 후 새 기사만 반환."""
    import requests
    headers = {
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY":    os.environ["NAVER_CLIENT_SECRET"],
    }
    new_items = []
    seen = set()   # 이번 실행 안에서의 중복(같은 기사 다중 매칭) 방지
    for t in tickers:
        query = (t["aliases"] or [t["name"]])[0]
        try:
            resp = requests.get(
                "https://naverapihub.apigw.ntruss.com/search/v1/news",
                headers=headers,
                # sort=date(최신순)는 검색어가 스치듯 언급된 무관한 기사까지 끌어온다
                # (예: "삼성생명" → 후원 배드민턴 기사). 종목 감정 분석에는
                # 관련도순(sim)이 훨씬 정확해서 sim 을 쓴다.
                params={"query": query, "display": NEWS_PER_TICKER, "sort": "sim"},
                timeout=10,
            )
            items = resp.json().get("items", [])
        except Exception as e:
            print(f"[news] {query} 실패: {e}")
            continue

        for it in items:
            row = parse_news_item(t["id"], it)
            if row is None:
                continue
            h = row["url_hash"]
            if h in seen:
                continue
            # DB 에 이미 있으면 skip (비용 방어: LLM 재호출 금지)
            exists = get_sb().table("news").select("id").eq("url_hash", h).execute()
            if exists.data:
                continue
            seen.add(h)
            new_items.append(row)
    print(f"[news] 신규 {len(new_items)}건")
    return new_items


# ======================================================================
# 3) LLM 감정/태그 (구조화 JSON)
# ======================================================================
# 감정 점수 기준표. 모델이 0.8/0.5 몇 개 값에만 몰리던 문제 때문에 넣었다.
# 실측(1000건)에서 0.8 이 23.3%, 0.5 가 23.2% 를 차지했고, 대시보드는 |점수| 상위
# 기사만 보여주기 때문에 "호재는 늘 +0.8, 악재는 늘 -0.8" 로 보였다.
# 사건 유형을 눈금에 묶어 주면 모델이 중간값을 쓸 근거가 생긴다.
SENTIMENT_SCALE = """\
점수 기준 — 그 회사 주가에 미칠 영향의 크기로 매긴다. 0.05 단위까지 쓸 수 있다.
 +0.9~1.0   피인수·경영권 매각, 대규모 수주, 신약 승인, 실적 서프라이즈 등 회사 가치를 크게 바꾸는 사건
 +0.6~0.8   호실적 발표, 목표주가 상향, 대형 계약 체결, 신제품 흥행
 +0.3~0.5   업황 개선 전망, 중소 규모 계약, 긍정적 애널리스트 언급
 +0.05~0.25 가벼운 긍정 언급, 부수적 호재, 업계 동향 속 긍정적 거론
  0.0       중립. 단순 사실 전달, 회사와 직접 관련 없는 기사, 판단 근거 부족
 -0.05~-0.25 가벼운 부정 언급, 부수적 악재
 -0.3~-0.5   업황 둔화 전망, 소송 제기, 경쟁 심화, 점유율 하락
 -0.6~-0.8   실적 부진, 목표주가 하향, 리콜, 대규모 인력 감축, 주요 계약 해지
 -0.9~-1.0   회계 부정, 상장폐지 위험, 거래정지, 핵심 경영진 구속, 대규모 손실 확정"""


def build_sentiment_prompt(title: str, desc: str) -> str:
    """기사 한 건의 감정 분석 프롬프트. (순수 함수)

    기준표를 함께 주는 이유는 §8-D 참고 — 기준 없이 물으면 모델이 몇 개 값으로
    몰려서, 점수가 사실상 '긍정/부정' 이진값이 된다.
    """
    return (
        "다음 뉴스의 제목과 요약을 보고 JSON 만 출력하라. 다른 말 금지.\n"
        '형식: {"sentiment": -1.0~1.0, "tags": ["..."], "summary": "한 줄 한국어 요약"}\n'
        f"{SENTIMENT_SCALE}\n"
        "사안의 크기에 맞춰 눈금을 세분화하라. 몇 개 값으로 몰지 마라.\n"
        f"제목: {title}\n요약: {desc}"
    )


def parse_sentiment(text: str) -> dict:
    """LLM 응답 텍스트에서 감정 JSON을 파싱·정규화. (순수 함수)

    - ```json 코드펜스/여백을 벗겨 JSON 만 추출.
    - sentiment 는 float 로 강제 후 [-1.0, 1.0] 클램프.
    - tags 는 list[str], summary 는 str 로 정규화.
    - 파싱 불가 시 예외를 던진다(호출부에서 중립 처리).
    """
    data = json.loads(_only_json(text))
    sentiment = max(-1.0, min(1.0, float(data.get("sentiment", 0.0))))
    tags = data.get("tags", [])
    tags = [str(x) for x in tags] if isinstance(tags, list) else []
    summary = str(data.get("summary", "") or "")
    return {"sentiment": sentiment, "tags": tags, "summary": summary}

def enrich_news(items):
    """각 기사에 sentiment(-1~1), tags, 요약을 붙여 news upsert."""
    enriched = []
    for idx, it in enumerate(items):
        if idx > 0:
            time.sleep(SENTIMENT_CALL_INTERVAL)
        prompt = build_sentiment_prompt(it["title"], it["_desc"])
        # 503(모델 과부하)은 이 경로에도 실제로 들어온다. 실패를 중립 0.0 으로
        # 떨어뜨리면 그날 평균이 0 쪽으로 끌려가고, 그게 기준선과 시그널까지
        # 오염시킨다. 그래서 일시적 오류만 한 번 더 시도한다 — 기사 수만큼 도는
        # 경로라 횟수는 짧게 잡았다(SDK 자체 재시도도 이미 있다).
        data = None
        for attempt in range(1, SENTIMENT_ATTEMPTS + 1):
            try:
                # thinking 토큰이 한도를 나눠 쓰므로 짧은 JSON 이어도 여유를 둔다
                text = _generate_text(CHEAP_MODEL, prompt, max_tokens=1000,
                                      timeout_ms=SENTIMENT_TIMEOUT_MS)
                data = parse_sentiment(text)
                break
            except Exception as e:
                if _is_transient(e) and attempt < SENTIMENT_ATTEMPTS:
                    print(f"[sentiment] 일시적 오류({getattr(e, 'code', '?')}), "
                          f"{SENTIMENT_RETRY_SECONDS}초 뒤 재시도")
                    time.sleep(SENTIMENT_RETRY_SECONDS)
                    continue
                print(f"[sentiment] 실패, 중립 처리: {e}")
                break
        if data is None:
            data = {"sentiment": 0.0, "tags": [], "summary": it["title"]}

        enriched.append({
            "ticker_id":    it["ticker_id"],
            "url_hash":     it["url_hash"],
            "title":        it["title"],
            "url":          it["url"],
            "source":       it["source"],
            "published_at": it["published_at"],
            "sentiment":    float(data.get("sentiment", 0.0)),
            "issue_tags":   data.get("tags", []),
            "summary":      data.get("summary", ""),
        })
    if enriched:
        get_sb().table("news").upsert(enriched, on_conflict="url_hash").execute()
    print(f"[sentiment] {len(enriched)}건 처리")

def _only_json(text: str) -> str:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return text.strip()


# ======================================================================
# 4) 감정 일집계 + 5) 감정 급변 시그널
#    판정 규칙(§7)은 아래 순수 함수로 분리해 단위 테스트로 고정한다.
# ======================================================================
def compute_baseline(history_avgs, today_avg):
    """기준선 = 직전 N일 평균 감정. 히스토리가 없으면 today_avg 로 둔다.

    초기 며칠은 히스토리가 없어 baseline==today_avg → delta 0 → 미발화(정상, §7).
    """
    return sum(history_avgs) / len(history_avgs) if history_avgs else today_avg


def classify_severity(abs_delta):
    """|delta| → 심각도. 경계는 SEVERITY_HIGH / SEVERITY_MID."""
    if abs_delta >= SEVERITY_HIGH:
        return "high"
    if abs_delta >= SEVERITY_MID:
        return "mid"
    return "low"


def decide_signal(avg, baseline, news_count, *, min_news=MIN_NEWS, threshold=THRESHOLD):
    """§7 규칙으로 감정 급변 시그널을 판정. (순수 함수)

    발화 조건: news_count ≥ min_news  AND  |avg - baseline| ≥ threshold.
    반환: 발화 시 {"type","severity","delta"}, 아니면 None.
    """
    delta = avg - baseline
    if news_count < min_news or abs(delta) < threshold:
        return None
    stype = "sentiment_surge_pos" if delta > 0 else "sentiment_surge_neg"
    return {"type": stype, "severity": classify_severity(abs(delta)), "delta": delta}


def aggregate_and_signal(tickers):
    for t in tickers:
        # 오늘 뉴스 감정 모으기
        today_news = get_sb().table("news").select("id,sentiment") \
            .eq("ticker_id", t["id"]) \
            .gte("published_at", TODAY.isoformat()) \
            .execute().data
        sents = [n["sentiment"] for n in (today_news or []) if n["sentiment"] is not None]
        if not sents:
            continue
        avg = sum(sents) / len(sents)

        # 기준선 = 직전 BASELINE_DAYS 일 평균 (오늘 제외)
        since = (TODAY - timedelta(days=BASELINE_DAYS)).isoformat()
        hist = get_sb().table("sentiment_daily").select("avg_sentiment") \
            .eq("ticker_id", t["id"]) \
            .gte("date", since).lt("date", TODAY.isoformat()) \
            .execute().data
        baseline = compute_baseline([h["avg_sentiment"] for h in (hist or [])], avg)

        get_sb().table("sentiment_daily").upsert({
            "ticker_id": t["id"], "date": TODAY.isoformat(),
            "avg_sentiment": avg, "news_count": len(sents), "baseline": baseline,
        }, on_conflict="ticker_id,date").execute()

        # 시그널 판정 (순수 함수)
        decision = decide_signal(avg, baseline, len(sents))
        if decision:
            get_sb().table("signals").upsert({
                "ticker_id": t["id"], "date": TODAY.isoformat(),
                "type": decision["type"], "severity": decision["severity"],
                "evidence": {"delta": round(decision["delta"], 3), "avg": round(avg, 3),
                             "baseline": round(baseline, 3), "news_count": len(sents),
                             "news_ids": [n["id"] for n in today_news]},
            }, on_conflict="ticker_id,date,type").execute()
            print(f"[signal] {t['symbol']} {decision['type']} delta={decision['delta']:.2f}")


# ======================================================================
# 6) LLM 리포트 (그라운딩)
# ======================================================================
# 하드룰 §2: 리포트에 투자 자문이 아님을 명시. LLM 출력에 의존하지 않고
# 결정론적으로 부착한다.
REPORT_DISCLAIMER = (
    "> ⚠️ 본 리포트는 공개 데이터 기반의 정보 제공 목적이며, 투자 판단의 근거가 아닙니다."
)

# 프롬프트가 요구하는 리포트 제목. is_valid_report 가 이 형태를 확인한다.
REPORT_HEADING = "## 오늘의 뉴스 감정 브리핑"
MIN_REPORT_CHARS = 80   # 이보다 짧으면 본문이라 볼 수 없다


def strip_markdown_fence(text: str) -> str:
    """본문 전체를 ``` 코드펜스로 감싼 응답이면 펜스를 벗긴다. (순수 함수)

    리포트는 마크다운 자체가 본문이다. 펜스가 남으면 대시보드에서 코드블록으로
    렌더링되고, 제목으로 시작하지도 않아 is_valid_report 에서 헛되게 걸린다.
    """
    body = (text or "").strip()
    if not body.startswith("```"):
        return body
    lines = body.splitlines()[1:]              # ```markdown 등 여는 줄 제거
    if lines and lines[-1].strip() == "```":   # 닫는 줄 제거
        lines = lines[:-1]
    return "\n".join(lines).strip()


def is_valid_report(text) -> bool:
    """리포트로 저장해도 되는 출력인지. (순수 함수)

    모델이 리포트 대신 자기검증 메모를 내려보낸 적이 있어서, 저장 전에 '리포트의
    형태인지'를 결정론적으로 확인한다. 프롬프트가 지시한 대로 마크다운 제목으로
    시작하고 본문이라 할 만한 길이가 있어야 통과다. 메모나 생각 과정은 제목 없이
    시작하므로 여기서 걸러진다.
    """
    if not text:
        return False
    body = text.strip()
    return body.startswith("#") and len(body) >= MIN_REPORT_CHARS


def round_numbers(value, ndigits: int = 3):
    """payload 안의 실수를 반올림. (순수 함수)

    집계값이 0.5750000000000001 이나 -2.7755575615628914e-17 같은 부동소수 꼬리를
    달고 있어서, 모델이 그걸 그대로 리포트 본문에 옮겨 적었다. 근거로 쓰는 숫자라
    정밀도를 크게 줄이지는 않고(시그널 임계치가 소수 둘째 자리), 읽는 데 방해가
    되는 꼬리만 자른다. -0.0 은 0.0 으로 눕힌다.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        rounded = round(value, ndigits)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        return {k: round_numbers(v, ndigits) for k, v in value.items()}
    if isinstance(value, list):
        return [round_numbers(v, ndigits) for v in value]
    return value


def build_report_payload(signals_rows, daily_rows, name_of, report_date):
    """리포트 LLM 에 넘길 근거 payload. 조회된 실제 행만으로 구성한다(그라운딩). (순수 함수)

    - signals: evidence(jsonb) 를 펼쳐 delta/avg/baseline/news_count 등을 노출.
    - sentiment: 종목별 일집계.
    - 데이터에 없는 값은 만들지 않는다.
    """
    return round_numbers({
        "date": report_date,
        "signals": [
            {"name": name_of.get(s["ticker_id"]), "type": s["type"],
             "severity": s["severity"], **(s.get("evidence") or {})}
            for s in (signals_rows or [])
        ],
        "sentiment": [
            {"name": name_of.get(d["ticker_id"]), "avg": d["avg_sentiment"],
             "baseline": d["baseline"], "news_count": d["news_count"]}
            for d in (daily_rows or [])
        ],
    })


def build_report_prompt(payload):
    """그라운딩 프롬프트. 제공된 JSON 외의 수치·전망을 금지한다. (순수 함수)"""
    return (
        "너는 시장 뉴스 감정 브리핑을 쓰는 애널리스트다. "
        "아래 JSON 데이터만 근거로 한국어 마크다운 리포트를 작성하라.\n"
        "규칙:\n"
        "- 데이터에 없는 수치·전망·목표가·투자의견은 절대 쓰지 마라.\n"
        "- 각 언급 끝에 근거가 된 종목명을 괄호로 표기하라.\n"
        "- 발화된 시그널이 없으면 '오늘은 감정 급변 시그널이 없습니다'라고 명시하라.\n"
        "- 매수/매도 등 투자 권유 표현을 쓰지 마라.\n"
        "- 검토 과정·자기점검 메모를 쓰지 말고 리포트 본문만 출력하라.\n"
        f"- 리포트는 `{REPORT_HEADING}` 제목으로 시작하라.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def build_report(tickers):
    """오늘 시그널 + 종목별 감정 집계만 근거로 리포트 생성."""
    sigs = get_sb().table("signals").select("*").eq("date", TODAY.isoformat()).execute().data
    daily = get_sb().table("sentiment_daily").select("*").eq("date", TODAY.isoformat()).execute().data
    name_of = {t["id"]: t["name"] for t in tickers}

    payload = build_report_payload(sigs, daily, name_of, TODAY.isoformat())
    prompt = build_report_prompt(payload)

    # 생각을 끈 상태로 뽑는다. 두 가지 이유로 다시 시도할 수 있다.
    #  - 일시적 오류(503 과부하·429 레이트리밋): 지수 백오프 후 재시도.
    #  - 리포트 형태가 아닌 응답: 바로 재시도(같은 프롬프트, 확률적 현상이므로).
    # 모두 소진하면 저장하지 않고 예외로 올린다 — 쓸 수 없는 본문으로 전날 리포트를
    # 덮어쓰는 것보다, 잡이 실패해서 눈에 띄는 쪽이 낫다.
    text = None
    for attempt in range(1, REPORT_ATTEMPTS + 1):
        try:
            candidate = strip_markdown_fence(
                _generate_text(REPORT_MODEL, prompt, max_tokens=6000,
                               disable_thinking=True,
                               timeout_ms=REPORT_TIMEOUT_MS))
        except Exception as e:
            if not _is_transient(e) or attempt == REPORT_ATTEMPTS:
                raise
            wait = REPORT_RETRY_SECONDS * (2 ** (attempt - 1))
            print(f"[report] 일시적 오류({getattr(e, 'code', '?')}), {wait}초 뒤 "
                  f"재시도 ({attempt}/{REPORT_ATTEMPTS}): {e}")
            time.sleep(wait)
            continue
        if is_valid_report(candidate):
            text = candidate
            break
        print(f"[report] 리포트 형태가 아닌 응답(시도 {attempt}): "
              f"{candidate.strip()[:120]!r}")
    if text is None:
        raise RuntimeError("리포트 형태의 응답을 받지 못했다 — 저장하지 않고 중단한다")

    # §2 면책 라벨을 결정론적으로 부착
    body = text.rstrip() + "\n\n" + REPORT_DISCLAIMER
    get_sb().table("reports").upsert({
        "date": TODAY.isoformat(), "scope": "market", "body_md": body,
        "model": REPORT_MODEL,
        "source_refs": [s["id"] for s in (sigs or [])],
    }, on_conflict="date,scope").execute()
    print("[report] 생성 완료")


# ======================================================================
def main():
    tickers = get_sb().table("tickers").select("*").eq("active", True).execute().data
    if not tickers:
        print("워치리스트가 비어있음. tickers 테이블에 종목을 먼저 넣으세요.")
        return
    collect_prices(tickers)
    new_items = collect_news(tickers)
    enrich_news(new_items)
    aggregate_and_signal(tickers)
    build_report(tickers)
    print("파이프라인 완료.")


if __name__ == "__main__":
    main()
