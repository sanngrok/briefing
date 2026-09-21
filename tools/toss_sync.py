"""
toss_sync.py — 토스증권 Open API 로 실제 보유 종목을 읽어 대시보드용 JSON 으로 저장

  내 PC ──(토스증권 Open API)──> portfolio.json ──('가져오기')──> 대시보드(브라우저)

이 스크립트는 **내 PC 에서만** 돌린다. Client ID/Secret 은 주문까지 나가는 자격증명이라
서버(Render/Vercel)·GitHub Actions 어디에도 올리지 않는다. 산출물(portfolio.json)도
보유 정보이므로 .gitignore 대상이다.

읽기 전용: GET /oauth2/token, GET /api/v1/accounts, GET /api/v1/holdings 만 호출한다.
주문(create/modify/cancel) 엔드포인트는 이 파일 어디에서도 부르지 않는다.
--include-us 를 줄 때만 당일 USD/KRW 환율을 구하려고 공개 환율 API(frankfurter.app)를
추가로 호출한다 — 인증 정보는 보내지 않는다.

사용법
    pip install -r tools/requirements.txt
    # .env 에 TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 입력 (.env 는 .gitignore)
    python tools/toss_sync.py                  # portfolio.json 생성 (국내 종목만)
    python tools/toss_sync.py --include-us     # 해외 종목도 당일 환율로 환산해 포함
    python tools/toss_sync.py --list-accounts  # 계좌 목록만 확인
    python tools/toss_sync.py --account-no 12345678901 -o ~/Desktop/portfolio.json

키 발급: 토스증권 앱 → 전체 → Open API → 신청 (발급 후 앱에서만 재확인 가능)
API 문서: https://developers.tossinvest.com/docs
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

BASE_URL = os.environ.get("TOSS_API_BASE", "https://openapi.tossinvest.com")
FX_API_URL = os.environ.get("TOSS_FX_API", "https://api.frankfurter.app/latest")
EXPORT_VERSION = 1   # frontend/src/lib/portfolio.ts 의 EXPORT_VERSION 과 맞춘다


# =====================================================================
# 순수 함수 — 네트워크 없이 단위 테스트로 고정 (tools/tests/test_toss_sync.py)
# =====================================================================

def to_holding(item: dict, fx_rate: float = None) -> dict:
    """HoldingsItem 한 건을 대시보드의 Holding 형태로 변환.

    토스 응답의 수량·단가는 decimal **문자열**이라 float 로 바꾼다.
    id 는 종목코드로 고정한다 — 다시 동기화해도 같은 종목이 같은 id 를 갖게 해,
    '가져오기' 로 덮어써도 행이 뒤섞이지 않는다.

    해외 종목은 평단·현재가가 원종목 통화(대개 USD)로 온다. fx_rate(원/달러)를
    주면 원화로 환산하고, 국내 종목이거나 fx_rate 가 없으면 그대로 둔다.

    lastPrice · dailyProfitLoss.rate 는 importedClose/importedChangePct 로도
    내보낸다 — 대시보드가 워치리스트에 시세가 없는 종목(해외 종목, 워치리스트
    밖 국내 종목)에서 이 값을 폴백으로 쓴다. 가져오기 시점의 스냅샷이라
    실시간은 아니다.
    """
    symbol = str(item.get("symbol") or "").strip()
    is_krw = (item.get("currency") or item.get("marketCountry")) in ("KRW", "KR")
    rate = 1.0 if is_krw else (fx_rate or 1.0)

    holding = {
        "id": f"toss-{symbol}",
        "symbol": symbol,
        "name": str(item.get("name") or symbol).strip() or symbol,
        "quantity": float(item.get("quantity") or 0),
        "avgPrice": float(item.get("averagePurchasePrice") or 0) * rate,
    }

    last_price = item.get("lastPrice")
    if last_price not in (None, ""):
        holding["importedClose"] = float(last_price) * rate

    daily_rate = (item.get("dailyProfitLoss") or {}).get("rate")
    if daily_rate not in (None, ""):
        holding["importedChangePct"] = float(daily_rate) * 100

    return holding


def to_holdings(overview: dict, include_us: bool = False, fx_rate: float = None) -> tuple:
    """HoldingsOverview → (holdings, skipped) 로 변환.

    기본값은 **국내(KRW) 종목만**이다. 대시보드의 평가·합계는 원화 기준이고
    시세도 KRX 가 우선이므로, 환율 없이 달러 종목을 섞으면 매입금액 합계의
    통화가 뒤섞인 엉터리 숫자가 된다.

    --include-us 로 켜면 fx_rate(원/달러)로 환산해 포함한다. include_us 가
    True 여도 fx_rate 를 못 구했으면(환율 API 실패 등) 안전하게 계속 건너뛴다 —
    통화를 안 맞춘 채 섞는 것보다 낫다.

    수량 0(전량 매도 후 잔재)과 종목코드가 빈 항목은 버린다.
    """
    can_include_us = bool(include_us and fx_rate)
    holdings, skipped = [], []
    for item in (overview or {}).get("items") or []:
        is_krw = (item.get("currency") or item.get("marketCountry")) in ("KRW", "KR")
        if not is_krw and not can_include_us:
            skipped.append(item.get("name") or item.get("symbol") or "?")
            continue
        holding = to_holding(item, fx_rate=fx_rate)
        if not holding["symbol"] or holding["quantity"] <= 0:
            continue
        holdings.append(holding)
    return holdings, skipped


def build_export(holdings: list, now=None) -> dict:
    """대시보드 '가져오기'가 그대로 읽는 백업 형태."""
    now = now or datetime.now(timezone.utc)
    return {
        "version": EXPORT_VERSION,
        "exportedAt": now.isoformat().replace("+00:00", "Z"),
        "holdings": holdings,
    }


def pick_account(accounts: list, account_no: str = None) -> dict:
    """사용할 계좌를 고른다.

    --account-no 를 주면 그 계좌, 아니면 종합매매(BROKERAGE) 계좌.
    후보가 여럿이면 고르지 않고 예외를 던진다(엉뚱한 계좌를 말없이 쓰지 않도록).
    """
    accounts = accounts or []
    if account_no:
        for a in accounts:
            if str(a.get("accountNo")) == str(account_no):
                return a
        raise LookupError(f"계좌 {account_no} 를 찾지 못했습니다. --list-accounts 로 확인하세요.")

    if not accounts:
        raise LookupError("조회된 계좌가 없습니다.")

    brokerage = [a for a in accounts if a.get("accountType") == "BROKERAGE"]
    candidates = brokerage or accounts
    if len(candidates) > 1:
        nos = ", ".join(str(a.get("accountNo")) for a in candidates)
        raise LookupError(f"계좌가 여러 개입니다. --account-no 로 지정하세요: {nos}")
    return candidates[0]


def mask_account_no(account_no: str) -> str:
    """로그에 계좌번호 전체를 남기지 않는다."""
    s = str(account_no or "")
    return f"{s[:4]}{'*' * max(len(s) - 8, 0)}{s[-4:]}" if len(s) > 8 else "*" * len(s)


# =====================================================================
# I/O — 토스증권 Open API 호출
# =====================================================================

def load_dotenv(path=".env") -> None:
    """의존성 없이 .env 를 읽어 환경변수로 넣는다(이미 있는 값은 두고)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def fetch_usd_krw_rate() -> float:
    """해외 종목을 원화로 환산할 당일 USD/KRW 환율을 공개 API 에서 가져온다.

    토스 응답 자체에는 환율이 없다 — 계좌 요약도 KRW/USD 를 각자 합산할 뿐
    하나로 섞어주지 않는다. 인증이 필요 없는 공개 API(frankfurter.app, ECB
    기준)를 쓰며, 여기엔 Toss 키/토큰을 전혀 보내지 않는다. 실패하면 None 을
    돌려주고 호출부가 해외 종목을 건너뛰도록 둔다.
    """
    import requests

    try:
        res = requests.get(FX_API_URL, params={"from": "USD", "to": "KRW"}, timeout=10)
        res.raise_for_status()
        rate = (res.json().get("rates") or {}).get("KRW")
        return float(rate) if rate else None
    except Exception:
        return None


class TossClient:
    """읽기 전용 토스증권 Open API 클라이언트 (GET 3종만 사용)."""

    def __init__(self, client_id: str, client_secret: str, base_url: str = BASE_URL):
        import requests

        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._id, self._secret = client_id, client_secret
        self._token = None

    def _check(self, res) -> dict:
        if res.status_code == 429:
            reset = res.headers.get("X-RateLimit-Reset", "?")
            raise SystemExit(f"호출 한도를 초과했습니다. {reset}초 후 다시 시도하세요.")
        if res.status_code in (401, 403):
            # 토큰/키 값은 절대 출력하지 않는다.
            raise SystemExit(
                "인증에 실패했습니다 (%d). TOSS_CLIENT_ID/TOSS_CLIENT_SECRET 과 "
                "앱에서 발급한 키가 일치하는지 확인하세요." % res.status_code
            )
        if not res.ok:
            raise SystemExit(f"API 오류 {res.status_code}: {res.text[:200]}")
        return res.json()

    def token(self) -> str:
        if self._token:
            return self._token
        res = self._session.post(
            f"{self._base}/oauth2/token",
            headers={"content-type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self._id,
                "client_secret": self._secret,
            },
            timeout=15,
        )
        self._token = self._check(res)["access_token"]
        return self._token

    def _get(self, path: str, account_seq: int = None) -> dict:
        headers = {"authorization": f"Bearer {self.token()}"}
        if account_seq is not None:
            headers["x-tossinvest-account"] = str(account_seq)
        body = self._check(self._session.get(f"{self._base}{path}", headers=headers, timeout=20))
        return body.get("result", body)

    def accounts(self) -> list:
        return self._get("/api/v1/accounts") or []

    def holdings(self, account_seq: int) -> dict:
        return self._get("/api/v1/holdings", account_seq=account_seq) or {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="토스증권 보유 종목 → 대시보드 JSON")
    parser.add_argument("-o", "--out", default="portfolio.json", help="저장 경로 (기본: portfolio.json)")
    parser.add_argument("--account-no", help="계좌가 여러 개일 때 사용할 계좌번호")
    parser.add_argument("--list-accounts", action="store_true", help="계좌 목록만 출력하고 종료")
    parser.add_argument(
        "--include-us", action="store_true",
        help="해외(USD) 종목도 포함. 당일 USD/KRW 환율(frankfurter.app)로 원화 환산합니다 "
             "— 환율을 못 구하면 이번에도 국내 종목만 저장합니다",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    client_id = os.environ.get("TOSS_CLIENT_ID", "")
    client_secret = os.environ.get("TOSS_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 이 없습니다. .env 를 확인하세요.", file=sys.stderr)
        print("발급: 토스증권 앱 → 전체 → Open API → 신청", file=sys.stderr)
        return 1

    client = TossClient(client_id, client_secret)
    accounts = client.accounts()

    if args.list_accounts:
        for a in accounts:
            print(f"{mask_account_no(a.get('accountNo'))}  {a.get('accountType')}  seq={a.get('accountSeq')}")
        return 0

    try:
        account = pick_account(accounts, args.account_no)
    except LookupError as e:
        print(str(e), file=sys.stderr)
        return 1

    fx_rate = None
    if args.include_us:
        fx_rate = fetch_usd_krw_rate()
        if not fx_rate:
            print("USD/KRW 환율을 가져오지 못해 해외 종목은 이번에도 제외합니다.", file=sys.stderr)

    overview = client.holdings(account["accountSeq"])
    holdings, skipped = to_holdings(overview, include_us=args.include_us, fx_rate=fx_rate)

    payload = build_export(holdings)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"계좌 {mask_account_no(account.get('accountNo'))} · 보유 {len(holdings)}종목 → {args.out}")
    for h in holdings:
        print(f"  {h['symbol']}  {h['name']}  {h['quantity']:g}주  평단 {h['avgPrice']:,.0f}")
    if skipped:
        print(f"\n해외 종목 {len(skipped)}건은 제외했습니다 ({', '.join(skipped)}).")
        print("대시보드 합계가 원화 기준이라 통화가 섞이기 때문입니다. 포함하려면 --include-us")
    elif fx_rate:
        print(f"\n해외 종목은 당일 환율(1달러 ≈ {fx_rate:,.0f}원)로 환산해 포함했습니다.")
        print("환산 시점 스냅샷이라 대시보드에 '가져온 시세'로 표시되며, 실시간으로 갱신되지 않습니다.")
    print("\n대시보드 '내 포트폴리오' → 가져오기 에서 이 파일을 선택하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
