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
        self.configs = []          # 넘어온 config 원본(타임아웃 검증용)

    def generate_content(self, *, model, contents, config):
        thinking_off = getattr(config, "thinking_config", None) is not None
        self.calls.append(thinking_off)
        self.configs.append(config)
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


# --- 타임아웃 -------------------------------------------------------
# google-genai 의 HttpOptions.timeout 기본값은 None(무제한)이다. 값을 실어
# 보내지 않으면 응답이 안 올 때 영원히 매달린다 — 2026-09-21, 09-28 실행이
# 그렇게 러너 한도 6시간을 태웠다. 호출마다 실제로 실리는지 고정한다.
def test_passes_timeout_to_call(fake_ai):
    models = fake_ai([FakeResp("본문")])
    pipeline._generate_text("m", "p", max_tokens=100, timeout_ms=12_345)
    assert models.configs[0].http_options.timeout == 12_345


def test_defaults_to_report_timeout(fake_ai):
    models = fake_ai([FakeResp("본문")])
    pipeline._generate_text("m", "p", max_tokens=100)
    assert models.configs[0].http_options.timeout == pipeline.REPORT_TIMEOUT_MS


def test_thinking_retry_keeps_timeout(fake_ai):
    """thinking 거부로 다시 부를 때도 타임아웃이 빠지면 안 된다."""
    models = fake_ai([FakeResp("본문")], reject_thinking=True)
    pipeline._generate_text("m", "p", max_tokens=100,
                            disable_thinking=True, timeout_ms=9_000)
    assert [c.http_options.timeout for c in models.configs] == [9_000, 9_000]


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


# --- 감정 분석 경로: 일시적 오류 재시도 (503 이 중립 0.0 으로 새지 않게) ----
class FakeAPIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _enrich_env(monkeypatch):
    """enrich_news 를 DB·네트워크 없이 돌린다. (upsert된 행, 잠든 시간)."""
    saved, slept = [], []

    class T:
        def upsert(self, rows, on_conflict=None):
            saved.extend(rows); return self
        def execute(self): return type("R", (), {"data": []})()

    monkeypatch.setattr(pipeline, "get_sb",
                        lambda: type("SB", (), {"table": staticmethod(lambda n: T())})())
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: slept.append(s))
    return saved, slept


ITEM = {"ticker_id": 1, "url_hash": "h", "title": "제목", "url": "u",
        "source": "naver", "published_at": "2026-09-24T00:00:00+09:00", "_desc": "요약"}
GOOD_JSON = '{"sentiment": 0.35, "tags": ["실적"], "summary": "한 줄"}'


def test_sentiment_retries_transient_then_succeeds(monkeypatch):
    saved, slept = _enrich_env(monkeypatch)
    calls = []

    def fake(model, prompt, max_tokens, disable_thinking=False, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise FakeAPIError(503, "high demand")
        return GOOD_JSON

    monkeypatch.setattr(pipeline, "_generate_text", fake)
    pipeline.enrich_news([dict(ITEM)])
    assert saved[0]["sentiment"] == 0.35          # 중립으로 떨어지지 않았다
    assert pipeline.SENTIMENT_RETRY_SECONDS in slept


def test_sentiment_falls_back_to_neutral_after_attempts(monkeypatch):
    saved, _ = _enrich_env(monkeypatch)
    monkeypatch.setattr(pipeline, "_generate_text",
                        lambda *a, **k: (_ for _ in ()).throw(FakeAPIError(503, "x")))
    pipeline.enrich_news([dict(ITEM)])
    assert saved[0]["sentiment"] == 0.0           # 다 실패하면 기존대로 중립
    assert saved[0]["summary"] == "제목"


def test_sentiment_does_not_retry_non_transient(monkeypatch):
    saved, slept = _enrich_env(monkeypatch)
    calls = []

    def fake(*a, **k):
        calls.append(1)
        raise ValueError("파싱 불가")

    monkeypatch.setattr(pipeline, "_generate_text", fake)
    pipeline.enrich_news([dict(ITEM)])
    assert len(calls) == 1 and pipeline.SENTIMENT_RETRY_SECONDS not in slept
