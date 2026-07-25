"""
db.py — 읽기 전용 데이터 접근 계층 (Repository)

라우터는 ReadRepo 에만 의존한다(관심사 분리). 테스트에서는
FastAPI 의 dependency_overrides 로 가짜 repo 를 주입해 DB 없이 검증한다.

주의: 이 계층은 SELECT 만 수행한다. 쓰기는 파이프라인 잡의 책임(하드룰 §4).
"""

from typing import Optional


class ReadRepo:
    """Supabase(PostgREST) 읽기 전용 래퍼."""

    def __init__(self, client):
        self._sb = client

    # --- reports ---
    def latest_report(self) -> Optional[dict]:
        r = (self._sb.table("reports").select("*")
             .eq("scope", "market").order("date", desc=True).limit(1).execute())
        return r.data[0] if r.data else None

    def report_by_date(self, d: str) -> Optional[dict]:
        r = (self._sb.table("reports").select("*")
             .eq("scope", "market").eq("date", d).limit(1).execute())
        return r.data[0] if r.data else None

    # --- tickers / metrics ---
    def ticker_by_symbol(self, symbol: str) -> Optional[dict]:
        r = (self._sb.table("tickers").select("id,symbol,name")
             .eq("symbol", symbol).limit(1).execute())
        return r.data[0] if r.data else None

    def prices(self, ticker_id: int, frm: Optional[str], to: Optional[str]) -> list:
        q = (self._sb.table("prices").select("date,close,change_pct,volume")
             .eq("ticker_id", ticker_id))
        if frm:
            q = q.gte("date", frm)
        if to:
            q = q.lte("date", to)
        return q.order("date").execute().data

    def sentiment_daily(self, ticker_id: int, frm: Optional[str], to: Optional[str]) -> list:
        q = (self._sb.table("sentiment_daily").select("date,avg_sentiment,news_count")
             .eq("ticker_id", ticker_id))
        if frm:
            q = q.gte("date", frm)
        if to:
            q = q.lte("date", to)
        return q.order("date").execute().data

    # --- signals ---
    def signals(self, date: Optional[str] = None, severity: Optional[str] = None) -> list:
        # tickers(symbol,name) 는 FK 임베딩(PostgREST)
        q = self._sb.table("signals").select("date,type,severity,evidence,tickers(symbol,name)")
        if date:
            q = q.eq("date", date)
        if severity:
            q = q.eq("severity", severity)
        return q.order("date", desc=True).execute().data


_repo: Optional[ReadRepo] = None


def get_repo() -> ReadRepo:
    """FastAPI 의존성. 최초 호출 시 Supabase 클라이언트를 지연 생성한다."""
    global _repo
    if _repo is None:
        from supabase import create_client
        from api.config import settings
        _repo = ReadRepo(create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY))
    return _repo
