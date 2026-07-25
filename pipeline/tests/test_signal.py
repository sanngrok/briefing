"""
test_signal.py — 감정 급변 시그널 판정 로직 단위 테스트 (M4, 필수)

브리핑 §7 규칙을 순수 함수(compute_baseline / classify_severity / decide_signal)
수준에서 경계값까지 고정한다. 키·네트워크·DB 불필요.

실행:  cd pipeline && python -m pytest tests/test_signal.py -v
"""

import pytest

from pipeline import (
    compute_baseline,
    classify_severity,
    decide_signal,
    MIN_NEWS,
    THRESHOLD,
)


# --- compute_baseline ------------------------------------------------
def test_baseline_uses_history_mean():
    assert compute_baseline([0.2, 0.4, 0.6], today_avg=0.9) == pytest.approx(0.4)


def test_baseline_without_history_falls_back_to_today():
    # 초기 며칠: 히스토리 없음 → baseline == today_avg → delta 0 → 미발화(정상)
    assert compute_baseline([], today_avg=0.75) == 0.75


# --- classify_severity (경계값) --------------------------------------
@pytest.mark.parametrize("abs_delta,expected", [
    (0.7, "high"),
    (0.95, "high"),
    (0.69, "mid"),
    (0.5, "mid"),
    (0.499, "low"),
    (0.4, "low"),
    (0.0, "low"),
])
def test_classify_severity_boundaries(abs_delta, expected):
    assert classify_severity(abs_delta) == expected


# --- decide_signal: 발화 방향 ----------------------------------------
def test_signal_fires_positive():
    d = decide_signal(avg=0.6, baseline=0.0, news_count=5)
    assert d["type"] == "sentiment_surge_pos"
    assert d["delta"] == pytest.approx(0.6)
    assert d["severity"] == "mid"


def test_signal_fires_negative():
    d = decide_signal(avg=-0.5, baseline=0.3, news_count=4)
    assert d["type"] == "sentiment_surge_neg"
    assert d["delta"] == pytest.approx(-0.8)
    assert d["severity"] == "high"


# --- decide_signal: 미발화 조건 --------------------------------------
def test_no_signal_when_too_few_news():
    # |delta| 는 충분하지만 기사 수가 MIN_NEWS 미만
    assert decide_signal(avg=0.9, baseline=0.0, news_count=MIN_NEWS - 1) is None


def test_no_signal_when_delta_below_threshold():
    assert decide_signal(avg=0.30, baseline=0.0, news_count=10) is None


def test_no_signal_when_no_history_delta_zero():
    # baseline == avg (히스토리 없음 상황) → delta 0 → 미발화
    assert decide_signal(avg=0.8, baseline=0.8, news_count=10) is None


# --- decide_signal: 경계값(>= 포함) ----------------------------------
def test_signal_fires_at_exact_threshold():
    # |delta| == THRESHOLD(0.40) 는 발화(>=), 심각도 low
    d = decide_signal(avg=THRESHOLD, baseline=0.0, news_count=MIN_NEWS)
    assert d is not None
    assert d["severity"] == "low"


def test_no_signal_just_below_threshold():
    assert decide_signal(avg=THRESHOLD - 0.001, baseline=0.0, news_count=MIN_NEWS) is None


def test_signal_fires_at_exact_min_news():
    assert decide_signal(avg=0.5, baseline=0.0, news_count=MIN_NEWS) is not None


# --- decide_signal: 파라미터 튜닝 주입 --------------------------------
def test_thresholds_are_injectable():
    # 기본값이면 미발화지만, threshold 를 낮추면 발화
    assert decide_signal(avg=0.2, baseline=0.0, news_count=2) is None
    d = decide_signal(avg=0.2, baseline=0.0, news_count=2, min_news=2, threshold=0.15)
    assert d is not None and d["type"] == "sentiment_surge_pos"
