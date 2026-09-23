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

import re
import time
from datetime import date as Date
from datetime import datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_LIVE_WINDOW = (dtime(9, 0), dtime(18, 0))   # 정규장 09:00~15:30 + 시간외 단일가 ~18:00

NAVER_QUOTE_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock"
MAX_SYMBOLS_PER_CALL = 50   # 네이버 페이지 자체도 워치리스트를 한 번에 묶어 부른다
CACHE_TTL_SECONDS = 5       # 여러 브라우저가 동시에 폴링해도 네이버는 5초에 한 번만 호출

# 이 엔드포인트는 국내(KRX) 6자리 코드만 받는다. 보유 종목에는 해외 티커(AAPL)나
# 오타가 섞일 수 있으므로, 물어봐야 소용없는 것은 호출 전에 걸러낸다.
KRX_CODE = re.compile(r"^\d{6}$")

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
