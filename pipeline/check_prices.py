"""
check_prices.py — 시세 수집 검증 (M2, DB/키 불필요)

fetch_latest_price 로 종목의 최근 영업일 일봉을 가져와 출력한다.
Supabase 없이 pykrx 응답 매핑이 맞는지 눈으로 확인하는 용도.

실행:
  cd pipeline
  python check_prices.py                 # 기본 시드 종목 전체
  python check_prices.py 005930 000660   # 특정 종목만
"""

import sys

from pipeline import fetch_latest_price
from seed_tickers import SEED_TICKERS


def main(argv):
    symbols = argv[1:] if len(argv) > 1 else [t["symbol"] for t in SEED_TICKERS]
    name_of = {t["symbol"]: t["name"] for t in SEED_TICKERS}

    print(f"[check] {len(symbols)}개 종목 최근 영업일 시세 조회")
    for sym in symbols:
        try:
            price = fetch_latest_price(sym)
        except Exception as e:
            print(f"  ! {sym} 실패: {e}")
            continue
        if price is None:
            print(f"  - {sym} 데이터 없음(휴장/미상장)")
            continue
        name = name_of.get(sym, "")
        print(
            f"  - {sym} {name:<10} {price['date']}  "
            f"종가={price['close']:>12,.0f}  "
            f"등락률={price['change_pct']:>6.2f}%  "
            f"거래량={price['volume']:>12,d}"
        )


if __name__ == "__main__":
    main(sys.argv)
