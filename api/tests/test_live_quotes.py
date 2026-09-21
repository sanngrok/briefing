"""test_live_quotes.py — live_quotes.py 순수 함수 테스트 (네트워크 불필요).

실행:  python -m pytest api/tests -v   (repo 루트에서)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from api.live_quotes import _to_float, is_market_live_window

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
