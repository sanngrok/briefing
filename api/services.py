"""
services.py — 순수 변환 로직 (DB row → 응답 형태)

라우터에서 떼어내 단위 테스트로 고정한다. 네트워크/DB 없음.
"""


def merge_metric_series(prices: list, sentiment: list) -> list:
    """일별 시세와 감정 집계를 date 기준으로 병합해 시계열 포인트 리스트로.

    시세만/감정만 있는 날짜도 모두 포함하며 date 오름차순으로 정렬한다.
    """
    by_date: dict[str, dict] = {}
    for p in prices or []:
        row = by_date.setdefault(p["date"], {"date": p["date"]})
        row["close"] = p.get("close")
        row["change_pct"] = p.get("change_pct")
        row["volume"] = p.get("volume")
    for s in sentiment or []:
        row = by_date.setdefault(s["date"], {"date": s["date"]})
        row["avg_sentiment"] = s.get("avg_sentiment")
        row["news_count"] = s.get("news_count")
    return [by_date[d] for d in sorted(by_date)]


def to_mover(row: dict) -> dict:
    """prices row(+임베딩 tickers)를 Mover 응답 형태로 변환."""
    ticker = row.get("tickers") or {}
    return {
        "symbol": ticker.get("symbol", ""),
        "name": ticker.get("name", ""),
        "date": row["date"],
        "close": row.get("close"),
        "change_pct": row.get("change_pct"),
        "volume": row.get("volume"),
    }


def split_movers(rows: list, limit: int) -> dict:
    """등락률 기준으로 상승/하락 상위를 나눈다. (순수 함수)

    change_pct 가 없는 종목과 보합(0)은 어느 쪽에도 넣지 않는다.
    gainers 는 높은 순, losers 는 낮은 순으로 각각 limit 건.
    """
    items = [to_mover(r) for r in rows or []]
    scored = [m for m in items if m["change_pct"] is not None]
    gainers = sorted([m for m in scored if m["change_pct"] > 0],
                     key=lambda m: m["change_pct"], reverse=True)[:limit]
    losers = sorted([m for m in scored if m["change_pct"] < 0],
                    key=lambda m: m["change_pct"])[:limit]
    return {"gainers": gainers, "losers": losers}


def to_news_item(row: dict) -> dict:
    """news row(+임베딩 tickers)를 NewsItem 응답 형태로 변환."""
    ticker = row.get("tickers") or {}
    tags = row.get("issue_tags")
    if not isinstance(tags, list):
        tags = []
    return {
        "title": row.get("title") or "",
        "url": row.get("url"),
        "source": row.get("source"),
        "published_at": row.get("published_at"),
        "sentiment": row.get("sentiment"),
        "issue_tags": [str(t) for t in tags],
        "summary": row.get("summary"),
        "symbol": ticker.get("symbol"),
        "name": ticker.get("name"),
    }


def rank_news(rows: list, limit: int) -> list:
    """감정 강도(|sentiment|)가 큰 순으로 상위 limit건. (순수 함수)

    '주요 뉴스' = 긍정이든 부정이든 감정이 강하게 잡힌 기사.
    sentiment 가 없는 기사는 0으로 취급해 뒤로 밀린다.
    파이썬 정렬은 안정적이므로 동점이면 입력 순서(발행 최신순)가 유지된다.
    """
    items = [to_news_item(r) for r in rows or []]
    items.sort(key=lambda x: abs(x["sentiment"] or 0.0), reverse=True)
    return items[:limit]


def to_signal(row: dict) -> dict:
    """signals row(+임베딩 tickers)를 Signal 응답 형태로 변환."""
    ticker = row.get("tickers") or {}
    return {
        "date": row["date"],
        "type": row["type"],
        "severity": row["severity"],
        "evidence": row.get("evidence") or {},
        "symbol": ticker.get("symbol"),
        "name": ticker.get("name"),
    }


def build_quotes(rows: list, symbols: list | None = None) -> list:
    """특정 일자 시세 rows 를 종목별 1건의 시세(Quote) 목록으로. (순수 함수)

    symbols 를 주면 그 종목만, 요청한 순서 그대로 돌려준다(프론트가 재정렬할 필요 없음).
    시세가 없는 종목은 조용히 빠진다 — 워치리스트 밖 종목을 보유 중일 수 있기 때문에,
    없는 것을 404 로 막지 않고 "시세 없음"으로 표현하는 책임을 호출부에 넘긴다.
    """
    by_symbol: dict[str, dict] = {}
    for r in rows or []:
        ticker = r.get("tickers") or {}
        symbol = ticker.get("symbol")
        if not symbol:
            continue
        by_symbol[symbol] = {
            "symbol": symbol,
            "name": ticker.get("name", ""),
            "date": r["date"],
            "close": r.get("close"),
            "change_pct": r.get("change_pct"),
        }
    if symbols is None:
        return [by_symbol[s] for s in sorted(by_symbol)]
    out = []
    seen: set[str] = set()
    for s in symbols:
        if s in by_symbol and s not in seen:   # 중복 요청은 1건만
            seen.add(s)
            out.append(by_symbol[s])
    return out


def merge_live_quotes(quotes: list, live_map: dict, symbols: list | None,
                      today) -> list:
    """DB 시세에 장중 실시간 값을 덮어쓰고, DB 에 없는 종목은 실시간 값만으로 채운다. (순수 함수)

    build_quotes 는 DB 시세 행에서 목록을 만들기 때문에, 워치리스트 밖 보유 종목처럼
    시세 행이 없는 종목은 조용히 빠진다. 그러면 장중에도 대시보드에 "시세 없음"으로
    남는다 — 네이버는 그 종목의 현재가를 알고 있는데도. 그래서 요청받은 종목
    (`symbols`)을 기준으로 다시 훑어, 실시간 값이 있으면 행을 만들어 끼운다.

    - `symbols` 가 None(워치리스트 전체 조회)이면 끼워 넣을 대상이 없으므로 덮어쓰기만 한다.
    - 새로 만든 행의 날짜는 기준일이 아니라 `today` 다. 실시간 값은 오늘 것이기 때문.
    - 실시간 값도 DB 행도 없는 종목은 그대로 빠진다("시세 없음" 표시는 프론트 책임).
    """
    def overwritten(q: dict) -> dict:
        live = live_map.get(q["symbol"])
        if not live:
            return q
        return {**q, "close": live["close"], "change_pct": live.get("change_pct")}

    if symbols is None:
        return [overwritten(q) for q in quotes]

    by_symbol = {q["symbol"]: q for q in quotes}
    out: list = []
    seen: set[str] = set()
    for s in symbols:
        if s in seen:
            continue
        seen.add(s)
        if s in by_symbol:
            out.append(overwritten(by_symbol[s]))
            continue
        live = live_map.get(s)
        if live:
            out.append({
                "symbol": s,
                "name": live.get("name") or "",
                "date": today,
                "close": live["close"],
                "change_pct": live.get("change_pct"),
            })
    return out
