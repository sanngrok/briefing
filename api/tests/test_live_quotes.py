"""test_live_quotes.py — live_quotes.py 순수 함수 테스트 (네트워크 불필요).

실행:  python -m pytest api/tests -v   (repo 루트에서)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import api.live_quotes as lq
from api.live_quotes import _to_float, fetch_live_quotes, is_market_live_window

KST = ZoneInfo("Asia/Seoul")


# --- is_market_live_window --------------------------------------------

def test_live_window_true_during_market_hours():
    # 2026-09-21 은 월요일
    assert is_market_live_window(datetime(2026, 9, 21, 10, 0, tzinfo=KST)) is True


def test_live_window_true_at_after_market_single_price():
    assert is_market_live_window(datetime(2026, 9, 21, 17, 30, tzinfo=KST)) is True


def test_live_window_false_before_open():
    assert is_market_live_window(datetime(2026, 9, 21, 8, 59, tzinfo=KST)) is False


def test_live_window_false_after_close():
    assert is_market_live_window(datetime(2026, 9, 21, 18, 1, tzinfo=KST)) is False


def test_live_window_false_on_weekend():
    # 2026-09-19 는 토요일, 장중 시간대여도 False
    assert is_market_live_window(datetime(2026, 9, 19, 10, 0, tzinfo=KST)) is False


def test_live_window_boundary_is_inclusive():
    assert is_market_live_window(datetime(2026, 9, 21, 9, 0, tzinfo=KST)) is True
    assert is_market_live_window(datetime(2026, 9, 21, 18, 0, tzinfo=KST)) is True


# --- _to_float ----------------------------------------------------------

def test_to_float_strips_commas():
    assert _to_float("274,000") == 274000.0


def test_to_float_keeps_negative_sign():
    """등락률은 네이버 응답에 이미 부호가 들어있다(하락 = 음수 문자열)."""
    assert _to_float("-2.75") == -2.75


def test_to_float_none_and_blank():
    assert _to_float(None) is None
    assert _to_float("") is None


def test_to_float_non_numeric_is_none():
    assert _to_float("N/A") is None


# --- KRX 6자리 코드만 묻는다 (네트워크 불필요) --------------------------

def test_fetch_skips_non_krx_symbols_without_calling(monkeypatch):
    """해외 티커·오타는 이 엔드포인트가 모른다. 남는 게 없으면 호출 자체를 안 한다."""
    called = []
    monkeypatch.setattr(lq, "_cache", {})
    monkeypatch.setitem(__import__("sys").modules, "requests",
                        type("M", (), {"get": lambda *a, **k: called.append(a)})())
    assert fetch_live_quotes(["AAPL", "TSLA", "00593"]) == {}
    assert called == []


def test_fetch_empty_input_returns_empty():
    assert fetch_live_quotes([]) == {}
    assert fetch_live_quotes(None) == {}


def test_fetch_returns_name_close_and_change(monkeypatch):
    """DB 행이 없는 종목을 채우려면 종목명도 함께 필요하다."""
    monkeypatch.setattr(lq, "_cache", {})

    class FakeRes:
        def raise_for_status(self): pass
        def json(self):
            return {"datas": [
                {"itemCode": "068270", "stockName": "셀트리온",
                 "closePrice": "195,000", "fluctuationsRatio": "-1.30"},
            ]}

    monkeypatch.setitem(__import__("sys").modules, "requests",
                        type("M", (), {"get": staticmethod(lambda *a, **k: FakeRes())})())
    out = fetch_live_quotes(["068270", "AAPL"])     # 해외 티커는 걸러지고
    assert out == {"068270": {"close": 195000.0, "change_pct": -1.3,
                              "name": "셀트리온"}}


def test_fetch_network_failure_returns_empty(monkeypatch):
    """비공식 API라 언제든 막힐 수 있다 — 조용히 빈 dict(호출부가 DB 값으로 폴백)."""
    monkeypatch.setattr(lq, "_cache", {})

    def boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setitem(__import__("sys").modules, "requests",
                        type("M", (), {"get": staticmethod(boom)})())
    assert fetch_live_quotes(["005930"]) == {}


# --- kst_today ---------------------------------------------------------

def test_kst_today_is_seoul_date():
    from api.live_quotes import kst_today
    assert kst_today() == datetime.now(KST).date()
