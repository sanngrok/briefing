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
  ANTHROPIC_API_KEY
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

의존성: supabase, anthropic, pykrx, requests  (requirements.txt 참고)

주의: pykrx / 네이버 API 응답 필드는 버전·정책에 따라 바뀔 수 있으니
      처음엔 종목 1~2개로 실제 응답을 print 해서 확인 후 매핑하세요.
"""

import os
import json
import hashlib
from datetime import date, datetime, timedelta

import requests
from supabase import create_client
import anthropic

# ---- 튜닝 파라미터 -----------------------------------------------------
BASELINE_DAYS = 5        # 감정 기준선 계산에 쓸 직전 일수
MIN_NEWS      = 3        # 시그널 발화 최소 기사 수
THRESHOLD     = 0.40     # |오늘 감정 - 기준선| 이 값 이상이면 급변
NEWS_PER_TICKER = 10     # 종목당 수집할 뉴스 개수
CHEAP_MODEL   = "claude-haiku-4-5-20251001"   # 감정/태그용
REPORT_MODEL  = "claude-sonnet-5"             # 리포트용 (모델명은 현재 사용 가능 값으로)

sb  = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
ai  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
TODAY = date.today()


# ======================================================================
# 1) 시세 수집
# ======================================================================
def collect_prices(tickers):
    """pykrx 로 당일(또는 최근 영업일) 일봉을 가져와 prices upsert."""
    from pykrx import stock
    ymd = TODAY.strftime("%Y%m%d")
    rows = []
    for t in tickers:
        try:
            df = stock.get_market_ohlcv_by_date(ymd, ymd, t["symbol"])
            if df.empty:
                continue
            r = df.iloc[-1]
            rows.append({
                "ticker_id":  t["id"],
                "date":       TODAY.isoformat(),
                "close":      float(r["종가"]),
                "change_pct": float(r.get("등락률", 0.0)),
                "volume":     int(r["거래량"]),
            })
        except Exception as e:
            print(f"[price] {t['symbol']} 실패: {e}")
    if rows:
        sb.table("prices").upsert(rows, on_conflict="ticker_id,date").execute()
    print(f"[price] {len(rows)}건 upsert")


# ======================================================================
# 2) 뉴스 수집 (네이버 검색 API)
# ======================================================================
def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()

def collect_news(tickers):
    """종목 aliases 로 뉴스 검색, url_hash 로 dedup 후 새 기사만 반환."""
    headers = {
        "X-Naver-Client-Id":     os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
    }
    new_items = []
    for t in tickers:
        query = (t["aliases"] or [t["name"]])[0]
        try:
            resp = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers=headers,
                params={"query": query, "display": NEWS_PER_TICKER, "sort": "date"},
                timeout=10,
            )
            items = resp.json().get("items", [])
        except Exception as e:
            print(f"[news] {query} 실패: {e}")
            continue

        for it in items:
            url = it.get("originallink") or it.get("link")
            h = _hash(url)
            # 이미 있으면 skip
            exists = sb.table("news").select("id").eq("url_hash", h).execute()
            if exists.data:
                continue
            new_items.append({
                "ticker_id":    t["id"],
                "url_hash":     h,
                "title":        _strip_tags(it.get("title", "")),
                "url":          url,
                "source":       "naver",
                "published_at": _parse_pubdate(it.get("pubDate")),
                # sentiment/summary/tags 는 다음 단계에서 채움
                "_desc":        _strip_tags(it.get("description", "")),
            })
    print(f"[news] 신규 {len(new_items)}건")
    return new_items

def _strip_tags(s: str) -> str:
    return s.replace("<b>", "").replace("</b>", "").replace("&quot;", '"').strip()

def _parse_pubdate(s):
    try:
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z").isoformat()
    except Exception:
        return None


# ======================================================================
# 3) LLM 감정/태그 (구조화 JSON)
# ======================================================================
def enrich_news(items):
    """각 기사에 sentiment(-1~1), tags, 요약을 붙여 news upsert."""
    enriched = []
    for it in items:
        prompt = (
            "다음 뉴스의 제목과 요약을 보고 JSON 만 출력하라. 다른 말 금지.\n"
            '형식: {"sentiment": -1.0~1.0, "tags": ["..."], "summary": "한 줄 한국어 요약"}\n'
            f'제목: {it["title"]}\n요약: {it["_desc"]}'
        )
        try:
            msg = ai.messages.create(
                model=CHEAP_MODEL, max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(_only_json(msg.content[0].text))
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
        sb.table("news").upsert(enriched, on_conflict="url_hash").execute()
    print(f"[sentiment] {len(enriched)}건 처리")

def _only_json(text: str) -> str:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return text.strip()


# ======================================================================
# 4) 감정 일집계 + 5) 감정 급변 시그널
# ======================================================================
def aggregate_and_signal(tickers):
    for t in tickers:
        # 오늘 뉴스 감정 모으기
        today_news = sb.table("news").select("id,sentiment") \
            .eq("ticker_id", t["id"]) \
            .gte("published_at", TODAY.isoformat()) \
            .execute().data
        if not today_news:
            continue
        sents = [n["sentiment"] for n in today_news if n["sentiment"] is not None]
        if not sents:
            continue
        avg = sum(sents) / len(sents)

        # 기준선 = 직전 BASELINE_DAYS 일 평균 (오늘 제외)
        since = (TODAY - timedelta(days=BASELINE_DAYS)).isoformat()
        hist = sb.table("sentiment_daily").select("avg_sentiment") \
            .eq("ticker_id", t["id"]) \
            .gte("date", since).lt("date", TODAY.isoformat()) \
            .execute().data
        baseline = (sum(h["avg_sentiment"] for h in hist) / len(hist)) if hist else avg

        sb.table("sentiment_daily").upsert({
            "ticker_id": t["id"], "date": TODAY.isoformat(),
            "avg_sentiment": avg, "news_count": len(sents), "baseline": baseline,
        }, on_conflict="ticker_id,date").execute()

        # 시그널 판정
        delta = avg - baseline
        if len(sents) >= MIN_NEWS and abs(delta) >= THRESHOLD:
            stype = "sentiment_surge_pos" if delta > 0 else "sentiment_surge_neg"
            severity = "high" if abs(delta) >= 0.7 else "mid" if abs(delta) >= 0.5 else "low"
            sb.table("signals").upsert({
                "ticker_id": t["id"], "date": TODAY.isoformat(),
                "type": stype, "severity": severity,
                "evidence": {"delta": round(delta, 3), "avg": round(avg, 3),
                             "baseline": round(baseline, 3), "news_count": len(sents),
                             "news_ids": [n["id"] for n in today_news]},
            }, on_conflict="ticker_id,date,type").execute()
            print(f"[signal] {t['symbol']} {stype} delta={delta:.2f}")


# ======================================================================
# 6) LLM 리포트 (그라운딩)
# ======================================================================
def build_report(tickers):
    """오늘 시그널 + 종목별 감정 집계만 근거로 리포트 생성."""
    sigs = sb.table("signals").select("*").eq("date", TODAY.isoformat()).execute().data
    daily = sb.table("sentiment_daily").select("*").eq("date", TODAY.isoformat()).execute().data
    name_of = {t["id"]: t["name"] for t in tickers}

    payload = {
        "date": TODAY.isoformat(),
        "signals": [{"name": name_of.get(s["ticker_id"]), "type": s["type"],
                     "severity": s["severity"], **s["evidence"]} for s in sigs],
        "sentiment": [{"name": name_of.get(d["ticker_id"]),
                       "avg": d["avg_sentiment"], "baseline": d["baseline"],
                       "news_count": d["news_count"]} for d in daily],
    }
    prompt = (
        "너는 시장 뉴스 감정 브리핑을 쓰는 애널리스트다. 아래 JSON 데이터만 근거로 "
        "한국어 마크다운 리포트를 작성하라. 데이터에 없는 수치·전망·투자의견은 절대 쓰지 마라. "
        "각 언급 끝에 근거가 된 종목명을 괄호로 표기하라.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    msg = ai.messages.create(
        model=REPORT_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    body = msg.content[0].text
    sb.table("reports").upsert({
        "date": TODAY.isoformat(), "scope": "market", "body_md": body,
        "model": REPORT_MODEL,
        "source_refs": [s["id"] for s in sigs],
    }, on_conflict="date,scope").execute()
    print("[report] 생성 완료")


# ======================================================================
def main():
    tickers = sb.table("tickers").select("*").eq("active", True).execute().data
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
