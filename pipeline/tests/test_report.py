"""
test_report.py — 리포트 그라운딩 단위 테스트 (M5, 키·네트워크 불필요)

payload 빌더와 프롬프트 빌더가 '조회된 실제 데이터만' 근거로 넘기는지 검증한다.
실제 Sonnet 호출/리포트 품질은 키 연동 후 파이프라인 실행으로 확인.

실행:  cd pipeline && python -m pytest tests/test_report.py -v
"""

import json

from pipeline import build_report_payload, build_report_prompt, REPORT_DISCLAIMER

NAME_OF = {1: "삼성전자", 2: "카카오"}

SIGNALS = [{
    "id": 100, "ticker_id": 1, "type": "sentiment_surge_neg", "severity": "high",
    "evidence": {"delta": -0.8, "avg": -0.5, "baseline": 0.3,
                 "news_count": 5, "news_ids": [10, 11]},
}]
DAILY = [
    {"ticker_id": 1, "avg_sentiment": -0.5, "baseline": 0.3, "news_count": 5},
    {"ticker_id": 2, "avg_sentiment": 0.1, "baseline": 0.0, "news_count": 3},
]


# --- payload ---------------------------------------------------------
def test_payload_maps_names_and_spreads_evidence():
    p = build_report_payload(SIGNALS, DAILY, NAME_OF, "2026-07-24")
    assert p["date"] == "2026-07-24"
    s = p["signals"][0]
    assert s["name"] == "삼성전자"
    assert s["severity"] == "high"
    assert s["delta"] == -0.8 and s["news_count"] == 5   # evidence 펼침
    assert p["sentiment"][1]["name"] == "카카오"


def test_payload_empty_inputs_stay_empty():
    p = build_report_payload([], [], NAME_OF, "2026-07-24")
    assert p["signals"] == [] and p["sentiment"] == []


def test_payload_handles_missing_evidence():
    rows = [{"ticker_id": 1, "type": "x", "severity": "low"}]  # evidence 없음
    p = build_report_payload(rows, [], NAME_OF, "2026-07-24")
    assert p["signals"][0]["name"] == "삼성전자"


# --- prompt (그라운딩) -----------------------------------------------
def test_prompt_contains_grounding_rules():
    prompt = build_report_prompt(build_report_payload(SIGNALS, DAILY, NAME_OF, "2026-07-24"))
    assert "데이터에 없는" in prompt
    assert "투자 권유" in prompt


def test_prompt_embeds_exact_payload_json():
    p = build_report_payload(SIGNALS, DAILY, NAME_OF, "2026-07-24")
    prompt = build_report_prompt(p)
    assert json.dumps(p, ensure_ascii=False) in prompt


def test_prompt_has_no_numbers_outside_payload():
    # payload JSON 을 걷어내면 지시문만 남고, 어떤 수치도 남지 않아야 한다(그라운딩 보증)
    p = build_report_payload(SIGNALS, DAILY, NAME_OF, "2026-07-24")
    prompt = build_report_prompt(p)
    without_json = prompt.replace(json.dumps(p, ensure_ascii=False), "")
    assert not any(ch.isdigit() for ch in without_json)


# --- disclaimer (§2) -------------------------------------------------
def test_disclaimer_states_not_investment_advice():
    assert "투자 판단" in REPORT_DISCLAIMER
