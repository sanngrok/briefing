"""quotes 라우터 — 최근 영업일 종목 시세 (읽기 전용).

포트폴리오 평가용. 보유 종목이 N개일 때 /api/tickers/{symbol}/metrics 를 N번
부르는 대신 한 번에 받아간다(시계열 없이 최신 종가·등락률만).
"""

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.db import ReadRepo, get_repo
from api.models import Quotes
from api.services import build_quotes

router = APIRouter(prefix="/api/quotes", tags=["quotes"])

MAX_SYMBOLS = 100


@router.get("", response_model=Quotes)
def list_quotes(
    symbols: Optional[str] = Query(
        None, description="종목코드 콤마 구분(생략 시 워치리스트 전체)"
    ),
    date: Optional[Date] = Query(None, description="기준일(생략 시 시세가 있는 최근일)"),
    repo: ReadRepo = Depends(get_repo),
):
    """기준일의 종목별 종가·등락률을 반환한다.

    기준일을 안 주면 시세가 있는 가장 최근일을 쓴다(휴장일에도 직전 영업일이 잡힘).
    """
    target = date.isoformat() if date else repo.latest_price_date()
    if not target:
        return {"date": None, "quotes": []}

    wanted: Optional[list[str]] = None
    if symbols is not None:
        wanted = [s.strip() for s in symbols.split(",") if s.strip()][:MAX_SYMBOLS]
        if not wanted:
            return {"date": target, "quotes": []}

    return {"date": target, "quotes": build_quotes(repo.prices_on(target), wanted)}
