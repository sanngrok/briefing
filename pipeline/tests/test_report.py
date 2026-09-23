"""
test_report.py — 리포트 그라운딩 단위 테스트 (M5, 키·네트워크 불필요)

payload 빌더와 프롬프트 빌더가 '조회된 실제 데이터만' 근거로 넘기는지 검증한다.
실제 Sonnet 호출/리포트 품질은 키 연동 후 파이프라인 실행으로 확인.

실행:  cd pipeline && python -m pytest tests/test_report.py -v
"""

import json

from pipeline import (build_report_payload, build_report_prompt, is_valid_report,
                      strip_markdown_fence, REPORT_DISCLAIMER)

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


# --- 본문 형태 검증 (모델이 리포트 대신 메모를 내려보낸 사고 방어) ----------
def test_valid_report_accepts_markdown_body():
    from pipeline import REPORT_HEADING
    body = REPORT_HEADING + "\n\n오늘은 감정 급변 시그널이 없습니다. " + "근거 요약 " * 10
    assert is_valid_report(body)


def test_valid_report_accepts_leading_whitespace():
    from pipeline import REPORT_HEADING
    assert is_valid_report("\n\n  " + REPORT_HEADING + "\n\n" + "본문 내용 " * 20)


def test_valid_report_rejects_self_verification_memo():
    # 2026-09-21 에 실제로 저장됐던 오염 본문(모델의 자기검증 메모, 제목 없이 시작)
    memo = (
        '  * Note about "각 언급 끝에 근거가 된 종목명을 괄호로 표기하라." -> In the '
        'markdown table, having "(삼성전자)" in each cell makes perfect sense.\n'
        "  Let's double check the rules.\n"
    )
    assert not is_valid_report(memo)


def test_valid_report_rejects_empty_and_too_short():
    assert not is_valid_report(None)
    assert not is_valid_report("")
    assert not is_valid_report("   \n  ")
    assert not is_valid_report("## 짧음")          # 제목만 있고 본문이 없음


def test_prompt_pins_heading_and_forbids_memo():
    prompt = build_report_prompt(build_report_payload(SIGNALS, DAILY, NAME_OF, "2026-07-24"))
    from pipeline import REPORT_HEADING
    assert REPORT_HEADING in prompt       # 검증이 확인하는 제목을 프롬프트가 요구한다
    assert "리포트 본문만" in prompt


# --- 코드펜스 방어 ----------------------------------------------------
def test_strip_fence_unwraps_wrapped_body():
    from pipeline import REPORT_HEADING
    body = REPORT_HEADING + "\n\n" + "본문 내용 " * 20
    for fence in ("```markdown", "```md", "```"):
        wrapped = fence + "\n" + body + "\n```"
        assert strip_markdown_fence(wrapped) == body.strip()
        assert is_valid_report(strip_markdown_fence(wrapped))


def test_strip_fence_leaves_plain_body_untouched():
    from pipeline import REPORT_HEADING
    body = REPORT_HEADING + "\n\n본문"
    assert strip_markdown_fence(body) == body
    assert strip_markdown_fence("") == ""
    assert strip_markdown_fence(None) == ""


def test_strip_fence_keeps_inner_code_blocks():
    # 본문 안쪽 코드블록은 건드리지 않는다(여는 줄이 ``` 가 아니므로)
    from pipeline import REPORT_HEADING
    body = REPORT_HEADING + "\n\n```\nsentiment_surge_pos\n```\n" + "설명 " * 20
    assert strip_markdown_fence(body) == body.strip()


# --- 저장 경로: 재시도와 "저장하지 않음" 보장 --------------------------
import pytest

import pipeline as P


class FakeTable:
    """signals/sentiment_daily 는 빈 목록, reports 의 upsert 는 기록만 한다."""

    def __init__(self, store):
        self.store = store

    def select(self, *a):
        return self

    def eq(self, *a):
        return self

    def execute(self):
        return type("R", (), {"data": []})()

    def upsert(self, payload, on_conflict=None):
        self.store.append(payload)
        return self


@pytest.fixture
def report_env(monkeypatch):
    """build_report 를 DB·네트워크 없이 돌린다. (저장된 payload, 잠든 시간) 을 돌려준다."""
    saved, slept = [], []
    monkeypatch.setattr(P, "get_sb",
                        lambda: type("SB", (), {"table": staticmethod(lambda t: FakeTable(saved))})())
    monkeypatch.setattr(P.time, "sleep", lambda s: slept.append(s))
    return saved, slept


class FakeAPIError(Exception):
    """google-genai APIError 처럼 HTTP 상태를 code 로 들고 있는 예외."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


GOOD = "## 오늘의 뉴스 감정 브리핑\n\n오늘은 감정 급변 시그널이 없습니다. " + "근거 " * 30


def _responses(monkeypatch, seq):
    """_generate_text 가 seq 를 순서대로 돌려주거나 던지게 한다."""
    calls = []

    def fake(model, prompt, max_tokens, disable_thinking=False):
        calls.append(disable_thinking)
        item = seq[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(P, "_generate_text", fake)
    return calls


# --- _is_transient ---------------------------------------------------
def test_transient_covers_overload_and_ratelimit():
    # 2026-09-22 실행을 죽인 것이 503 이다
    assert P._is_transient(FakeAPIError(503, "high demand"))
    assert P._is_transient(FakeAPIError(429, "rate limit"))
    assert P._is_transient(FakeAPIError(500, "internal"))


def test_transient_excludes_client_errors_and_our_own():
    assert not P._is_transient(FakeAPIError(400, "bad request"))
    assert not P._is_transient(FakeAPIError(404, "not found"))
    # 잘림·빈 응답은 다시 불러도 같은 문제라 재시도 대상이 아니다(code 가 없다)
    assert not P._is_transient(RuntimeError("출력이 max_output_tokens=6000 에서 잘림"))


# --- 재시도 ------------------------------------------------------------
def test_report_retries_transient_error_then_saves(report_env, monkeypatch):
    saved, slept = report_env
    _responses(monkeypatch, [FakeAPIError(503, "high demand"), GOOD])
    P.build_report([])
    assert len(saved) == 1
    assert saved[0]["body_md"].startswith("## 오늘의 뉴스 감정 브리핑")
    assert slept == [P.REPORT_RETRY_SECONDS]        # 첫 재시도는 기준 대기


def test_report_backoff_is_exponential(report_env, monkeypatch):
    saved, slept = report_env
    _responses(monkeypatch, [FakeAPIError(503, "x"), FakeAPIError(503, "x"), GOOD])
    P.build_report([])
    assert slept == [P.REPORT_RETRY_SECONDS, P.REPORT_RETRY_SECONDS * 2]


def test_report_gives_up_after_all_attempts_without_saving(report_env, monkeypatch):
    saved, slept = report_env
    _responses(monkeypatch, [FakeAPIError(503, "x")] * P.REPORT_ATTEMPTS)
    with pytest.raises(FakeAPIError):
        P.build_report([])
    assert saved == []                              # 전날 리포트를 덮어쓰지 않는다


def test_report_does_not_retry_non_transient(report_env, monkeypatch):
    saved, slept = report_env
    calls = _responses(monkeypatch, [FakeAPIError(400, "bad request"), GOOD])
    with pytest.raises(FakeAPIError):
        P.build_report([])
    assert len(calls) == 1 and slept == [] and saved == []


# --- 형태 불량 재시도 --------------------------------------------------
def test_report_retries_malformed_output_then_saves(report_env, monkeypatch):
    saved, _ = report_env
    calls = _responses(monkeypatch, ["  Let's double check the rules.", GOOD])
    P.build_report([])
    assert len(calls) == 2 and len(saved) == 1


def test_report_never_saves_malformed_output(report_env, monkeypatch):
    saved, _ = report_env
    _responses(monkeypatch, ["  Let's double check the rules."] * P.REPORT_ATTEMPTS)
    with pytest.raises(RuntimeError, match="리포트 형태"):
        P.build_report([])
    assert saved == []


def test_report_always_disables_thinking(report_env, monkeypatch):
    calls = _responses(monkeypatch, [GOOD])
    P.build_report([])
    assert calls == [True]
