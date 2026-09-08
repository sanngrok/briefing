"""
models.py — Pydantic 응답 모델 (API 계약 고정)

응답 스키마를 여기서 못 박아 프론트/백엔드 간 계약을 명시한다.
"""

from datetime import date as Date
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict


class Report(BaseModel):
    # 'model' 필드가 Pydantic 보호 네임스페이스(model_)와 충돌하지 않도록 해제
    model_config = ConfigDict(protected_namespaces=())

    date: Date
    scope: str
    body_md: str
    model: Optional[str] = None
    created_at: Optional[str] = None


class Ticker(BaseModel):
    symbol: str
    name: str


class NewsItem(BaseModel):
    title: str
    url: Optional[str] = None
    source: Optional[str] = None
    published_at: Optional[str] = None
    sentiment: Optional[float] = None
    issue_tags: list[str] = []
    summary: Optional[str] = None
    # 종목(FK 임베딩)
    symbol: Optional[str] = None
    name: Optional[str] = None


class MetricPoint(BaseModel):
    date: Date
    close: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    avg_sentiment: Optional[float] = None
    news_count: Optional[int] = None


class TickerMetrics(BaseModel):
    symbol: str
    name: str
    series: list[MetricPoint]


class Signal(BaseModel):
    date: Date
    symbol: Optional[str] = None
    name: Optional[str] = None
    type: str
    severity: Literal["low", "mid", "high"]
    evidence: dict = {}
