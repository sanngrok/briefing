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
#
# 120 이면 최근 3일치밖에 안 들어와서, 사건이 없던 며칠은 악재 후보 자체가 동난다.
# 300 이면 대략 한 주치가 들어온다(실측: 120건=3일 악재 15 / 300건=5일 악재 45).
POOL_SIZE = 300


@router.get("", response_model=list[NewsItem])
def list_news(
    date: Optional[Date] = Query(None, description="해당 일자 발행분만"),
    symbol: Optional[str] = Query(None, description="종목 코드로 필터"),
    limit: int = Query(12, ge=1, le=50, description="반환할 기사 수"),
    direction: str = Query(
        "all", pattern="^(all|good|bad)$",
        description="호재(good)/악재(bad)만 추리기. 기본은 전체(all)",
    ),
    repo: ReadRepo = Depends(get_repo),
):
    """최근 기사 중 감정 강도(|sentiment|)가 큰 순으로 반환한다.

    direction 을 주면 그 방향 안에서 강한 순으로 뽑는다. 전체를 줄 세운 뒤 자르면
    수가 많은 쪽(대개 호재)이 상위를 쓸어가서 반대쪽 목록이 비다시피 하기 때문이다.
    """
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
    return rank_news(rows, limit, direction)
