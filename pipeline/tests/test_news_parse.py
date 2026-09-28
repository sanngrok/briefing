"""
test_news_parse.py — 뉴스/감정 파싱 단위 테스트 (M3, 키·네트워크 불필요)

순수 함수 parse_news_item / parse_sentiment / _hash 만 검증한다.
실행:  cd pipeline && python -m pytest tests/ -v
"""

import pytest

from pipeline import (build_sentiment_prompt, parse_news_item, parse_sentiment,
                      SENTIMENT_SCALE, _hash)


# 네이버 뉴스 검색 API 응답 item 샘플 (실제 형태: HTML 태그·엔티티 포함)
NAVER_ITEM = {
    "title": "삼성전자, 2분기 <b>깜짝 실적</b> &quot;반도체 회복&quot;",
    "originallink": "https://news.example.com/article/123",
    "link": "https://n.news.naver.com/mnews/456",
    "description": "삼성전자가 <b>반도체</b> 업황 회복에 힘입어 실적이 개선 &amp; 반등했다.",
    "pubDate": "Fri, 24 Jul 2026 15:30:00 +0900",
}


# --- parse_news_item -------------------------------------------------
def test_parse_news_item_basic():
    row = parse_news_item(1, NAVER_ITEM)
    assert row["ticker_id"] == 1
    assert row["source"] == "naver"
    # HTML 태그 제거 + 엔티티 복원
    assert row["title"] == '삼성전자, 2분기 깜짝 실적 "반도체 회복"'
    assert "<b>" not in row["_desc"] and "&amp;" not in row["_desc"]
    assert "실적이 개선 & 반등했다" in row["_desc"]
    # 원문 링크(originallink) 우선
    assert row["url"] == "https://news.example.com/article/123"
    assert row["url_hash"] == _hash("https://news.example.com/article/123")
    # pubDate → ISO8601
    assert row["published_at"].startswith("2026-07-24T15:30:00")


def test_parse_news_item_falls_back_to_link():
    item = dict(NAVER_ITEM)
    item.pop("originallink")
    row = parse_news_item(1, item)
    assert row["url"] == item["link"]


def test_parse_news_item_no_url_returns_none():
    assert parse_news_item(1, {"title": "url 없음"}) is None


def test_parse_news_item_bad_pubdate_is_none():
    item = dict(NAVER_ITEM)
    item["pubDate"] = "not-a-date"
    assert parse_news_item(1, item)["published_at"] is None


def test_hash_is_deterministic_and_unique():
    assert _hash("https://a.com") == _hash("https://a.com")
    assert _hash("https://a.com") != _hash("https://b.com")


# --- parse_sentiment -------------------------------------------------
def test_parse_sentiment_clean_json():
    d = parse_sentiment('{"sentiment": 0.7, "tags": ["실적"], "summary": "호실적"}')
    assert d == {"sentiment": 0.7, "tags": ["실적"], "summary": "호실적"}


def test_parse_sentiment_strips_code_fence():
    text = '```json\n{"sentiment": -0.5, "tags": [], "summary": "우려"}\n```'
    assert parse_sentiment(text)["sentiment"] == -0.5


def test_parse_sentiment_clamps_out_of_range():
    assert parse_sentiment('{"sentiment": 5}')["sentiment"] == 1.0
    assert parse_sentiment('{"sentiment": -9}')["sentiment"] == -1.0


def test_parse_sentiment_coerces_bad_tags():
    assert parse_sentiment('{"sentiment": 0, "tags": "실적"}')["tags"] == []


def test_parse_sentiment_defaults_when_missing_keys():
    d = parse_sentiment("{}")
    assert d == {"sentiment": 0.0, "tags": [], "summary": ""}


def test_parse_sentiment_invalid_raises():
    with pytest.raises(Exception):
        parse_sentiment("이건 JSON 이 아님")


# --- 감정 프롬프트 기준표 (눈금이 몇 개 값으로 몰리던 문제) ----------------
def test_prompt_embeds_title_and_description():
    prompt = build_sentiment_prompt("삼성전자 깜짝 실적", "반도체 업황 회복")
    assert "삼성전자 깜짝 실적" in prompt
    assert "반도체 업황 회복" in prompt


def test_prompt_carries_the_scale():
    """기준표가 빠지면 모델이 0.8/0.5 로 몰린다 — 이 변경의 핵심이라 고정한다."""
    prompt = build_sentiment_prompt("t", "d")
    assert SENTIMENT_SCALE in prompt
    assert "0.05 단위" in prompt
    assert "몇 개 값으로 몰지 마라" in prompt


def test_scale_anchors_span_both_directions():
    """양 끝과 중간이 모두 정의돼 있어야 모델이 중간값을 쓸 근거가 생긴다."""
    for anchor in ("+0.9~1.0", "+0.6~0.8", "+0.3~0.5", "0.0",
                   "-0.3~-0.5", "-0.6~-0.8", "-0.9~-1.0"):
        assert anchor in SENTIMENT_SCALE, anchor


def test_prompt_still_demands_json_only():
    """응답 파서(parse_sentiment)가 JSON 을 기대하므로 이 지시는 유지돼야 한다."""
    prompt = build_sentiment_prompt("t", "d")
    assert "JSON 만 출력하라" in prompt
    assert '"sentiment"' in prompt and '"tags"' in prompt and '"summary"' in prompt


def test_prompt_handles_empty_description():
    prompt = build_sentiment_prompt("제목만 있는 기사", "")
    assert "제목만 있는 기사" in prompt
