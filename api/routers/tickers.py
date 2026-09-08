"""tickers 라우터 — 종목별 시세·감정 시계열 (읽기 전용)."""

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.db import ReadRepo, get_repo
from api.models import Ticker, TickerMetrics
from api.services import merge_metric_series

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("", response_model=list[Ticker])
def list_tickers(repo: ReadRepo = Depends(get_repo)):
    """활성 워치리스트. 프론트가 종목 탭을 하드코딩하지 않도록 여기서 받아간다."""
    return repo.tickers()


@router.get("/{symbol}/metrics", response_model=TickerMetrics)
def ticker_metrics(
    symbol: str,
    from_: Optional[Date] = Query(None, alias="from", description="시작일(포함)"),
    to: Optional[Date] = Query(None, description="종료일(포함)"),
    repo: ReadRepo = Depends(get_repo),
):
    if from_ and to and from_ > to:
        raise HTTPException(status_code=422, detail="from 이 to 보다 클 수 없습니다")

    ticker = repo.ticker_by_symbol(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"종목 {symbol} 없음")

    frm = from_.isoformat() if from_ else None
    to_s = to.isoformat() if to else None
    prices = repo.prices(ticker["id"], frm, to_s)
    sentiment = repo.sentiment_daily(ticker["id"], frm, to_s)

    return {
        "symbol": ticker["symbol"],
        "name": ticker["name"],
        "series": merge_metric_series(prices, sentiment),
    }
