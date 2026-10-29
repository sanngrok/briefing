"""
test_notify.py — 아침 브리핑 메일 본문 단위 테스트 (키·네트워크 불필요)

실행:  cd pipeline && python -m pytest tests/test_notify.py -v
"""

from datetime import date

from pipeline import (build_briefing, briefing_window, parse_holdings, pick_headlines,
                      render_html, render_text, DASHBOARD_URL)

TODAY = date(2026, 10, 29)   # 목요일
WINDOW = briefing_window(TODAY)

TICKERS = [
    {"id": 1, "symbol": "005930", "name": "삼성전자"},
    {"id": 2, "symbol": "000660", "name": "SK하이닉스"},
    {"id": 3, "symbol": "055550", "name": "신한지주"},
    {"id": 4, "symbol": "035720", "name": "카카오"},
]


def sig(tid, stype, severity, delta, news_ids=()):
    return {"ticker_id": tid, "type": stype, "severity": severity,
            "evidence": {"delta": delta, "news_ids": list(news_ids)}}


SIGNALS = [
    sig(3, "sentiment_surge_neg", "low", -0.31),
    sig(2, "sentiment_surge_pos", "high", 0.751, news_ids=[10, 11, 12]),
]
DAILY = [
    {"ticker_id": 1, "avg_sentiment": 0.167, "baseline": 0.103, "news_count": 9},
    {"ticker_id": 2, "avg_sentiment": 0.955, "baseline": 0.204, "news_count": 10},
]
NEWS = [
    {"id": 10, "ticker_id": 2, "title": "HBM 수주 확대", "sentiment": 0.9},
    {"id": 11, "ticker_id": 2, "title": "실적 서프라이즈", "sentiment": 1.0},
    {"id": 12, "ticker_id": 2, "title": "규제 우려", "sentiment": -0.4},
]


# ---- parse_holdings ----------------------------------------------------

def test_parse_holdings_trims_uppercases_and_dedups():
    assert parse_holdings(" 005930, aapl ,,005930,") == ["005930", "AAPL"]


def test_parse_holdings_empty():
    assert parse_holdings("") == []
    assert parse_holdings(None) == []


# ---- pick_headlines ----------------------------------------------------

def test_pick_headlines_positive_takes_highest():
    assert pick_headlines(NEWS, "sentiment_surge_pos") == ["실적 서프라이즈", "HBM 수주 확대"]


def test_pick_headlines_negative_takes_lowest():
    assert pick_headlines(NEWS, "sentiment_surge_neg", n=1) == ["규제 우려"]


def test_pick_headlines_skips_unscored():
    rows = [{"title": "미채점", "sentiment": None}, {"title": "채점", "sentiment": 0.1}]
    assert pick_headlines(rows, "sentiment_surge_pos") == ["채점"]


# ---- build_briefing ----------------------------------------------------

def test_subject_counts_all_signals():
    b = build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY)
    assert b["subject"] == "☀️ 10/29(목) 아침 브리핑 · 시그널 2건"


def test_subject_counts_held_signals():
    b = build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY, ["000660"])
    assert b["subject"] == "☀️ 10/29(목) 아침 브리핑 · 시그널 2건 (보유 1)"


def test_header_has_date_weekday_and_window():
    b = build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY)
    assert b["lines"][:2] == [("title", "10/29(목) 아침 브리핑"),
                              ("sub", "뉴스 구간 10/28 07:00 ~ 10/29 07:00")]


def test_without_holdings_has_no_holdings_block():
    b = build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY)
    assert ("heading", "내 보유 종목") not in b["lines"]


def test_all_signals_sorted_by_severity_then_delta():
    lines = build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY)["lines"]
    i = lines.index(("heading", "전체 시그널 2건"))
    assert lines[i + 1:i + 3] == [("pos", "SK하이닉스 긍정 급변 · high (+0.75)"),
                                  ("neg", "신한지주 부정 급변 · low (-0.31)")]


def test_no_signals_says_so():
    b = build_briefing(TODAY, WINDOW, TICKERS, [], DAILY)
    assert ("text", "감정 급변 시그널이 없습니다.") in b["lines"]
    assert b["subject"].endswith("시그널 0건")


def test_holdings_block_signal_first_with_headlines():
    holdings = ["005930", "035720", "000660", "AAPL"]
    lines = build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY, holdings, NEWS)["lines"]
    i = lines.index(("heading", "내 보유 종목"))
    assert lines[i + 1:i + 7] == [
        ("pos", "SK하이닉스 긍정 급변 · high (+0.75)"),   # 시그널 걸린 종목이 맨 위
        ("headline", "실적 서프라이즈"),
        ("headline", "HBM 수주 확대"),
        ("item", "삼성전자 감정 +0.17 (뉴스 9건, 기준 +0.10)"),
        ("item", "카카오 새 뉴스 없음"),
        ("item", "AAPL 워치리스트 밖 (데이터 없음)"),
    ]


def test_holding_without_baseline():
    daily = [{"ticker_id": 1, "avg_sentiment": -0.2, "baseline": None, "news_count": 1}]
    lines = build_briefing(TODAY, WINDOW, TICKERS, [], daily, ["005930"])["lines"]
    assert ("item", "삼성전자 감정 -0.20 (뉴스 1건)") in lines


# ---- render ------------------------------------------------------------

def test_render_text_has_markers_dashboard_and_disclaimer():
    text = render_text(build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY))
    assert "🔺 SK하이닉스 긍정 급변 · high (+0.75)" in text
    assert "🔻 신한지주 부정 급변 · low (-0.31)" in text
    assert DASHBOARD_URL in text
    assert text.endswith("투자 판단의 근거가 아닙니다.")


def test_render_html_escapes_headlines():
    news = [{"id": 10, "ticker_id": 2, "title": "<b>속보</b> & 단독", "sentiment": 0.9}]
    out = render_html(build_briefing(TODAY, WINDOW, TICKERS, SIGNALS, DAILY, ["000660"], news))
    assert "&lt;b&gt;속보&lt;/b&gt; &amp; 단독" in out
    assert "<b>속보" not in out
    assert f'href="{DASHBOARD_URL}"' in out
