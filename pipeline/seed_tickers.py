"""
seed_tickers.py — 워치리스트(tickers) 시드 스크립트 (M1)

Supabase 의 tickers 테이블에 초기 종목을 upsert 한다.
멱등성: symbol UNIQUE 충돌 시 upsert 이므로 여러 번 실행해도 중복이 쌓이지 않는다.

사전 준비:
  1) db/schema.sql 을 Supabase 에 먼저 적용 (README 'DB 준비' 참고).
  2) 환경변수 SUPABASE_URL, SUPABASE_KEY(service_role) 설정.

실행:
  cd pipeline
  python seed_tickers.py

환경변수가 없으면 실행하지 않고 안내만 출력한다 (구조 우선, 키 연동은 이후 단계).
"""

import os
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


def main():
    url = _require_env("SUPABASE_URL")
    key = _require_env("SUPABASE_KEY")

    from supabase import create_client
    sb = create_client(url, key)

    # symbol UNIQUE 기준 upsert -> 재실행해도 중복 없음(멱등)
    rows = [{**t, "active": True} for t in SEED_TICKERS]
    sb.table("tickers").upsert(rows, on_conflict="symbol").execute()
    print(f"[seed] {len(SEED_TICKERS)}개 종목 upsert 완료")

    # 목록에서 빠진 종목은 비활성화한다. 행을 지우면 과거 시세·뉴스(FK)까지
    # 잃으므로 active=False 로만 내려 히스토리는 남긴다.
    keep = [t["symbol"] for t in SEED_TICKERS]
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
