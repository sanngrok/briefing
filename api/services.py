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
