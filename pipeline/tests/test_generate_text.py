"""
test_generate_text.py — LLM 호출 헬퍼 단위 테스트 (키·네트워크 불필요)

_generate_text 가 '쓸 수 없는 응답'을 호출부로 흘리지 않는지 검증한다.
2026-09-21 에 생각(thinking) 도중 max_output_tokens 에서 잘린 텍스트가 그대로
리포트 본문으로 저장된 사고가 있었다 — 그 경로를 여기서 고정한다.

실행:  cd pipeline && python -m pytest tests/test_generate_text.py -v
"""

import pytest

import pipeline


class FakeResp:
    """generate_content 응답 스텁. _generate_text 는 .text/.candidates 만 본다."""

    def __init__(self, text, finish_reason="STOP"):
        self.text = text
        self.candidates = [type("C", (), {"finish_reason": finish_reason})()]


class FakeModels:
    def __init__(self, responses, reject_thinking=False):
        self._responses = list(responses)
        self._reject_thinking = reject_thinking
        self.calls = []            # (thinking 을 껐는지) 기록

    def generate_content(self, *, model, contents, config):
        thinking_off = getattr(config, "thinking_config", None) is not None
        self.calls.append(thinking_off)
        if thinking_off and self._reject_thinking:
            raise RuntimeError("400 INVALID_ARGUMENT: thinking_budget is not supported")
        return self._responses.pop(0)


@pytest.fixture
def fake_ai(monkeypatch):
    """pipeline.get_ai 를 가짜 클라이언트로 바꿔 끼운다."""

    def _install(responses, reject_thinking=False):
        models = FakeModels(responses, reject_thinking)
        client = type("Client", (), {"models": models})()
        monkeypatch.setattr(pipeline, "get_ai", lambda: client)
        return models

    return _install


# --- 정상 응답 -------------------------------------------------------
def test_returns_text_on_normal_finish(fake_ai):
    fake_ai([FakeResp("리포트 본문")])
    assert pipeline._generate_text("m", "p", max_tokens=100) == "리포트 본문"


def test_disable_thinking_passes_thinking_config(fake_ai):
    models = fake_ai([FakeResp("본문")])
    pipeline._generate_text("m", "p", max_tokens=100, disable_thinking=True)
    assert models.calls == [True]


def test_thinking_left_on_by_default(fake_ai):
    models = fake_ai([FakeResp("본문")])
    pipeline._generate_text("m", "p", max_tokens=100)
    assert models.calls == [False]


# --- 잘린 응답은 저장되면 안 된다 ------------------------------------
def test_raises_on_max_tokens_truncation(fake_ai):
    # 생각 도중 한도에 걸려 끊긴 텍스트. 예전에는 이 값이 그대로 리포트가 됐다.
    fake_ai([FakeResp("  Let's double check the rules. 기준선은 0.0019047",
                      finish_reason="MAX_TOKENS")])
    with pytest.raises(RuntimeError, match="잘림"):
        pipeline._generate_text("m", "p", max_tokens=100)


def test_raises_on_empty_text(fake_ai):
    fake_ai([FakeResp("   ", finish_reason="MAX_TOKENS")])
    with pytest.raises(RuntimeError, match="빈 응답"):
        pipeline._generate_text("m", "p", max_tokens=100)


def test_finish_reason_enum_name_is_read(fake_ai):
    # SDK 는 문자열이 아니라 enum 을 주므로 .name 으로도 읽혀야 한다
    enum_like = type("FinishReason", (), {"name": "MAX_TOKENS"})()
    fake_ai([FakeResp("잘린 본문", finish_reason=enum_like)])
    with pytest.raises(RuntimeError, match="잘림"):
        pipeline._generate_text("m", "p", max_tokens=100)


# --- thinking_config 미지원 모델(flash-lite) 폴백 ---------------------
def test_falls_back_when_model_rejects_thinking_config(fake_ai):
    models = fake_ai([FakeResp("본문")], reject_thinking=True)
    assert pipeline._generate_text("m", "p", max_tokens=100,
                                   disable_thinking=True) == "본문"
    assert models.calls == [True, False]     # 끄고 시도 -> 거부 -> 설정 없이 재시도


def test_other_errors_are_not_retried(fake_ai):
    models = fake_ai([FakeResp("본문")])

    def boom(*, model, contents, config):
        models.calls.append(getattr(config, "thinking_config", None) is not None)
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    models.generate_content = boom
    with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
        pipeline._generate_text("m", "p", max_tokens=100, disable_thinking=True)
    assert models.calls == [True]            # 재시도 없음(레이트리밋은 폴백 대상 아님)
