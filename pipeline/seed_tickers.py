"""
seed_tickers.py — 워치리스트(tickers) 시드 스크립트 (M1)

Supabase 의 tickers 테이블에 초기 종목을 upsert 한다.
멱등성: symbol UNIQUE 충돌 시 upsert 이므로 여러 번 실행해도 중복이 쌓이지 않는다.

사전 준비:
  1) db/schema.sql 을 Supabase 에 먼저 적용 (README 'DB 준비' 참고).
  2) 환경변수 SUPABASE_URL, SUPABASE_KEY(service_role) 설정.

실행:
  cd pipeline
  python seed_tickers.py                    # 시총 상위 20 + (있으면) 내 보유 종목
  python seed_tickers.py --no-portfolio     # 시총 상위 20 만
  python seed_tickers.py --portfolio ~/portfolio.json

내 보유 종목 반영:
  tools/toss_sync.py 가 만든 portfolio.json 이 있으면 그 종목도 워치리스트에 넣는다.
  넣어야 시세·뉴스가 수집되고, 대시보드에서 "시세 없음"이 아니라 평가가 된다.

  주의: 이 스크립트는 목록에 없는 종목을 active=False 로 내린다. 그래서 보유 종목도
  '매번' 같이 넘겨야 켜진 채로 남는다 — portfolio.json 을 자동으로 찾는 이유다.

환경변수가 없으면 실행하지 않고 안내만 출력한다 (구조 우선, 키 연동은 이후 단계).
"""

import argparse
import json
import os
import re
import sys

# ---- 시드 종목 -------------------------------------------------------
# 선정 기준: KRX 시가총액 상위 20 (우선주 제외 — 본주와 뉴스가 중복되므로).
# 기준일 2026-09-08, 네이버 금융 시가총액 순위 기준.
#   갱신 방법: pykrx 의 시총/전종목 API 는 현재 KRX 응답 변경으로 동작하지 않는다
#   (개별 종목 시세만 정상). 순위는 네이버 금융 시가총액 페이지에서 확인해 갱신할 것.
#
# aliases[0] 이 뉴스 검색어로 쓰인다. 검색어는 반드시 실제 결과를 눈으로 확인하고
# 넣을 것 — 회사와 무관한 기사가 섞이면 감정 점수가 통째로 오염된다.
SEED_TICKERS = [
    {"symbol": "005930", "name": "삼성전자",         "aliases": ["삼성전자", "Samsung Electronics"]},
    {"symbol": "000660", "name": "SK하이닉스",       "aliases": ["SK하이닉스", "하이닉스", "SK Hynix"]},
    {"symbol": "402340", "name": "SK스퀘어",         "aliases": ["SK스퀘어", "SK Square"]},
    {"symbol": "009150", "name": "삼성전기",         "aliases": ["삼성전기", "Samsung Electro-Mechanics"]},
    {"symbol": "373220", "name": "LG에너지솔루션",   "aliases": ["LG에너지솔루션", "LG엔솔"]},
    {"symbol": "005380", "name": "현대차",           "aliases": ["현대차", "현대자동차", "Hyundai Motor"]},
    {"symbol": "207940", "name": "삼성바이오로직스", "aliases": ["삼성바이오로직스", "삼성바이오"]},
    {"symbol": "028260", "name": "삼성물산",         "aliases": ["삼성물산"]},
    {"symbol": "105560", "name": "KB금융",           "aliases": ["KB금융", "KB금융지주"]},
    {"symbol": "032830", "name": "삼성생명",         "aliases": ["삼성생명"]},
    {"symbol": "034020", "name": "두산에너빌리티",   "aliases": ["두산에너빌리티"]},
    {"symbol": "055550", "name": "신한지주",         "aliases": ["신한지주", "신한금융지주"]},
    {"symbol": "012450", "name": "한화에어로스페이스", "aliases": ["한화에어로스페이스", "한화에어로"]},
    # "기아"는 야구단(기아 타이거즈) 기사가 섞여 자동차 회사로 좁혀지는 "기아차"를 쓴다.
    {"symbol": "000270", "name": "기아",             "aliases": ["기아차", "기아 자동차", "Kia"]},
    {"symbol": "329180", "name": "HD현대중공업",     "aliases": ["HD현대중공업", "현대중공업"]},
    # SK㈜는 지주회사라 어떤 검색어를 써도 SK하이닉스·SK이노베이션 등 계열사 기사가
    # 주로 잡힌다(깨끗한 검색어가 없음). 지주사 특성상 그룹 뉴스가 주가에 실제로
    # 반영되는 면은 있으나, 이 종목의 감정 점수는 계열사와 상관이 높다는 한계가 있다.
    {"symbol": "034730", "name": "SK",               "aliases": ["SK그룹", "SK 지주회사"]},
    {"symbol": "006400", "name": "삼성SDI",          "aliases": ["삼성SDI", "삼성 SDI"]},
    {"symbol": "068270", "name": "셀트리온",         "aliases": ["셀트리온", "Celltrion"]},
    {"symbol": "086790", "name": "하나금융지주",     "aliases": ["하나금융지주", "하나금융"]},
    {"symbol": "012330", "name": "현대모비스",       "aliases": ["현대모비스", "Hyundai Mobis"]},
]


# ---- 내 보유 종목 -----------------------------------------------------
# portfolio.json 에서 가져온 종목은 종목명을 그대로 뉴스 검색어로 쓴다.
# 그 이름이 검색어로 부적절할 때만(동명이인·야구단·지주사 등) 여기에 넣는다.
# 위 SEED_TICKERS 의 "기아" 주석이 왜 필요한지 보여주는 대표 사례다.
PORTFOLIO_ALIAS_OVERRIDES = {
    # "000270": ["기아차", "기아 자동차", "Kia"],
}

# 워치리스트는 KRX 전용(pykrx 로 시세를 받는다). 6자리 숫자가 아닌 심볼은 넣지 않는다.
KR_SYMBOL = re.compile(r"^\d{6}$")

# portfolio.json 을 찾아볼 위치 (pipeline/ 에서 실행하는 경우와 루트에서 실행하는 경우)
PORTFOLIO_CANDIDATES = ("portfolio.json", "../portfolio.json")


def load_portfolio(path: str) -> list:
    """portfolio.json 에서 (symbol, name) 목록을 읽는다.

    tools/toss_sync.py 산출물과 대시보드 '내보내기' 파일이 같은 형태라 둘 다 읽힌다.
    형식이 깨졌으면 빈 목록 — 시드 자체가 실패하지는 않게 한다.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get("holdings") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out = []
    for h in items:
        if not isinstance(h, dict):
            continue
        symbol = str(h.get("symbol") or "").strip()
        if symbol:
            out.append({"symbol": symbol, "name": str(h.get("name") or symbol).strip() or symbol})
    return out


def find_portfolio(candidates=PORTFOLIO_CANDIDATES) -> str:
    """기본 위치에서 portfolio.json 을 찾는다. 없으면 None."""
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def merge_portfolio(seed: list, holdings: list, overrides: dict = None) -> tuple:
    """시드 종목 + 보유 종목을 합친다. (순수 함수)

    반환: (merged, added, skipped)
      - 이미 시드에 있는 종목은 시드 쪽을 그대로 둔다. 시드의 aliases 는 실제 검색
        결과를 눈으로 확인해 넣은 값이라, 자동 추출한 종목명보다 믿을 수 있다.
      - 같은 종목이 portfolio 안에 중복돼 있어도 1건만 들어간다.
      - KRX 6자리 코드가 아닌 심볼(해외 티커 등)은 skipped 로 뺀다. pykrx 가
        시세를 못 가져와 파이프라인이 매번 헛돌기 때문이다.
    """
    overrides = overrides or {}
    merged = list(seed)
    seen = {t["symbol"] for t in merged}
    added, skipped = [], []

    for h in holdings or []:
        symbol = h["symbol"]
        if symbol in seen:
            continue
        if not KR_SYMBOL.match(symbol):
            skipped.append(h)
            continue
        seen.add(symbol)
        entry = {
            "symbol": symbol,
            "name": h["name"],
            "aliases": overrides.get(symbol) or [h["name"]],
        }
        merged.append(entry)
        added.append(entry)
    return merged, added, skipped


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(
            f"[seed] 환경변수 {name} 가 없습니다. "
            "SUPABASE_URL / SUPABASE_KEY 를 설정한 뒤 다시 실행하세요.\n"
            "      (로컬: .env.example -> .env 복사 후 값 입력)"
        )
        sys.exit(1)
    return val


def build_watchlist(args) -> list:
    """시드 + (옵션) 보유 종목으로 이번에 적용할 워치리스트를 만든다."""
    if args.no_portfolio:
        return SEED_TICKERS

    path = args.portfolio or find_portfolio()
    if not path:
        print("[seed] portfolio.json 이 없어 시드 종목만 반영합니다. "
              "(내 보유 종목을 넣으려면 tools/toss_sync.py 를 먼저 실행하세요)")
        return SEED_TICKERS

    holdings = load_portfolio(path)
    if not holdings:
        print(f"[seed] {path} 에서 보유 종목을 읽지 못했습니다. 시드 종목만 반영합니다.")
        return SEED_TICKERS

    merged, added, skipped = merge_portfolio(holdings=holdings, seed=SEED_TICKERS,
                                             overrides=PORTFOLIO_ALIAS_OVERRIDES)
    print(f"[seed] {path} 에서 보유 {len(holdings)}종목 확인 "
          f"-> 워치리스트에 {len(added)}종목 추가")
    if added:
        for t in added:
            print(f"       + {t['symbol']} {t['name']}  (뉴스 검색어: \"{t['aliases'][0]}\")")
        # 자동 추출한 검색어는 눈으로 확인해야 한다 — 엉뚱한 기사가 섞이면
        # 그 종목의 감정 점수가 통째로 오염된다(SEED_TICKERS 의 '기아' 사례).
        print("       ! 검색어가 회사와 무관한 기사를 부르지 않는지 확인하세요.")
        print("         부적절하면 seed_tickers.py 의 PORTFOLIO_ALIAS_OVERRIDES 에 넣으세요.")
    if skipped:
        names = ", ".join(f"{h['name']}({h['symbol']})" for h in skipped)
        print(f"       - 국내 종목이 아니라 제외: {names}")
    return merged


def main(argv=None):
    parser = argparse.ArgumentParser(description="워치리스트 시드 (시총 상위 + 내 보유 종목)")
    parser.add_argument("--portfolio", help="보유 종목 JSON 경로 (기본: portfolio.json 자동 탐색)")
    parser.add_argument("--no-portfolio", action="store_true",
                        help="보유 종목을 넣지 않고 시드 종목만 반영")
    args = parser.parse_args(argv)

    watchlist = build_watchlist(args)

    url = _require_env("SUPABASE_URL")
    key = _require_env("SUPABASE_KEY")

    from supabase import create_client
    sb = create_client(url, key)

    # symbol UNIQUE 기준 upsert -> 재실행해도 중복 없음(멱등)
    rows = [{**t, "active": True} for t in watchlist]
    sb.table("tickers").upsert(rows, on_conflict="symbol").execute()
    print(f"[seed] {len(watchlist)}개 종목 upsert 완료")

    # 목록에서 빠진 종목은 비활성화한다. 행을 지우면 과거 시세·뉴스(FK)까지
    # 잃으므로 active=False 로만 내려 히스토리는 남긴다.
    keep = [t["symbol"] for t in watchlist]
    dropped = (sb.table("tickers").update({"active": False})
               .eq("active", True).not_.in_("symbol", keep).execute().data)
    if dropped:
        print(f"[seed] 목록에서 빠져 비활성화: {', '.join(d['name'] for d in dropped)}")

    # 확인용: active 종목 목록 출력
    rows = sb.table("tickers").select("symbol,name,active").order("id").execute().data
    for r in rows:
        flag = "on" if r["active"] else "off"
        print(f"  - {r['symbol']} {r['name']} ({flag})")


if __name__ == "__main__":
    main()
