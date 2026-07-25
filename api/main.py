"""
main.py — FastAPI 진입점 (레이어 B, 읽기 전용 서빙)

로컬 실행:  uvicorn api.main:app --reload   (repo 루트에서)
CORS 는 프론트 도메인만 허용하고, GET 만 노출한다(읽기 전용).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import reports, signals, tickers

app = FastAPI(
    title="AI 시그널 리포트 API",
    description="뉴스 감정 급변 시그널·리포트 읽기 전용 서빙 레이어",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],   # 읽기 전용
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.include_router(reports.router)
app.include_router(tickers.router)
app.include_router(signals.router)
