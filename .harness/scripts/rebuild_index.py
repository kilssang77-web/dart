#!/usr/bin/env python3
"""
phases/index.json을 각 run 폴더의 run.json·index.json으로부터 재생성한다.

phases/index.json은 derived 파일이다. 머지 충돌이 발생하면 이 스크립트로 재생성한다.
진실(source of truth)은 phases/<task>/<runId>/run.json (또는 index.json) 이다.

Usage:
    python .harness/scripts/rebuild_index.py
    python .harness/scripts/rebuild_index.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
PHASES_DIR = ROOT / ".harness" / "phases"


def _load_run_meta(task: str, run_id: str) -> dict | None:
    """run.json 또는 index.json에서 run 메타데이터를 로드한다."""
    run_dir = PHASES_DIR / task / run_id

    run_json = run_dir / "run.json"
    if run_json.exists():
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
            return {
                "task": data.get("task", task),
                "run_id": data.get("run_id", run_id),
                "dir": f"{task}/{run_id}",
                "status": data.get("status", "unknown"),
                "stage": data.get("stage", ""),
                "branch": data.get("branch", f"feat/{task}-{run_id}"),
                "started_at": data.get("started_at", ""),
                "author": data.get("author", {}).get("email", "") if isinstance(data.get("author"), dict) else data.get("author", ""),
            }
        except (json.JSONDecodeError, OSError):
            pass

    idx_json = run_dir / "index.json"
    if idx_json.exists():
        try:
            data = json.loads(idx_json.read_text(encoding="utf-8"))
            steps = data.get("steps", [])
            statuses = [s.get("status", "pending") for s in steps]
            if all(s == "completed" for s in statuses):
                status = "completed"
            elif any(s == "error" for s in statuses):
                status = "error"
            elif any(s == "blocked" for s in statuses):
                status = "blocked"
            else:
                status = "pending"
            return {
                "task": data.get("phase", task),
                "run_id": run_id,
                "dir": f"{task}/{run_id}",
                "status": data.get("status", status),
                "stage": data.get("stage", ""),
                "branch": data.get("branch", f"feat/{task}-{run_id}"),
                "started_at": data.get("created_at", ""),
                "author": "",
            }
        except (json.JSONDecodeError, OSError):
            pass

    return None


def rebuild(dry_run: bool = False) -> int:
    """phases/index.json을 재생성한다. dry_run이면 출력만 한다."""
    if not PHASES_DIR.is_dir():
        print(f"ERROR: {PHASES_DIR} not found")
        return 1

    runs: list[dict] = []

    for task_dir in sorted(PHASES_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name == "index.json":
            continue
        task = task_dir.name
        for run_dir in sorted(task_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            meta = _load_run_meta(task, run_id)
            if meta:
                runs.append(meta)

    index = {"runs": runs, "_note": "이 파일은 derived입니다. rebuild_index.py로 재생성하세요."}

    if dry_run:
        print(json.dumps(index, indent=2, ensure_ascii=False))
    else:
        out = PHASES_DIR / "index.json"
        out.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✓ {out} 재생성 완료 ({len(runs)}개 run)")

    return 0


def main():
    parser = argparse.ArgumentParser(description="phases/index.json 재생성")
    parser.add_argument("--dry-run", action="store_true", help="파일 수정 없이 결과만 출력")
    args = parser.parse_args()
    sys.exit(rebuild(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
