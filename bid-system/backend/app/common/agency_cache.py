"""발주기관 인메모리 캐시 — {id: name} 딕셔너리"""
from typing import Dict

_cache: Dict[int, str] = {}


def load(data: Dict[int, str]) -> None:
    _cache.clear()
    _cache.update(data)


def get(agency_id: int) -> str:
    return _cache.get(agency_id, "")


def get_all() -> Dict[int, str]:
    return _cache
