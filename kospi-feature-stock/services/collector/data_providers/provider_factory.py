import logging
import os

logger = logging.getLogger(__name__)


def get_provider():
    """KIS 크리덴셜이 있으면 KIS Provider를, 없으면 PyKRXProvider를 반환한다.

    KISProvider가 아직 구현되지 않은 경우 None을 반환하며,
    기존 KIS REST 클라이언트(kis/ 서브모듈)를 그대로 사용한다.
    """
    kis_key = os.getenv("KIS_APP_KEY", "").strip()
    if kis_key:
        logger.info("KIS 모드로 데이터 수집")
        # KISProvider 구현 전까지 None 반환 — 기존 코드 경로 유지
        return None
    else:
        logger.warning(
            "KIS 크리덴셜 없음 — pykrx fallback 모드 (실시간 탐지 불가)"
        )
        from .pykrx_provider import PyKRXProvider

        return PyKRXProvider()


def is_kis_available() -> bool:
    """KIS_APP_KEY 환경변수가 설정되어 있으면 True를 반환한다."""
    return bool(os.getenv("KIS_APP_KEY", "").strip())
