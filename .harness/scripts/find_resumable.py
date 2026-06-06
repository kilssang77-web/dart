#!/usr/bin/env python3
"""
미완료(pending/blocked/error) run을 스캔하여 사용자에게 안내한다.
/a2m_start 진입 시 첫 단계로 호출된다.

기본적으로 현재 git user.email(또는 HARNESS_AUTHOR)과 일치하는 run만 표시한다.
타인 run을 포함하려면 --show-all 플래그를 사용하라.

Usage:
    python3 scripts/find_resumable.py
    python3 scripts/find_resumable.py --json
    python3 scripts/find_resumable.py --show-all
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from _resumable import scan_resumable_runs


def _get_current_author_email() -> str:
    """현재 사용자의 author 이메일을 반환한다."""
    env_val = os.environ.get("HARNESS_AUTHOR", "")
    if env_val:
        return env_val
    try:
        r = subprocess.run(["git", "config", "--get", "user.email"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    return f"{os.environ.get('USERNAME', 'unknown')}@unknown"


def _get_run_author(run: dict, phases_dir: Path) -> str:
    """run의 author 이메일을 반환한다. run.json이 있으면 우선 읽는다."""
    run_json = phases_dir / run.get("dir", "") / "run.json"
    if run_json.exists():
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
            author = data.get("author", {})
            if isinstance(author, dict):
                return author.get("email", "")
            return str(author)
        except (json.JSONDecodeError, OSError):
            pass
    return run.get("author", "")


def _print_human(runs: list[dict], all_runs: list[dict], current_author: str):
    if not runs:
        if all_runs:
            print("[find_resumable] 본인 author의 미완료 run이 없습니다.")
            print(f"  (타인 run {len(all_runs)}개가 있습니다. --show-all로 확인하세요.)")
        else:
            print("[find_resumable] 재개 가능한 미완료 run이 없습니다.")
        return

    own_count = sum(1 for r in all_runs if r.get("_author") == current_author)
    other_count = len(all_runs) - own_count

    print(f"\n{'='*60}")
    print(f"  미완료 run 감지 ({len(runs)}개 / 본인: {own_count}, 타인: {other_count})")
    print(f"  현재 사용자: {current_author}")
    print(f"{'='*60}")
    for i, run in enumerate(runs, 1):
        status_icon = {"blocked": "⏸", "error": "✗", "pending": "⏳"}.get(run["status"], "?")
        author = run.get("_author", "")
        is_own = author == current_author
        owner_tag = "" if is_own else f"  [타인: {author}]"
        print(f"\n  [{i}] {status_icon} {run['task']}/{run['run_id']}{owner_tag}")
        print(f"      상태:   {run['status']}")
        if run.get("stage"):
            print(f"      단계:   {run['stage']}")
        if run.get("started_at"):
            print(f"      시작:   {run['started_at']}")
        if run.get("blocked_step") is not None:
            print(f"      중단:   Step {run['blocked_step']}")
        if run.get("reason"):
            print(f"      사유:   {run['reason']}")
        if not is_own:
            print(f"      ⚠ 타인 run입니다. 인계받으려면: --takeover {author}")

    print(f"\n  이어서 진행하려면:")
    print(f"  python .harness/scripts/execute.py --resume")
    print(f"  또는 특정 run:")
    print(f"  python .harness/scripts/execute.py {runs[0]['dir']}")


def main():
    parser = argparse.ArgumentParser(description="미완료 run 스캐너")
    parser.add_argument("--json", action="store_true", help="JSON 출력 (명령 파이프라인용)")
    parser.add_argument("--show-all", action="store_true",
                        help="본인 run뿐만 아니라 모든 author의 run을 표시")
    args = parser.parse_args()

    phases_dir = ROOT / ".harness" / "phases"
    all_runs = scan_resumable_runs(phases_dir)
    current_author = _get_current_author_email()

    # 각 run에 _author 캐시
    for run in all_runs:
        run["_author"] = _get_run_author(run, phases_dir) or current_author

    if args.show_all:
        filtered_runs = all_runs
    else:
        filtered_runs = [r for r in all_runs if r.get("_author") == current_author]

    if args.json:
        output = {
            "resumable": filtered_runs,
            "current_author": current_author,
            "show_all": args.show_all,
            "total_runs": len(all_runs),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_human(filtered_runs, all_runs, current_author)

    sys.exit(2 if filtered_runs else 0)


if __name__ == "__main__":
    main()
