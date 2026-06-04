"""pytest 전역 픽스처 — psycopg2 미설치 환경 단위 테스트 지원"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# psycopg2가 없는 환경(CI/로컬)에서 SQLAlchemy 드라이버 임포트 오류 방지.
# 단위 테스트는 실제 DB를 사용하지 않으므로 Mock 드라이버로 충분하다.
for _mod in ("psycopg2", "psycopg2.extensions", "psycopg2.extras"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
