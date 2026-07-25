"""reports 라우터 — 일일 리포트 조회 (읽기 전용)."""

from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException

from api.db import ReadRepo, get_repo
from api.models import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])


# NOTE: '/latest' 를 '/{report_date}' 보다 먼저 선언해야 'latest' 가
#       날짜로 파싱되지 않는다.
@router.get("/latest", response_model=Report)
def latest_report(repo: ReadRepo = Depends(get_repo)):
    row = repo.latest_report()
    if not row:
        raise HTTPException(status_code=404, detail="리포트가 아직 없습니다")
    return row


@router.get("/{report_date}", response_model=Report)
def report_by_date(report_date: Date, repo: ReadRepo = Depends(get_repo)):
    row = repo.report_by_date(report_date.isoformat())
    if not row:
        raise HTTPException(status_code=404, detail=f"{report_date} 리포트가 없습니다")
    return row
