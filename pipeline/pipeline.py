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
THRESHOLD     = 0.40     # |오늘 감정 - 기준선| 이 값 이상이면 급변
NEWS_PER_TICKER = 10     # 종목당 수집할 뉴스 개수
PRICE_LOOKBACK_DAYS = 10 # 주말/공휴일 대비: 최근 영업일을 찾기 위한 조회 범위
CHEAP_MODEL   = "gemini-3.5-flash-lite"   # 감정/태그용 (무료 티어)
REPORT_MODEL  = "gemini-3.5-flash"        # 리포트용 (무료 티어)
SENTIMENT_CALL_INTERVAL = 4.5  # 초. 무료 티어 분당 15회 제한 대응(호출 간 최소 간격)

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


def _generate_text(model: str, prompt: str, max_tokens: int) -> str:
    """Gemini generate_content 호출 후 텍스트만 반환. (호출부 공통 헬퍼)"""
    from google.genai import types
    resp = get_ai().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return resp.text


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
                params={"query": query, "display": NEWS_PER_TICKER, "sort": "date"},
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
        prompt = (
            "다음 뉴스의 제목과 요약을 보고 JSON 만 출력하라. 다른 말 금지.\n"
            '형식: {"sentiment": -1.0~1.0, "tags": ["..."], "summary": "한 줄 한국어 요약"}\n'
            f'제목: {it["title"]}\n요약: {it["_desc"]}'
        )
        try:
            text = _generate_text(CHEAP_MODEL, prompt, max_tokens=300)
            data = parse_sentiment(text)
        except Exception as e:
            print(f"[sentiment] 실패, 중립 처리: {e}")
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
    """|delta| → 심각도. ≥0.7 high, ≥0.5 mid, 그 외 low."""
    if abs_delta >= 0.7:
        return "high"
    if abs_delta >= 0.5:
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


def build_report_payload(signals_rows, daily_rows, name_of, report_date):
    """리포트 LLM 에 넘길 근거 payload. 조회된 실제 행만으로 구성한다(그라운딩). (순수 함수)

    - signals: evidence(jsonb) 를 펼쳐 delta/avg/baseline/news_count 등을 노출.
    - sentiment: 종목별 일집계.
    - 데이터에 없는 값은 만들지 않는다.
    """
    return {
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
    }


def build_report_prompt(payload):
    """그라운딩 프롬프트. 제공된 JSON 외의 수치·전망을 금지한다. (순수 함수)"""
    return (
        "너는 시장 뉴스 감정 브리핑을 쓰는 애널리스트다. "
        "아래 JSON 데이터만 근거로 한국어 마크다운 리포트를 작성하라.\n"
        "규칙:\n"
        "- 데이터에 없는 수치·전망·목표가·투자의견은 절대 쓰지 마라.\n"
        "- 각 언급 끝에 근거가 된 종목명을 괄호로 표기하라.\n"
        "- 발화된 시그널이 없으면 '오늘은 감정 급변 시그널이 없습니다'라고 명시하라.\n"
        "- 매수/매도 등 투자 권유 표현을 쓰지 마라.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def build_report(tickers):
    """오늘 시그널 + 종목별 감정 집계만 근거로 리포트 생성."""
    sigs = get_sb().table("signals").select("*").eq("date", TODAY.isoformat()).execute().data
    daily = get_sb().table("sentiment_daily").select("*").eq("date", TODAY.isoformat()).execute().data
    name_of = {t["id"]: t["name"] for t in tickers}

    payload = build_report_payload(sigs, daily, name_of, TODAY.isoformat())
    prompt = build_report_prompt(payload)
    text = _generate_text(REPORT_MODEL, prompt, max_tokens=1500)
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
