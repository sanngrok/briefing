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


# --- 해외(미국) 종목 --------------------------------------------------

def _stub_requests(monkeypatch, *, fx=1300.0, datas=None, boom=False):
    """환율 API 와 네이버 해외 시세를 URL 로 구분해 응답하는 가짜 requests."""
    monkeypatch.setattr(lq, "_world_cache", {})
    monkeypatch.setattr(lq, "_fx_cache", {})
    seen = {"urls": []}

    class Res:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def get(url, params=None, timeout=None):
        seen["urls"].append(url)
        if boom:
            raise RuntimeError("connection reset")
        if url.startswith(lq.FX_API_URL):
            return Res({"rates": {"KRW": fx}} if fx else {"rates": {}})
        return Res({"datas": datas or []})

    monkeypatch.setitem(__import__("sys").modules, "requests",
                        type("M", (), {"get": staticmethod(get)})())
    return seen


def test_world_candidates_covers_nasdaq_and_nyse():
    """나스닥은 `AAPL.O`, 뉴욕은 접미사 없는 평문(`JPM`)이 조회 키다."""
    assert lq.world_candidates("AAPL") == ["AAPL.O", "AAPL"]


def test_is_krx_code_splits_domestic_and_world():
    assert lq.is_krx_code("005930") and not lq.is_krx_code("AAPL")
    assert not lq.is_krx_code("00593") and not lq.is_krx_code("")


def test_world_converts_usd_to_krw(monkeypatch):
    """대시보드 합계가 원화 기준이라, 달러 시세는 환산해서 내려야 한다."""
    _stub_requests(monkeypatch, fx=1300.0, datas=[
        {"symbolCode": "AAPL", "stockName": "애플", "closePrice": "339.75",
         "fluctuationsRatio": "0.23", "marketStatus": "CLOSE"},
    ])
    out = lq.fetch_world_quotes(["AAPL"])
    assert out["AAPL"]["close"] == 339.75 * 1300.0
    assert out["AAPL"]["change_pct"] == 0.23     # 등락률은 종목 자체 값(환율 무관)
    assert out["AAPL"]["name"] == "애플"
    assert out["AAPL"]["market_open"] is False


def test_world_market_open_from_market_status(monkeypatch):
    """서머타임 때문에 한국 기준 개장 시각이 밀리므로, 네이버의 판단을 그대로 쓴다."""
    _stub_requests(monkeypatch, datas=[
        {"symbolCode": "AAPL", "stockName": "애플", "closePrice": "1",
         "fluctuationsRatio": "0", "marketStatus": "OPEN"},
    ])
    assert lq.fetch_world_quotes(["AAPL"])["AAPL"]["market_open"] is True


def test_world_returns_empty_without_fx_rate(monkeypatch):
    """환율을 못 구하면 통화가 뒤섞이므로 아예 내리지 않는다(가져오기 스냅샷으로 폴백)."""
    seen = _stub_requests(monkeypatch, fx=None, datas=[
        {"symbolCode": "AAPL", "stockName": "애플", "closePrice": "339.75",
         "fluctuationsRatio": "0.23", "marketStatus": "OPEN"},
    ])
    assert lq.fetch_world_quotes(["AAPL"]) == {}
    assert all(u.startswith(lq.FX_API_URL) for u in seen["urls"])   # 시세는 묻지도 않는다


def test_world_skips_krx_codes(monkeypatch):
    """국내 코드는 국내 엔드포인트 담당이다. 남는 게 없으면 호출 자체를 안 한다."""
    seen = _stub_requests(monkeypatch)
    assert lq.fetch_world_quotes(["005930", "000660"]) == {}
    assert seen["urls"] == []


def test_world_keeps_first_candidate_when_both_match(monkeypatch):
    """`AAPL.O` 와 `AAPL` 이 모두 응답에 오면 먼저 온 것 하나만 쓴다."""
    _stub_requests(monkeypatch, fx=1000.0, datas=[
        {"symbolCode": "AAPL", "stockName": "애플", "closePrice": "1",
         "fluctuationsRatio": "0", "marketStatus": "CLOSE"},
        {"symbolCode": "AAPL", "stockName": "애플(중복)", "closePrice": "2",
         "fluctuationsRatio": "0", "marketStatus": "CLOSE"},
    ])
    out = lq.fetch_world_quotes(["AAPL"])
    assert len(out) == 1 and out["AAPL"]["close"] == 1000.0


def test_world_network_failure_returns_empty(monkeypatch):
    _stub_requests(monkeypatch, boom=True)
    assert lq.fetch_world_quotes(["AAPL"]) == {}


def test_fx_rate_is_cached(monkeypatch):
    """환율은 하루 단위 값이라 매 요청마다 부르지 않는다."""
    seen = _stub_requests(monkeypatch, fx=1300.0, datas=[])
    assert lq.fetch_usd_krw() == 1300.0
    assert lq.fetch_usd_krw() == 1300.0
    assert len(seen["urls"]) == 1
