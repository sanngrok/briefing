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
    {"symbol": "005930", "name": "삼성전자",   "aliases": ["삼성전자", "삼성", "Samsung Electronics"]},
    {"symbol": "000660", "name": "SK하이닉스", "aliases": ["SK하이닉스", "하이닉스", "SK Hynix"]},
    {"symbol": "035420", "name": "NAVER",      "aliases": ["네이버", "NAVER", "네이버 주가"]},
    {"symbol": "035720", "name": "카카오",     "aliases": ["카카오", "Kakao", "카카오 주가"]},
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
