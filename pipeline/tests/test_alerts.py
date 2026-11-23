"""
test_alerts.py — 목표가·손절가 판정과 메일 블록 단위 테스트 (키·네트워크 불필요)

실행:  cd pipeline && python -m pytest tests/test_alerts.py -v
"""

from datetime import date

import pytest

from pipeline import (alert_prices, briefing_window, build_briefing, evaluate_alert,
                      evaluate_alerts, fmt_alert_price, parse_alerts, parse_holdings,
                      render_html, render_text)

TODAY = date(2026, 11, 24)
WINDOW = briefing_window(TODAY)
TICKERS = [{"id": 1, "symbol": "005930", "name": "삼성전자"}]


# ---- 시크릿 한 줄 읽기 ---------------------------------------------------
def test_parse_holdings_ignores_alert_suffix():
    raw = "005930:stop=170000:target=250000, tsla ,PLTR:target=200"
    assert parse_holdings(raw) == ["005930", "TSLA", "PLTR"]


def test_parse_alerts_reads_values_and_skips_bad_ones():
    raw = ("005930:stop=170000:target=250000,TSLA,PLTR:target=200.5,"
           "BAD:stop=10:target=5,X:target=abc,Y:foo=1,Z:target=-3")
    assert parse_alerts(raw) == {
        "005930": {"stop": 170000.0, "target": 250000.0},
        "PLTR": {"target": 200.5},
    }
    assert parse_alerts("") == {}
    assert parse_alerts(None) == {}


# ---- 판정 (frontend evaluateAlert 와 같은 경계) ----------------------------
@pytest.mark.parametrize("price,expected", [
    (250000, "target_hit"), (260000, "target_hit"),
    (170000, "stop_hit"), (150000, "stop_hit"),
    (244000, "near_target"), (175000, "near_stop"),
    (200000, None),
])
def test_evaluate_alert(price, expected):
    assert evaluate_alert(price, target=250000, stop=170000) == expected


def test_evaluate_alert_one_side_and_closer_wins():
    assert evaluate_alert(100, target=102) == "near_target"
    assert evaluate_alert(100, stop=100) == "stop_hit"
    assert evaluate_alert(100, target=101, stop=98) == "near_target"
    assert evaluate_alert(100, target=102, stop=99.5) == "near_stop"


# ---- 시세 → 종목 통화 -----------------------------------------------------
def test_alert_prices_converts_world_quotes_back_to_usd():
    payload = {"fx_usdkrw": 1400, "quotes": [
        {"symbol": "005930", "name": "삼성전자", "close": 180000},
        {"symbol": "PLTR", "name": "팔란티어", "close": 280000},
        {"symbol": "TSLA", "name": "테슬라", "close": None},
    ]}
    assert alert_prices(payload) == {"005930": (180000.0, "삼성전자"),
                                     "PLTR": (200.0, "팔란티어")}


def test_alert_prices_without_fx_drops_world_quotes():
    payload = {"quotes": [{"symbol": "PLTR", "close": 280000}]}
    assert alert_prices(payload) == {}


def test_fmt_alert_price():
    assert fmt_alert_price(251000.4, "005930") == "251,000원"
    assert fmt_alert_price(201.3, "PLTR") == "$201.30"


def test_evaluate_alerts_keeps_only_hits_and_nears_urgent_first():
    alerts = {"005930": {"target": 250000}, "PLTR": {"target": 199},
              "TSLA": {"stop": 420}, "NVDA": {"target": 1}}   # NVDA 는 시세 없음
    prices = {"005930": (180000.0, "삼성전자"), "PLTR": (200.0, "팔란티어"),
              "TSLA": (428.6, "테슬라")}
    items = evaluate_alerts(alerts, prices)
    assert [(i["symbol"], i["status"]) for i in items] == [("PLTR", "target_hit"),
                                                           ("TSLA", "near_stop")]


# ---- 메일 블록 -----------------------------------------------------------
HIT = {"symbol": "005930", "name": "삼성전자", "status": "stop_hit",
       "price": 168000.0, "target": 250000.0, "stop": 170000.0}
NEAR = {"symbol": "PLTR", "name": "팔란티어", "status": "near_target",
        "price": 195.0, "target": 200.0, "stop": None}


def test_briefing_puts_alert_block_first_and_tags_subject():
    b = build_briefing(TODAY, WINDOW, TICKERS, [], [], ["005930"], alerts=[HIT, NEAR])
    heading_at = b["lines"].index(("heading", "목표가 · 손절가"))
    assert heading_at < b["lines"].index(("heading", "내 보유 종목"))
    assert ("alert_down", "삼성전자 손절가 도달 — 현재 168,000원 (손절 170,000원)") in b["lines"]
    assert ("item", "팔란티어 목표가까지 +2.6% — 현재 $195.00 (목표 $200.00)") in b["lines"]
    assert b["subject"].startswith("[손절가 도달] ")


def test_briefing_near_only_does_not_tag_subject():
    b = build_briefing(TODAY, WINDOW, TICKERS, [], [], alerts=[NEAR])
    assert b["subject"].startswith("☀️")


def test_briefing_without_alerts_has_no_block():
    b = build_briefing(TODAY, WINDOW, TICKERS, [], [])
    assert ("heading", "목표가 · 손절가") not in b["lines"]


def test_briefing_alert_note_when_prices_failed():
    b = build_briefing(TODAY, WINDOW, TICKERS, [], [], alert_note="시세를 받지 못했어요.")
    assert ("text", "시세를 받지 못했어요.") in b["lines"]


def test_render_alert_lines():
    b = build_briefing(TODAY, WINDOW, TICKERS, [], [], alerts=[HIT])
    assert "▼ 삼성전자 손절가 도달" in render_text(b)
    html_body = render_html(b)
    assert "▼ 삼성전자 손절가 도달" in html_body
    assert "color:#2563eb;font-weight:700" in html_body
