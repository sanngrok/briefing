"""live_quotes.py — 네이버 금융 실시간(비공식) 시세로 장중 준실시간 값을 보강.

pykrx/KRX 는 당일 시세를 저녁 6시 이후에야 확정해서 내려준다
(https://github.com/sharebook-kr/pykrx/issues/158) — 파이프라인이 장마감 후
하루 1회만 도는 이유이기도 하다. 그래서 장중엔 DB 값이 전일 종가에 머문다.

좀 더 최신 값을 보여주려고, 네이버 금융이 자기 페이지에서 쓰는 폴링 API를
그대로 호출해 종가·등락률만 덮어쓴다(DB에는 쓰지 않는다 — 쓰기는 파이프라인의
책임, 하드룰 §4). 비공식 API라 언제든 응답 형태가 바뀌거나 막힐 수 있으므로,
실패하면 조용히 빈 dict 를 돌려주고 호출부가 DB 값(전일 종가)을 그대로 쓰게
둔다.
"""

import os
import re
import time
from datetime import date as Date
from datetime import datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_LIVE_WINDOW = (dtime(9, 0), dtime(18, 0))   # 정규장 09:00~15:30 + 시간외 단일가 ~18:00

NAVER_QUOTE_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock"
# 해외(미국) 종목. 조회 키가 로이터 코드라 나스닥은 `AAPL.O`, 뉴욕은 접미사 없이 `JPM` 이다.
NAVER_WORLD_URL = "https://polling.finance.naver.com/api/realtime/worldstock/stock"
# 달러 시세를 원화로 환산할 공개 환율 API (인증 불필요, tools/toss_sync.py 와 같은 출처).
FX_API_URL = os.environ.get("FX_API_URL", "https://api.frankfurter.dev/v1/latest")
MAX_SYMBOLS_PER_CALL = 50   # 네이버 페이지 자체도 워치리스트를 한 번에 묶어 부른다
CACHE_TTL_SECONDS = 5       # 여러 브라우저가 동시에 폴링해도 네이버는 5초에 한 번만 호출

# 이 엔드포인트는 국내(KRX) 6자리 코드만 받는다. 보유 종목에는 해외 티커(AAPL)나
# 오타가 섞일 수 있으므로, 물어봐야 소용없는 것은 호출 전에 걸러낸다.
KRX_CODE = re.compile(r"^\d{6}$")

WORLD_CACHE_TTL_SECONDS = 30    # 네이버가 권하는 해외 폴링 주기가 70초라 국내보다 느슨하게
FX_CACHE_TTL_SECONDS = 3600     # 환율은 하루 단위 값이라 한 시간이면 충분하다

_world_cache: dict = {}
_fx_cache: dict = {}


def is_krx_code(symbol: str) -> bool:
    """국내(KRX) 6자리 코드인지. 아니면 해외 티커로 본다."""
    return bool(KRX_CODE.match(symbol or ""))


def world_candidates(symbol: str) -> list:
    """해외 티커 하나를 네이버가 아는 조회 키 후보로. 나스닥은 `.O`, 뉴욕은 평문이다.

    토스가 주는 건 `AAPL` 같은 평문이라 어느 거래소인지 알 수 없다. 둘 다 후보로
    넣어 한 번에 묻고, 응답의 symbolCode 로 원래 티커에 되맞춘다(없는 키는 그냥
    응답에서 빠진다).
    """
    return [f"{symbol}.O", symbol]

_cache: dict = {}


def kst_today() -> Date:
    """지금 한국 날짜. DB 행이 없는 종목에 실시간 값만으로 시세를 만들 때 쓴다."""
    return datetime.now(KST).date()


def is_market_live_window(now: datetime = None) -> bool:
    """지금이 국내 정규장~시간외 단일가 시간대인지(평일 09:00~18:00 KST)."""
    now = (now or datetime.now(KST)).astimezone(KST)
    if now.weekday() >= 5:   # 토(5)/일(6)
        return False
    return _LIVE_WINDOW[0] <= now.time() <= _LIVE_WINDOW[1]


def _to_float(s):
    """네이버 응답은 "274,000"/"−2.75" 처럼 콤마 섞인 문자열이라 숫자로 바꾼다."""
    if s in (None, ""):
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def fetch_live_quotes(symbols: list) -> dict:
    """symbol -> {"close", "change_pct", "name"} 매핑. 실패하면(네트워크·스키마 변경) 빈 dict.

    등락률(fluctuationsRatio)은 네이버 응답에 이미 부호가 들어 있다(하락은 음수).
    종목명(stockName)도 함께 돌려주는 이유는, 워치리스트 밖 보유 종목처럼 DB 행이
    없어 이름을 채울 데가 없는 경우가 있기 때문이다.
    """
    symbols = [s for s in (symbols or []) if KRX_CODE.match(s)]
    if not symbols:
        return {}

    key = ",".join(sorted(symbols))
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    import requests

    out = {}
    for i in range(0, len(symbols), MAX_SYMBOLS_PER_CALL):
        chunk = symbols[i:i + MAX_SYMBOLS_PER_CALL]
        try:
            res = requests.get(f"{NAVER_QUOTE_URL}/{','.join(chunk)}", timeout=3)
            res.raise_for_status()
            for item in res.json().get("datas") or []:
                code = item.get("itemCode")
                close = _to_float(item.get("closePrice"))
                if not code or close is None:
                    continue
                out[code] = {
                    "close": close,
                    "change_pct": _to_float(item.get("fluctuationsRatio")),
                    "name": item.get("stockName") or "",
                }
        except Exception:
            continue   # 이 청크만 스킵 — 나머지 종목은 DB 폴백으로 채워진다

    _cache[key] = (now, out)
    return out


def fetch_usd_krw():
    """USD/KRW 환율. 실패하면 None.

    대시보드의 금액은 전부 원화 기준이다(토스 동기화도 평단을 원화로 환산해 넣는다).
    달러 시세를 그대로 내려주면 평단과 통화가 뒤섞여 평가손익이 엉터리가 되므로,
    환율을 못 구하면 해외 시세는 아예 내리지 않는다 — 호출부가 가져오기 스냅샷으로
    폴백하게 둔다(tools/toss_sync.py 가 --include-us 에서 쓰는 것과 같은 판단).
    """
    now = time.monotonic()
    cached = _fx_cache.get("USDKRW")
    if cached and now - cached[0] < FX_CACHE_TTL_SECONDS:
        return cached[1]

    import requests

    rate = None
    try:
        res = requests.get(FX_API_URL, params={"from": "USD", "to": "KRW"}, timeout=5)
        res.raise_for_status()
        value = (res.json().get("rates") or {}).get("KRW")
        rate = float(value) if value else None
    except Exception:
        rate = None

    if rate:
        _fx_cache["USDKRW"] = (now, rate)
    return rate


def fetch_world_quotes(symbols: list) -> dict:
    """해외 티커 -> {"close"(원화), "change_pct", "name", "market_open"}. 실패하면 빈 dict.

    국내와 달리 시간대로 거르지 않는다. 미국 장은 한국 새벽이라 낮에 물으면 늘
    '장 마감'이지만, 그때 받는 직전 종가도 '토스 동기화 시점에 박제된 값'보다는
    훨씬 최신이기 때문이다. 지금 장이 열려 있는지는 응답의 marketStatus 로 알려준다.

    close 는 원화로 환산해서 돌려준다(대시보드 합계가 원화 기준). change_pct 는
    종목 자체의 등락률(달러 기준)이라 환율 변동은 반영되지 않는다.
    """
    symbols = [s for s in (symbols or []) if s and not is_krx_code(s)]
    if not symbols:
        return {}

    key = ",".join(sorted(symbols))
    now = time.monotonic()
    cached = _world_cache.get(key)
    if cached and now - cached[0] < WORLD_CACHE_TTL_SECONDS:
        return cached[1]

    rate = fetch_usd_krw()
    if not rate:
        return {}          # 환산할 수 없으면 통화가 뒤섞이므로 내리지 않는다

    import requests

    wanted = {s.upper(): s for s in symbols}
    codes = [c for s in symbols for c in world_candidates(s)]

    out = {}
    for i in range(0, len(codes), MAX_SYMBOLS_PER_CALL):
        chunk = codes[i:i + MAX_SYMBOLS_PER_CALL]
        try:
            res = requests.get(f"{NAVER_WORLD_URL}/{','.join(chunk)}", timeout=3)
            res.raise_for_status()
            for item in res.json().get("datas") or []:
                symbol = wanted.get(str(item.get("symbolCode") or "").upper())
                close = _to_float(item.get("closePrice"))
                if not symbol or close is None or symbol in out:
                    continue   # 같은 티커가 두 후보로 다 오면 먼저 온 것을 쓴다
                out[symbol] = {
                    # 환산 부동소수 꼬리(461091.00000000006)를 잘라 낸다
                    "close": round(close * rate, 2),
                    "change_pct": _to_float(item.get("fluctuationsRatio")),
                    "name": item.get("stockName") or "",
                    # marketStatus 는 서머타임까지 반영된 네이버의 판단이다. 한국 기준
                    # 개장 시각이 계절마다 밀리는 문제를 우리가 계산하지 않아도 된다.
                    "market_open": str(item.get("marketStatus") or "").upper() != "CLOSE",
                }
        except Exception:
            continue

    _world_cache[key] = (now, out)
    return out
