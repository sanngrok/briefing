"""
config.py — 서빙 레이어 설정 (환경변수 로딩 집중)

읽기 전용 서비스이므로 SUPABASE_KEY 는 anon(RLS) 키 사용을 권장한다.
service_role 키는 파이프라인(쓰기)에서만 쓴다.
"""

import os


class Settings:
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")

    # CORS: 프론트 도메인만 허용 (와일드카드 금지). 콤마로 여러 개.
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]


settings = Settings()
