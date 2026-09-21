"""
test_toss_sync.py — 토스증권 동기화 순수 함수 테스트 (키·네트워크 불필요)

실행:  python -m pytest tools/tests -v   (repo 루트에서)

픽스처는 토스증권 Open API 1.1.1 의 HoldingsOverview/HoldingsItem 스키마를 따른다
(수량·단가가 decimal '문자열'인 점이 핵심).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toss_sync import (  # noqa: E402
    build_export,
    mask_account_no,
    pick_account,
    to_holding,
    to_holdings,
)


def item(**over):
    base = {
        "symbol": "005930",
        "name": "삼성전자",
        "marketCountry": "KR",
        "currency": "KRW",
        "quantity": "100",
        "lastPrice": "72000",
        "averagePurchasePrice": "65000",
        "dailyProfitLoss": {"rate": "0.0181"},
    }
    base.update(over)
    return base


def usd_item(**over):
    """실측(2026-09-21 run) 기반 — 해외 종목은 평단·현재가가 USD 로 온다."""
    base = {
        "symbol": "PLTR",
        "name": "팔란티어",
        "marketCountry": "US",
        "currency": "USD",
        "quantity": "17",
        "lastPrice": "177.78",
        "averagePurchasePrice": "176.84",
        "dailyProfitLoss": {"rate": "0.0007"},
    }
    base.update(over)
    return base


# --- to_holding -------------------------------------------------------

def test_to_holding_parses_decimal_strings():
    h = to_holding(item())
    assert h["id"] == "toss-005930"
    assert h["symbol"] == "005930"
    assert h["name"] == "삼성전자"
    assert h["quantity"] == 100.0
    assert h["avgPrice"] == 65000.0


def test_to_holding_includes_imported_price_snapshot():
    """lastPrice/dailyProfitLoss.rate 는 워치리스트에 시세가 없을 때의 폴백으로 같이 내보낸다."""
    h = to_holding(item())
    assert h["importedClose"] == 72000.0
    assert h["importedChangePct"] == pytest.approx(1.81)


def test_to_holding_omits_imported_fields_when_missing():
    h = to_holding(item(lastPrice=None, dailyProfitLoss={}))
    assert "importedClose" not in h
    assert "importedChangePct" not in h


def test_to_holding_keeps_fractional_quantity():
    """해외 주식 소수점 매수 — 버림/반올림하면 평가금액이 틀어진다."""
    assert to_holding(item(quantity="1.53"))["quantity"] == 1.53


def test_to_holding_falls_back_to_symbol_when_name_missing():
    assert to_holding(item(name=""))["name"] == "005930"


def test_to_holding_id_is_stable_across_syncs():
    """id 가 종목코드 기반이라 재동기화해도 같은 종목이 같은 id 를 갖는다."""
    assert to_holding(item())["id"] == to_holding(item(quantity="7"))["id"]


def test_to_holding_converts_usd_with_fx_rate():
    """해외 종목은 fx_rate(원/달러)를 주면 평단·현재가를 원화로 환산한다."""
    h = to_holding(usd_item(), fx_rate=1400.0)
    assert h["avgPrice"] == pytest.approx(176.84 * 1400.0)
    assert h["importedClose"] == pytest.approx(177.78 * 1400.0)
    assert h["importedChangePct"] == pytest.approx(0.07)


def test_to_holding_leaves_usd_unconverted_without_fx_rate():
    """fx_rate 를 안 주면 원래 통화값 그대로 둔다 — 통화 혼합 방지는 to_holdings 의 몫."""
    h = to_holding(usd_item())
    assert h["avgPrice"] == pytest.approx(176.84)
    assert h["importedClose"] == pytest.approx(177.78)


# --- to_holdings ------------------------------------------------------

def test_to_holdings_excludes_us_by_default():
    holdings, skipped = to_holdings({"items": [
        item(),
        item(symbol="AAPL", name="Apple", marketCountry="US", currency="USD",
             quantity="3", averagePurchasePrice="180.5"),
    ]})
    assert [h["symbol"] for h in holdings] == ["005930"]
    assert skipped == ["Apple"]


def test_to_holdings_include_us_requires_fx_rate():
    """include_us=True 여도 환율을 못 구했으면(fx_rate=None) 통화 혼합을 막기 위해 여전히 제외한다."""
    holdings, skipped = to_holdings({"items": [usd_item()]}, include_us=True, fx_rate=None)
    assert holdings == []
    assert skipped == ["팔란티어"]


def test_to_holdings_include_us_converts_with_fx_rate():
    holdings, skipped = to_holdings(
        {"items": [item(), usd_item()]}, include_us=True, fx_rate=1400.0,
    )
    assert [h["symbol"] for h in holdings] == ["005930", "PLTR"]
    assert skipped == []
    pltr = holdings[1]
    assert pltr["avgPrice"] == pytest.approx(176.84 * 1400.0)
    assert pltr["importedClose"] == pytest.approx(177.78 * 1400.0)


def test_to_holdings_drops_zero_quantity_and_blank_symbol():
    holdings, _ = to_holdings({"items": [
        item(quantity="0"),                  # 전량 매도 잔재
        item(symbol="", name="이름만"),       # 종목코드 없음
        item(symbol="000660", name="SK하이닉스"),
    ]})
    assert [h["symbol"] for h in holdings] == ["000660"]


def test_to_holdings_handles_empty_and_missing_items():
    assert to_holdings({"items": []}) == ([], [])
    assert to_holdings({}) == ([], [])
    assert to_holdings(None) == ([], [])


# --- build_export -----------------------------------------------------

def test_build_export_matches_dashboard_import_format():
    """프론트 parseHoldings 가 읽는 {version, holdings} 형태여야 한다."""
    out = build_export([to_holding(item())],
                       now=datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc))
    assert out["version"] == 1
    assert out["exportedAt"] == "2026-09-21T07:00:00Z"
    assert out["holdings"][0]["symbol"] == "005930"


# --- pick_account -----------------------------------------------------

ACCOUNTS = [
    {"accountNo": "12345678901", "accountSeq": 1, "accountType": "BROKERAGE"},
    {"accountNo": "98765432109", "accountSeq": 2, "accountType": "PENSION_SAVINGS"},
]


def test_pick_account_prefers_brokerage():
    assert pick_account(ACCOUNTS)["accountSeq"] == 1


def test_pick_account_by_account_no():
    assert pick_account(ACCOUNTS, "98765432109")["accountSeq"] == 2


def test_pick_account_raises_on_ambiguous_brokerage():
    """종합매매가 둘이면 말없이 하나를 고르지 않는다."""
    two = ACCOUNTS + [{"accountNo": "55555555555", "accountSeq": 3, "accountType": "BROKERAGE"}]
    with pytest.raises(LookupError, match="여러 개"):
        pick_account(two)


def test_pick_account_raises_on_unknown_and_empty():
    with pytest.raises(LookupError, match="찾지 못"):
        pick_account(ACCOUNTS, "00000000000")
    with pytest.raises(LookupError, match="계좌가 없습니다"):
        pick_account([])


# --- mask_account_no --------------------------------------------------

def test_mask_account_no_keeps_only_edges():
    assert mask_account_no("12345678901") == "1234***8901"
    assert mask_account_no("1234") == "****"
