#!/usr/bin/env python3
"""
공유 헬퍼 모듈 — run/step 상태 판정.
find_resumable.py와 execute.py._check_blockers가 이 모듈을 import하여 사용한다.
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

RESUMABLE_STATUSES = {"pending", "error", "blocked"}
STALE_HOURS = 24  # 이 시간 이내에 변경된 run을 "중단됨"으로 간주


def is_resumable_state(status: str) -> bool:
    """run/step 상태가 재개 가능 상태인지 반환한다."""
    return status in RESUMABLE_STATUSES


def find_blocked_step(run_index: dict) -> Optional[dict]:
    """run index의 steps 중 blocked/error 상태인 첫 step을 반환한다."""
    for step in run_index.get("steps", []):
        if step.get("status") in ("blocked", "error"):
            return step
    return None


def first_pending_step(run_index: dict) -> Optional[dict]:
    """run index의 steps 중 첫 pending step을 반환한다."""
    for step in run_index.get("steps", []):
        if step.get("status") == "pending":
            return step
    return None


def run_has_pending_steps(run_index: dict) -> bool:
    """run에 pending 상태 step이 1개 이상 있는지 반환한다."""
    return any(s.get("status") == "pending" for s in run_index.get("steps", []))


def is_recently_active(run_entry: dict, hours: int = STALE_HOURS) -> bool:
    """phases/index.json의 run 항목이 최근 N시간 이내에 활동했는지 확인한다."""
    for ts_key in ("blocked_at", "failed_at", "started_at"):
        ts_str = run_entry.get(ts_key)
        if not ts_str:
            continue
        try:
            # ISO 8601 파싱 (Python 3.7+)
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone(timedelta(hours=9)))
            now = datetime.now(tz=ts.tzinfo)
            if (now - ts).total_seconds() < hours * 3600:
                return True
        except ValueError:
            pass
    return False


def load_json_safe(path: Path) -> Optional[dict]:
    """JSON 파일을 안전하게 읽는다. 실패 시 None 반환."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _entry_from_run_index(run_dir: Path, task: str, run_id: str) -> Optional[dict]:
    """run 디렉터리의 index.json에서 run 엔트리를 구성한다."""
    run_index = load_json_safe(run_dir / "index.json")
    if run_index is None:
        return None

    # run-level index.json에는 status 필드가 없고 completed_at으로 완료 여부를 판별한다.
    # completed_at이 있으면 완료 처리 — 재개 목록에서 제외.
    if run_index.get("completed_at"):
        return None

    status = run_index.get("status", "pending")
    if not is_resumable_state(status):
        return None

    blocked_step = None
    reason = ""
    blocked = find_blocked_step(run_index)
    if blocked:
        blocked_step = blocked.get("step")
        reason = blocked.get("blocked_reason") or blocked.get("error_message") or ""

    return {
        "task": task,
        "run_id": run_id,
        "dir": f"{task}/{run_id}",
        "status": status,
        "blocked_step": blocked_step,
        "reason": reason,
        "stage": run_index.get("stage", ""),
        "started_at": run_index.get("created_at", "") or run_index.get("started_at", ""),
    }


def scan_resumable_runs(phases_dir: Path) -> list[dict]:
    """
    phases/ 디렉토리를 스캔하여 재개 가능한 run 목록을 반환한다.

    두 단계로 동작한다:
    1. phases/index.json(최상단 레지스트리)에서 run 목록을 읽어 빈 필드를 보정
    2. 레지스트리에 없는 run 디렉터리를 파일시스템 대조 스캔으로 추가 검출

    반환 형식:
        [
            {
                "task": str,
                "run_id": str,
                "dir": str,
                "status": str,
                "blocked_step": int | None,
                "reason": str,
                "stage": str,
                "started_at": str,
            },
            ...
        ]
    """
    top_index_path = phases_dir / "index.json"
    top = load_json_safe(top_index_path)

    results: list[dict] = []
    seen_dirs: set[str] = set()  # 레지스트리에서 처리한 dir (중복 방지)

    # ── 단계 1: 최상단 index.json 레지스트리 처리 ──
    for run_entry in (top or {}).get("runs", []):
        status = run_entry.get("status", "pending")
        if not is_resumable_state(status):
            continue

        # 최근 활동 여부 확인 (너무 오래된 run은 제외, pending은 예외)
        if not is_recently_active(run_entry, hours=STALE_HOURS):
            if status != "pending":
                continue

        run_dir_rel = run_entry.get("dir", "")
        task = run_entry.get("task", "")
        run_id = run_entry.get("run_id", "")

        # dir이 비어 있으면 task+run_id로 재조합 시도
        if not run_dir_rel:
            if task and run_id:
                run_dir_rel = f"{task}/{run_id}"
            else:
                # 복구 불가 — 이 엔트리는 스킵
                continue

        # task/run_id가 비어 있으면 dir에서 역산
        if not task or not run_id:
            parts = run_dir_rel.split("/", 1)
            if len(parts) == 2:
                task, run_id = parts[0], parts[1]
            else:
                continue

        seen_dirs.add(run_dir_rel)
        run_dir = phases_dir / run_dir_rel
        run_index = load_json_safe(run_dir / "index.json") if run_dir.is_dir() else None

        blocked_step = None
        reason = run_entry.get("blocked_reason", "")

        if run_index:
            blocked = find_blocked_step(run_index)
            if blocked:
                blocked_step = blocked.get("step")
                reason = blocked.get("blocked_reason") or blocked.get("error_message") or reason

        results.append({
            "task": task,
            "run_id": run_id,
            "dir": run_dir_rel,
            "status": status,
            "blocked_step": blocked_step,
            "reason": reason,
            "stage": run_entry.get("stage", ""),
            "started_at": run_entry.get("started_at", ""),
        })

    # ── 단계 2: 파일시스템 대조 스캔 (레지스트리 미등록 run 검출) ──
    if phases_dir.is_dir():
        for task_dir in sorted(phases_dir.iterdir()):
            if not task_dir.is_dir() or task_dir.name == "index.json":
                continue
            # 최상단 index.json 자체는 제외
            if task_dir.name.endswith(".json"):
                continue
            for run_dir in sorted(task_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                dir_rel = f"{task_dir.name}/{run_dir.name}"
                if dir_rel in seen_dirs:
                    continue
                entry = _entry_from_run_index(run_dir, task_dir.name, run_dir.name)
                if entry:
                    results.append(entry)

    return results
