"""signals 라우터 — 감정 급변 시그널 조회 (읽기 전용)."""

from datetime import date as Date
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query

from api.db import ReadRepo, get_repo
from api.models import Signal
from api.services import to_signal

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("", response_model=list[Signal])
def list_signals(
    date: Optional[Date] = Query(None, description="해당 일자만"),
    severity: Optional[Literal["low", "mid", "high"]] = Query(None),
    repo: ReadRepo = Depends(get_repo),
):
    rows = repo.signals(date.isoformat() if date else None, severity)
    return [to_signal(r) for r in rows]
