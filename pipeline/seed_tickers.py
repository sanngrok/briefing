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
# aliases: 네이버 뉴스 검색에 쓸 회사명/약칭. 첫 항목이 기본 검색어로 쓰인다.
SEED_TICKERS = [
    # 반도체·IT
    {"symbol": "005930", "name": "삼성전자",       "aliases": ["삼성전자", "삼성", "Samsung Electronics"]},
    {"symbol": "000660", "name": "SK하이닉스",     "aliases": ["SK하이닉스", "하이닉스", "SK Hynix"]},
    # 인터넷·플랫폼
    {"symbol": "035420", "name": "NAVER",          "aliases": ["네이버", "NAVER", "네이버 주가"]},
    {"symbol": "035720", "name": "카카오",         "aliases": ["카카오", "Kakao", "카카오 주가"]},
    {"symbol": "259960", "name": "크래프톤",       "aliases": ["크래프톤", "KRAFTON", "배틀그라운드"]},
    # 2차전지·화학
    {"symbol": "373220", "name": "LG에너지솔루션", "aliases": ["LG에너지솔루션", "LG엔솔", "LG Energy Solution"]},
    {"symbol": "006400", "name": "삼성SDI",        "aliases": ["삼성SDI", "삼성 SDI"]},
    {"symbol": "051910", "name": "LG화학",         "aliases": ["LG화학", "LG Chem"]},
    # 바이오·헬스케어
    {"symbol": "207940", "name": "삼성바이오로직스", "aliases": ["삼성바이오로직스", "삼성바이오"]},
    {"symbol": "068270", "name": "셀트리온",       "aliases": ["셀트리온", "Celltrion"]},
    # 자동차
    {"symbol": "005380", "name": "현대차",         "aliases": ["현대차", "현대자동차", "Hyundai Motor"]},
    {"symbol": "000270", "name": "기아",           "aliases": ["기아", "기아차", "Kia"]},
    # 철강·조선·방산
    {"symbol": "005490", "name": "POSCO홀딩스",    "aliases": ["POSCO홀딩스", "포스코홀딩스", "포스코"]},
    {"symbol": "012450", "name": "한화에어로스페이스", "aliases": ["한화에어로스페이스", "한화에어로"]},
    # 금융
    {"symbol": "105560", "name": "KB금융",         "aliases": ["KB금융", "KB금융지주", "국민은행"]},
    {"symbol": "055550", "name": "신한지주",       "aliases": ["신한지주", "신한금융", "신한금융지주"]},
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
    sb.table("tickers").upsert(SEED_TICKERS, on_conflict="symbol").execute()
    print(f"[seed] {len(SEED_TICKERS)}개 종목 upsert 완료")

    # 확인용: active 종목 목록 출력
    rows = sb.table("tickers").select("symbol,name,active").order("symbol").execute().data
    for r in rows:
        flag = "on" if r["active"] else "off"
        print(f"  - {r['symbol']} {r['name']} ({flag})")


if __name__ == "__main__":
    main()
