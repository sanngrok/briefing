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
