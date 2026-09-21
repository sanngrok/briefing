"""
test_seed_tickers.py — 워치리스트 시드 병합 로직 단위 테스트

내 보유 종목(portfolio.json)을 시드 목록에 합치는 규칙을 고정한다.
키·네트워크·DB 불필요.

실행:  cd pipeline && python -m pytest tests/test_seed_tickers.py -v
"""

import json

from seed_tickers import (
    find_portfolio,
    load_portfolio,
    merge_portfolio,
)

SEED = [
    {"symbol": "005930", "name": "삼성전자", "aliases": ["삼성전자", "Samsung Electronics"]},
    {"symbol": "000270", "name": "기아", "aliases": ["기아차", "기아 자동차", "Kia"]},
]


# --- merge_portfolio -------------------------------------------------

def test_merge_adds_new_holding_with_name_as_search_term():
    merged, added, skipped = merge_portfolio(
        SEED, [{"symbol": "035420", "name": "NAVER"}])
    assert [t["symbol"] for t in merged] == ["005930", "000270", "035420"]
    assert added == [{"symbol": "035420", "name": "NAVER", "aliases": ["NAVER"]}]
    assert skipped == []


def test_merge_keeps_seed_entry_for_already_listed_holding():
    """보유 중이어도 시드에 있으면 시드의 검증된 검색어를 그대로 쓴다.

    '기아'를 그대로 검색어로 덮어쓰면 야구단 기사가 섞여 감정이 오염된다.
    """
    merged, added, _ = merge_portfolio(SEED, [{"symbol": "000270", "name": "기아"}])
    kia = next(t for t in merged if t["symbol"] == "000270")
    assert kia["aliases"][0] == "기아차"   # 종목명이 아니라 시드 검색어
    assert added == []
    assert len(merged) == len(SEED)


def test_merge_applies_alias_override():
    merged, added, _ = merge_portfolio(
        SEED, [{"symbol": "035720", "name": "카카오"}],
        overrides={"035720": ["카카오 주가", "Kakao"]})
    assert added[0]["aliases"] == ["카카오 주가", "Kakao"]


def test_merge_skips_non_kr_symbols():
    """해외 티커는 pykrx 가 시세를 못 가져와 파이프라인이 헛돈다."""
    merged, added, skipped = merge_portfolio(
        SEED, [{"symbol": "AAPL", "name": "Apple"},
               {"symbol": "12345", "name": "다섯자리"},
               {"symbol": "0123456", "name": "일곱자리"},
               {"symbol": "035420", "name": "NAVER"}])
    assert [t["symbol"] for t in added] == ["035420"]
    assert [h["symbol"] for h in skipped] == ["AAPL", "12345", "0123456"]


def test_merge_dedups_repeated_holding():
    _, added, _ = merge_portfolio(
        SEED, [{"symbol": "035420", "name": "NAVER"},
               {"symbol": "035420", "name": "네이버"}])
    assert len(added) == 1


def test_merge_does_not_mutate_seed():
    before = json.dumps(SEED, ensure_ascii=False)
    merge_portfolio(SEED, [{"symbol": "035420", "name": "NAVER"}])
    assert json.dumps(SEED, ensure_ascii=False) == before


def test_merge_with_no_holdings_returns_seed():
    for holdings in ([], None):
        merged, added, skipped = merge_portfolio(SEED, holdings)
        assert merged == SEED and added == [] and skipped == []


# --- load_portfolio --------------------------------------------------

def test_load_portfolio_reads_export_format(tmp_path):
    f = tmp_path / "portfolio.json"
    f.write_text(json.dumps({"version": 1, "holdings": [
        {"id": "toss-005930", "symbol": "005930", "name": "삼성전자",
         "quantity": 10, "avgPrice": 65000},
    ]}, ensure_ascii=False), encoding="utf-8")
    assert load_portfolio(str(f)) == [{"symbol": "005930", "name": "삼성전자"}]


def test_load_portfolio_accepts_bare_array(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([{"symbol": "005930", "name": "삼성전자"}]), encoding="utf-8")
    assert load_portfolio(str(f))[0]["symbol"] == "005930"


def test_load_portfolio_skips_broken_entries(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"holdings": [
        {"symbol": "", "name": "코드없음"},
        "garbage",
        {"symbol": "005930"},                 # 이름 없음 -> 코드로 대체
    ]}, ensure_ascii=False), encoding="utf-8")
    assert load_portfolio(str(f)) == [{"symbol": "005930", "name": "005930"}]


def test_load_portfolio_survives_missing_or_invalid_file(tmp_path):
    assert load_portfolio(str(tmp_path / "없음.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_portfolio(str(bad)) == []


# --- find_portfolio --------------------------------------------------

def test_find_portfolio_returns_first_existing(tmp_path):
    second = tmp_path / "b.json"
    second.write_text("[]", encoding="utf-8")
    assert find_portfolio((str(tmp_path / "a.json"), str(second))) == str(second)


def test_find_portfolio_returns_none_when_absent(tmp_path):
    assert find_portfolio((str(tmp_path / "a.json"),)) is None
