"""movers 라우터 — 급등락 종목 조회 (읽기 전용)."""

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.db import ReadRepo, get_repo
from api.models import Movers
from api.services import split_movers

router = APIRouter(prefix="/api/movers", tags=["movers"])


@router.get("", response_model=Movers)
def list_movers(
    date: Optional[Date] = Query(None, description="기준일(생략 시 시세가 있는 최근일)"),
    limit: int = Query(5, ge=1, le=20, description="상승·하락 각각 반환할 종목 수"),
    repo: ReadRepo = Depends(get_repo),
):
    """워치리스트 중 등락률 상위(상승/하락)를 반환한다.

    기준일을 안 주면 시세가 있는 가장 최근일을 쓴다(휴장일에도 직전 영업일이 잡힘).
    """
    target = date.isoformat() if date else repo.latest_price_date()
    if not target:
        return {"date": None, "gainers": [], "losers": []}

    rows = repo.prices_on(target)
    return {"date": target, **split_movers(rows, limit)}
