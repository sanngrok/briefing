"""
test_api.py — 서빙 레이어 통합 테스트 (M6, Supabase 불필요)

FastAPI dependency_overrides 로 가짜 repo 를 주입해 라우팅·검증·응답 스키마·
404/422 를 실제 DB 없이 검증한다.

실행:  python -m pytest api/tests -v   (repo 루트에서)
"""

from datetime import date as Date

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.db import get_repo
from api.services import (
    build_quotes,
    merge_live_quotes,
    merge_metric_series,
    rank_news,
    split_movers,
    to_signal,
)


class FakeRepo:
    def latest_report(self):
        return {"date": "2026-07-24", "scope": "market", "body_md": "# 리포트",
                "model": "claude-sonnet-5", "created_at": "2026-07-24T16:00:00+09:00"}

    def report_by_date(self, d):
        return self.latest_report() if d == "2026-07-24" else None

    def tickers(self):
        return [{"symbol": "005930", "name": "삼성전자"},
                {"symbol": "000660", "name": "SK하이닉스"}]

    def ticker_by_symbol(self, symbol):
        return {"id": 1, "symbol": "005930", "name": "삼성전자"} if symbol == "005930" else None

    def latest_price_date(self):
        return "2026-07-24"

    def prices_on(self, date):
        return [
            {"date": date, "close": 100, "change_pct": 3.1, "volume": 10,
             "tickers": {"symbol": "005930", "name": "삼성전자"}},
            {"date": date, "close": 200, "change_pct": -5.4, "volume": 20,
             "tickers": {"symbol": "000660", "name": "SK하이닉스"}},
            {"date": date, "close": 300, "change_pct": 7.2, "volume": 30,
             "tickers": {"symbol": "035420", "name": "NAVER"}},
            {"date": date, "close": 400, "change_pct": 0.0, "volume": 40,
             "tickers": {"symbol": "035720", "name": "카카오"}},
        ]

    def news(self, ticker_id=None, frm=None, to=None, limit=120):
        rows = [
            {"title": "약한 감정 기사", "url": "https://e.com/1", "source": "naver",
             "published_at": "2026-07-24T10:00:00+09:00", "sentiment": 0.1,
             "issue_tags": ["실적"], "summary": "요약1",
             "tickers": {"symbol": "005930", "name": "삼성전자"}},
            {"title": "강한 악재 기사", "url": "https://e.com/2", "source": "naver",
             "published_at": "2026-07-24T09:00:00+09:00", "sentiment": -0.9,
             "issue_tags": ["리콜"], "summary": "요약2",
             "tickers": {"symbol": "005930", "name": "삼성전자"}},
        ]
        return rows[:limit]

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


@pytest.fixture(autouse=True)
def _quotes_never_live_by_default(monkeypatch):
    """실제 현재 시각·네트워크에 좌우되지 않도록, 명시적으로 켜는 테스트 외엔 항상 꺼둔다.

    해외 조회는 시간대로 거르지 않으므로(미국 장은 한국 새벽) 여기서 막지 않으면
    테스트가 네이버를 실제로 부른다.
    """
    monkeypatch.setattr("api.routers.quotes.is_market_live_window", lambda: False)
    monkeypatch.setattr("api.routers.quotes.fetch_world_quotes", lambda symbols: {})


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


# --- tickers 목록 ----------------------------------------------------
def test_list_tickers():
    r = client.get("/api/tickers")
    assert r.status_code == 200
    assert [t["symbol"] for t in r.json()] == ["005930", "000660"]


# --- news ------------------------------------------------------------
def test_news_ranked_by_sentiment_strength():
    r = client.get("/api/news")
    assert r.status_code == 200
    items = r.json()
    # |sentiment| 가 큰 악재 기사가 앞으로
    assert items[0]["title"] == "강한 악재 기사"
    assert items[0]["symbol"] == "005930" and items[0]["issue_tags"] == ["리콜"]


def test_news_limit_applied():
    assert len(client.get("/api/news", params={"limit": 1}).json()) == 1


def test_news_unknown_symbol_404():
    assert client.get("/api/news", params={"symbol": "999999"}).status_code == 404


def test_news_limit_out_of_range_422():
    assert client.get("/api/news", params={"limit": 0}).status_code == 422


# --- movers ----------------------------------------------------------
def test_movers_splits_gainers_and_losers():
    r = client.get("/api/movers")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2026-07-24"
    # 상승은 높은 순, 하락은 낮은 순
    assert [g["name"] for g in body["gainers"]] == ["NAVER", "삼성전자"]
    assert [l["name"] for l in body["losers"]] == ["SK하이닉스"]
    # 보합(0%)은 어느 쪽에도 들어가지 않는다
    assert all(m["name"] != "카카오" for m in body["gainers"] + body["losers"])


def test_movers_limit_applied():
    body = client.get("/api/movers", params={"limit": 1}).json()
    assert len(body["gainers"]) == 1 and body["gainers"][0]["name"] == "NAVER"


def test_movers_limit_out_of_range_422():
    assert client.get("/api/movers", params={"limit": 99}).status_code == 422


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


def test_rank_news_pure_orders_by_strength_and_handles_nulls():
    out = rank_news(
        [
            {"title": "a", "sentiment": 0.2},
            {"title": "b", "sentiment": None},      # 감정 없음 → 0 취급, 뒤로
            {"title": "c", "sentiment": -0.7},      # 부호와 무관하게 강도 우선
        ],
        limit=3,
    )
    assert [n["title"] for n in out] == ["c", "a", "b"]
    assert out[1]["issue_tags"] == [] and out[1]["symbol"] is None


def test_split_movers_pure_ignores_missing_change():
    out = split_movers(
        [
            {"date": "2026-07-24", "change_pct": None, "tickers": {"symbol": "a", "name": "A"}},
            {"date": "2026-07-24", "change_pct": -1.0, "tickers": {"symbol": "b", "name": "B"}},
            {"date": "2026-07-24", "change_pct": 2.0, "tickers": {"symbol": "c", "name": "C"}},
        ],
        limit=5,
    )
    assert [m["name"] for m in out["gainers"]] == ["C"]
    assert [m["name"] for m in out["losers"]] == ["B"]   # change_pct 없는 A 는 제외


def test_rank_news_coerces_bad_tags():
    out = rank_news([{"title": "x", "sentiment": 0.1, "issue_tags": "리콜"}], limit=1)
    assert out[0]["issue_tags"] == []   # list 가 아니면 빈 리스트


# ---- /api/quotes (포트폴리오 평가용) ----

def test_quotes_returns_all_watchlist_by_default():
    r = client.get("/api/quotes")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2026-07-24"
    assert {q["symbol"] for q in body["quotes"]} == {"005930", "000660", "035420", "035720"}
    first = body["quotes"][0]
    assert set(first) == {"symbol", "name", "date", "close", "change_pct"}


def test_quotes_filters_by_symbols_in_requested_order():
    r = client.get("/api/quotes?symbols=035420,005930")
    assert r.status_code == 200
    assert [q["symbol"] for q in r.json()["quotes"]] == ["035420", "005930"]


def test_quotes_skips_unknown_symbol_instead_of_404():
    """워치리스트 밖 종목을 보유 중일 수 있으므로 404 대신 조용히 제외한다."""
    r = client.get("/api/quotes?symbols=005930,999999")
    assert r.status_code == 200
    assert [q["symbol"] for q in r.json()["quotes"]] == ["005930"]


def test_quotes_empty_symbols_returns_nothing():
    r = client.get("/api/quotes?symbols=")
    assert r.status_code == 200
    assert r.json() == {"date": "2026-07-24", "quotes": [], "live": False}


def test_quotes_rejects_bad_date():
    assert client.get("/api/quotes?date=2026-13-01").status_code == 422


def test_quotes_live_window_overlays_naver_price(monkeypatch):
    """장중~시간외 시간대면 네이버 실시간 값으로 close/change_pct 를 덮어쓴다."""
    monkeypatch.setattr("api.routers.quotes.is_market_live_window", lambda: True)
    monkeypatch.setattr(
        "api.routers.quotes.fetch_live_quotes",
        lambda symbols: {"005930": {"close": 274500.0, "change_pct": 5.17}},
    )
    r = client.get("/api/quotes?symbols=005930")
    body = r.json()
    assert body["live"] is True
    assert body["quotes"][0]["close"] == 274500.0
    assert body["quotes"][0]["change_pct"] == 5.17


def test_quotes_live_window_falls_back_when_naver_fails(monkeypatch):
    """네이버 호출이 실패하면(빈 dict) DB 값 그대로 쓰고 live=False 로 보고한다."""
    monkeypatch.setattr("api.routers.quotes.is_market_live_window", lambda: True)
    monkeypatch.setattr("api.routers.quotes.fetch_live_quotes", lambda symbols: {})
    r = client.get("/api/quotes?symbols=005930")
    body = r.json()
    assert body["live"] is False
    assert body["quotes"][0]["close"] == 100   # FakeRepo 의 DB 값 그대로


def test_quotes_explicit_date_skips_live_overlay(monkeypatch):
    """과거 특정일 조회에는 실시간 값을 덮어쓰지 않는다."""
    monkeypatch.setattr("api.routers.quotes.is_market_live_window", lambda: True)
    calls = []
    monkeypatch.setattr(
        "api.routers.quotes.fetch_live_quotes",
        lambda symbols: calls.append(symbols) or {},
    )
    r = client.get("/api/quotes?date=2026-07-24")
    assert r.json()["live"] is False
    assert calls == []


def test_build_quotes_pure_dedups_and_ignores_rows_without_ticker():
    out = build_quotes(
        [
            {"date": "2026-07-24", "close": 1, "change_pct": 1.0},                    # 임베딩 없음
            {"date": "2026-07-24", "close": 2, "change_pct": 2.0, "tickers": {}},     # symbol 없음
            {"date": "2026-07-24", "close": 3, "change_pct": 3.0,
             "tickers": {"symbol": "005930", "name": "삼성전자"}},
        ],
        symbols=["005930", "005930"],   # 중복 요청 → 1건
    )
    assert len(out) == 1
    assert out[0] == {"symbol": "005930", "name": "삼성전자", "date": "2026-07-24",
                      "close": 3, "change_pct": 3.0}


def test_build_quotes_pure_sorts_by_symbol_when_unfiltered():
    rows = [
        {"date": "d", "tickers": {"symbol": "b", "name": "B"}},
        {"date": "d", "tickers": {"symbol": "a", "name": "A"}},
    ]
    assert [q["symbol"] for q in build_quotes(rows)] == ["a", "b"]


# ---- 워치리스트 밖 보유 종목도 장중엔 실시간으로 (DB 행이 없어도) ----
def _live_on(monkeypatch, live_map, seen=None):
    monkeypatch.setattr("api.routers.quotes.is_market_live_window", lambda: True)
    monkeypatch.setattr("api.routers.quotes.kst_today", lambda: Date(2026, 7, 25))

    def fake(symbols):
        if seen is not None:
            seen.append(list(symbols))
        return live_map

    monkeypatch.setattr("api.routers.quotes.fetch_live_quotes", fake)


def test_quotes_live_fills_symbol_missing_from_db(monkeypatch):
    """보유 중이지만 워치리스트 밖이라 DB 시세가 없는 종목도 실시간 값으로 채운다."""
    _live_on(monkeypatch, {
        "005930": {"close": 280000.0, "change_pct": 2.19, "name": "삼성전자"},
        "068270": {"close": 195000.0, "change_pct": -1.3, "name": "셀트리온"},
    })
    body = client.get("/api/quotes?symbols=005930,068270").json()
    assert body["live"] is True
    assert [q["symbol"] for q in body["quotes"]] == ["005930", "068270"]

    filled = body["quotes"][1]
    assert filled["name"] == "셀트리온"        # 이름은 네이버 응답에서 온다
    assert filled["close"] == 195000.0
    assert filled["change_pct"] == -1.3
    assert filled["date"] == "2026-07-25"      # 기준일이 아니라 오늘(실시간 값이므로)


def test_quotes_live_asks_naver_for_symbols_missing_from_db(monkeypatch):
    """DB 행이 없어 build_quotes 에서 빠진 종목도 네이버에는 물어봐야 한다."""
    seen = []
    _live_on(monkeypatch, {}, seen)
    client.get("/api/quotes?symbols=005930,068270")
    assert seen == [["005930", "068270"]]


def test_quotes_live_skips_symbol_with_neither_db_nor_live(monkeypatch):
    """DB 에도 없고 네이버도 모르는 종목은 그대로 빠진다(404 아님)."""
    _live_on(monkeypatch, {"005930": {"close": 280000.0, "change_pct": 2.19,
                                      "name": "삼성전자"}})
    body = client.get("/api/quotes?symbols=005930,999999").json()
    assert [q["symbol"] for q in body["quotes"]] == ["005930"]


def test_quotes_live_watchlist_wide_still_overlays(monkeypatch):
    """symbols 미지정(워치리스트 전체)이면 끼워 넣을 대상이 없고 덮어쓰기만 한다."""
    _live_on(monkeypatch, {"005930": {"close": 280000.0, "change_pct": 2.19,
                                      "name": "삼성전자"}})
    body = client.get("/api/quotes").json()
    assert len(body["quotes"]) == 4                     # FakeRepo 의 4종목 그대로
    got = {q["symbol"]: q["close"] for q in body["quotes"]}
    assert got["005930"] == 280000.0                    # 덮어써짐
    assert got["000660"] == 200                         # 실시간 값 없으면 DB 값


# ---- merge_live_quotes (순수 함수) ----
DB_ROWS = [
    {"symbol": "005930", "name": "삼성전자", "date": "2026-07-24", "close": 100,
     "change_pct": 1.0},
]
TODAY = Date(2026, 7, 25)


def test_merge_overwrites_db_row_with_live_value():
    out = merge_live_quotes(
        DB_ROWS, {"005930": {"close": 280000.0, "change_pct": 2.19}},
        ["005930"], TODAY)
    assert out[0]["close"] == 280000.0 and out[0]["change_pct"] == 2.19
    assert out[0]["date"] == "2026-07-24"      # DB 행의 기준일은 유지


def test_merge_keeps_db_row_when_no_live_value():
    out = merge_live_quotes(DB_ROWS, {}, ["005930"], TODAY)
    assert out[0]["close"] == 100


def test_merge_preserves_requested_order_and_dedups():
    live = {"068270": {"close": 1.0, "change_pct": 0.0, "name": "셀트리온"}}
    out = merge_live_quotes(DB_ROWS, live, ["068270", "005930", "068270"], TODAY)
    assert [q["symbol"] for q in out] == ["068270", "005930"]


def test_merge_without_symbols_only_overwrites():
    """워치리스트 전체 조회(symbols=None)에는 새 행을 만들지 않는다."""
    live = {"005930": {"close": 9.0, "change_pct": 0.0},
            "068270": {"close": 1.0, "change_pct": 0.0, "name": "셀트리온"}}
    out = merge_live_quotes(DB_ROWS, live, None, TODAY)
    assert [q["symbol"] for q in out] == ["005930"]
    assert out[0]["close"] == 9.0


def test_merge_does_not_mutate_input_rows():
    rows = [dict(DB_ROWS[0])]
    merge_live_quotes(rows, {"005930": {"close": 9.0, "change_pct": 0.0}},
                      ["005930"], TODAY)
    assert rows[0]["close"] == 100


def test_merge_filled_row_falls_back_to_blank_name():
    live = {"068270": {"close": 1.0, "change_pct": None}}   # name 없음
    out = merge_live_quotes([], live, ["068270"], TODAY)
    assert out[0]["name"] == "" and out[0]["change_pct"] is None


# ---- 해외 종목 (네이버 해외 시세, 원화 환산) ----
def _world_on(monkeypatch, world_map, seen=None):
    """해외 응답만 주입한다. 국내 장 시간대는 꺼진 채로 둔다(기본 fixture)."""
    monkeypatch.setattr("api.routers.quotes.kst_today", lambda: Date(2026, 7, 25))

    def fake(symbols):
        if seen is not None:
            seen.append(list(symbols))
        return world_map

    monkeypatch.setattr("api.routers.quotes.fetch_world_quotes", fake)


def test_quotes_fills_world_symbol_even_outside_korean_hours(monkeypatch):
    """미국 장은 한국 새벽이라, 국내 장 시간대가 아니어도 해외 시세는 채운다."""
    _world_on(monkeypatch, {
        "AAPL": {"close": 460751.96, "change_pct": 0.23, "name": "애플",
                 "market_open": False},
    })
    body = client.get("/api/quotes?symbols=005930,AAPL").json()
    assert [q["symbol"] for q in body["quotes"]] == ["005930", "AAPL"]
    aapl = body["quotes"][1]
    assert aapl["name"] == "애플"
    assert aapl["close"] == 460751.96        # 원화 환산된 값
    assert body["quotes"][0]["close"] == 100  # 국내는 장 시간대가 아니라 DB 값 그대로


def test_quotes_world_market_closed_is_not_reported_live(monkeypatch):
    """장이 닫혀 있으면 값은 채우되 live 로 표시하지 않는다."""
    _world_on(monkeypatch, {"AAPL": {"close": 1.0, "change_pct": 0.0, "name": "애플",
                                     "market_open": False}})
    assert client.get("/api/quotes?symbols=AAPL").json()["live"] is False


def test_quotes_world_market_open_is_reported_live(monkeypatch):
    """미국 장이 열려 있으면 live=True — 프론트가 폴링을 이어갈 근거가 된다."""
    _world_on(monkeypatch, {"AAPL": {"close": 1.0, "change_pct": 0.0, "name": "애플",
                                     "market_open": True}})
    assert client.get("/api/quotes?symbols=AAPL").json()["live"] is True


def test_quotes_explicit_date_skips_world_too(monkeypatch):
    """과거 날짜 조회에는 해외 시세도 묻지 않는다."""
    seen = []
    _world_on(monkeypatch, {}, seen)
    assert client.get("/api/quotes?date=2026-07-24&symbols=AAPL").json()["live"] is False
    assert seen == []


def test_quotes_mixed_domestic_and_world(monkeypatch):
    """국내 실시간과 해외를 함께 내려도 요청 순서가 유지된다."""
    monkeypatch.setattr("api.routers.quotes.is_market_live_window", lambda: True)
    monkeypatch.setattr(
        "api.routers.quotes.fetch_live_quotes",
        lambda symbols: {"005930": {"close": 280000.0, "change_pct": 2.19,
                                    "name": "삼성전자"}},
    )
    _world_on(monkeypatch, {"AAPL": {"close": 460751.96, "change_pct": 0.23,
                                     "name": "애플", "market_open": True}})
    body = client.get("/api/quotes?symbols=AAPL,005930").json()
    assert [q["symbol"] for q in body["quotes"]] == ["AAPL", "005930"]
    assert body["quotes"][1]["close"] == 280000.0
    assert body["live"] is True
