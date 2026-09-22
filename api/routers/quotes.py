"""quotes 라우터 — 종목 시세 (읽기 전용).

포트폴리오 평가용. 보유 종목이 N개일 때 /api/tickers/{symbol}/metrics 를 N번
부르는 대신 한 번에 받아간다(시계열 없이 최신 종가·등락률만).

기본(날짜 미지정) 조회는 장중~시간외 단일가 시간대에 네이버 금융 실시간(비공식)
값으로 덮어써 "준실시간"을 낸다 — api/live_quotes.py 참고.
"""

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.db import ReadRepo, get_repo
from api.live_quotes import fetch_live_quotes, is_market_live_window
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
    이때 지금이 장중~시간외 단일가 시간대(평일 09:00~18:00 KST)면 네이버 금융의
    실시간(비공식) 값으로 close/change_pct 를 덮어쓴다 — DB 종가는 파이프라인이
    저녁에나 갱신하므로 장중엔 그대로면 전일 값이기 때문이다. 특정 date 를
    명시한 과거 조회에는 적용하지 않는다.
    """
    target = date.isoformat() if date else repo.latest_price_date()
    if not target:
        return {"date": None, "quotes": []}

    wanted: Optional[list[str]] = None
    if symbols is not None:
        wanted = [s.strip() for s in symbols.split(",") if s.strip()][:MAX_SYMBOLS]
        if not wanted:
            return {"date": target, "quotes": []}

    quotes = build_quotes(repo.prices_on(target), wanted)

    live = False
    if date is None and is_market_live_window():
        live_map = fetch_live_quotes([q["symbol"] for q in quotes])
        if live_map:
            live = True
            for q in quotes:
                l = live_map.get(q["symbol"])
                if l:
                    q["close"] = l["close"]
                    q["change_pct"] = l["change_pct"]

    return {"date": target, "quotes": quotes, "live": live}
