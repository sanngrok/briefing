"""news 라우터 — 주요 뉴스 조회 (읽기 전용)."""

from datetime import date as Date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.db import ReadRepo, get_repo
from api.models import NewsItem
from api.services import rank_news

router = APIRouter(prefix="/api/news", tags=["news"])

# 감정 강도로 순위를 매기기 전에 DB 에서 가져올 최근 기사 수.
# (PostgREST 로는 abs(sentiment) 정렬이 안 되므로 최근분을 받아 파이썬에서 정렬한다)
POOL_SIZE = 120


@router.get("", response_model=list[NewsItem])
def list_news(
    date: Optional[Date] = Query(None, description="해당 일자 발행분만"),
    symbol: Optional[str] = Query(None, description="종목 코드로 필터"),
    limit: int = Query(12, ge=1, le=50, description="반환할 기사 수"),
    repo: ReadRepo = Depends(get_repo),
):
    """최근 기사 중 감정 강도(|sentiment|)가 큰 순으로 반환한다."""
    ticker_id = None
    if symbol:
        ticker = repo.ticker_by_symbol(symbol)
        if not ticker:
            raise HTTPException(status_code=404, detail=f"종목 {symbol} 없음")
        ticker_id = ticker["id"]

    frm = to = None
    if date:
        frm = date.isoformat()
        to = (date + timedelta(days=1)).isoformat()

    rows = repo.news(ticker_id=ticker_id, frm=frm, to=to, limit=POOL_SIZE)
    return rank_news(rows, limit)
