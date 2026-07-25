"""
test_api.py — 서빙 레이어 통합 테스트 (M6, Supabase 불필요)

FastAPI dependency_overrides 로 가짜 repo 를 주입해 라우팅·검증·응답 스키마·
404/422 를 실제 DB 없이 검증한다.

실행:  python -m pytest api/tests -v   (repo 루트에서)
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.db import get_repo
from api.services import merge_metric_series, to_signal


class FakeRepo:
    def latest_report(self):
        return {"date": "2026-07-24", "scope": "market", "body_md": "# 리포트",
                "model": "claude-sonnet-5", "created_at": "2026-07-24T16:00:00+09:00"}

    def report_by_date(self, d):
        return self.latest_report() if d == "2026-07-24" else None

    def ticker_by_symbol(self, symbol):
        return {"id": 1, "symbol": "005930", "name": "삼성전자"} if symbol == "005930" else None

    def prices(self, ticker_id, frm, to):
        return [{"date": "2026-07-24", "close": 249500, "change_pct": -7.59, "volume": 26175580}]

    def sentiment_daily(self, ticker_id, frm, to):
        return [{"date": "2026-07-24", "avg_sentiment": -0.5, "news_count": 5}]

    def signals(self, date=None, severity=None):
        rows = [{
            "date": "2026-07-24", "type": "sentiment_surge_neg", "severity": "high",
            "evidence": {"delta": -0.8, "news_count": 5},
            "tickers": {"symbol": "005930", "name": "삼성전자"},
        }]
        if severity:
            rows = [r for r in rows if r["severity"] == severity]
        return rows


app.dependency_overrides[get_repo] = lambda: FakeRepo()
client = TestClient(app)


# --- health ----------------------------------------------------------
def test_health():
    assert client.get("/health").json() == {"status": "ok"}


# --- reports ---------------------------------------------------------
def test_latest_report():
    r = client.get("/api/reports/latest")
    assert r.status_code == 200
    assert r.json()["body_md"] == "# 리포트"


def test_report_by_date_found():
    r = client.get("/api/reports/2026-07-24")
    assert r.status_code == 200
    assert r.json()["date"] == "2026-07-24"


def test_report_by_date_not_found_404():
    assert client.get("/api/reports/2020-01-01").status_code == 404


def test_report_by_date_invalid_format_422():
    assert client.get("/api/reports/notadate").status_code == 422


# --- tickers/metrics -------------------------------------------------
def test_metrics_merges_price_and_sentiment():
    r = client.get("/api/tickers/005930/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "005930" and body["name"] == "삼성전자"
    pt = body["series"][0]
    # 같은 날짜에 시세와 감정이 한 포인트로 병합
    assert pt["close"] == 249500 and pt["avg_sentiment"] == -0.5


def test_metrics_unknown_symbol_404():
    assert client.get("/api/tickers/999999/metrics").status_code == 404


def test_metrics_from_after_to_422():
    r = client.get("/api/tickers/005930/metrics", params={"from": "2026-07-24", "to": "2026-07-01"})
    assert r.status_code == 422


# --- signals ---------------------------------------------------------
def test_signals_list_and_embedding():
    r = client.get("/api/signals")
    assert r.status_code == 200
    s = r.json()[0]
    assert s["symbol"] == "005930" and s["name"] == "삼성전자"
    assert s["severity"] == "high" and s["evidence"]["delta"] == -0.8


def test_signals_severity_filter():
    assert client.get("/api/signals", params={"severity": "low"}).json() == []


def test_signals_invalid_severity_422():
    assert client.get("/api/signals", params={"severity": "boom"}).status_code == 422


# --- pure services ---------------------------------------------------
def test_merge_metric_series_pure():
    out = merge_metric_series(
        [{"date": "2026-07-24", "close": 100, "change_pct": 1.0, "volume": 10}],
        [{"date": "2026-07-24", "avg_sentiment": 0.2, "news_count": 3},
         {"date": "2026-07-23", "avg_sentiment": -0.1, "news_count": 2}],
    )
    assert [p["date"] for p in out] == ["2026-07-23", "2026-07-24"]  # 정렬
    assert out[1]["close"] == 100 and out[1]["avg_sentiment"] == 0.2


def test_to_signal_without_embedding():
    s = to_signal({"date": "2026-07-24", "type": "x", "severity": "low"})
    assert s["symbol"] is None and s["evidence"] == {}
