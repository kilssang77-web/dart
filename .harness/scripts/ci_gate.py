#!/usr/bin/env python3
"""
production 단계용 CI 게이트 스크립트.
PR 머지 전 자동으로 실행되며 다음을 검증한다:

1. validate_docs.py — docs 구문 게이트 (스켈레톤·플레이스홀더·필수 섹션)
2. runId 중복 검사 — phases/index.json에서 중복 runId 탐지
3. docs 스켈레톤 차단 — 스켈레톤 배너가 남은 문서 배열

Usage:
    python .harness/scripts/ci_gate.py [--stage production] [--json]

Exit codes:
    0 — 모든 게이트 통과
    1 — 1개 이상 실패
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = ROOT / ".harness" / "docs"
PHASES_DIR = ROOT / ".harness" / "phases"

_SKELETON_BANNER_RE = re.compile(
    r"(AUTO-GENERATED|스켈레톤|SKELETON|이 파일은.*초안|내용을 채워넣으세요)",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\{[A-Z_]{3,}\}")


def _check_validate_docs(stage: str) -> list[dict]:
    """validate_docs.py를 실행하고 에러 목록을 반환한다."""
    try:
        result = subprocess.run(
            [sys.executable, ".harness/scripts/validate_docs.py", "--stage", stage, "--json"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        data = json.loads(result.stdout) if result.stdout.strip() else {}
        errors = data.get("errors", [])
        return [{"gate": "validate_docs", "level": "error", "message": e} for e in errors]
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        return [{"gate": "validate_docs", "level": "error", "message": f"validate_docs.py 실행 실패: {e}"}]


def _check_duplicate_run_ids() -> list[dict]:
    """phases/index.json에서 중복 runId를 탐지한다."""
    index_path = PHASES_DIR / "index.json"
    if not index_path.exists():
        return []

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [{"gate": "run_id_dedup", "level": "error", "message": "phases/index.json 파싱 실패"}]

    seen: dict[str, list[str]] = {}
    for run in data.get("runs", []):
        run_id = run.get("run_id", "")
        task = run.get("task", "")
        key = f"{task}/{run_id}"
        seen.setdefault(key, []).append(run.get("dir", key))

    issues = []
    for key, dirs in seen.items():
        if len(dirs) > 1:
            issues.append({
                "gate": "run_id_dedup",
                "level": "error",
                "message": f"중복 runId 감지: {key} → {dirs}",
            })
    return issues


def _check_skeleton_docs() -> list[dict]:
    """docs 폴더에서 스켈레톤 배너·플레이스홀더가 남은 파일을 탐지한다."""
    issues = []
    if not DOCS_DIR.exists():
        return issues

    for doc in DOCS_DIR.glob("**/*.md"):
        try:
            content = doc.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(doc.relative_to(ROOT)).replace("\\", "/")
        if _SKELETON_BANNER_RE.search(content):
            issues.append({
                "gate": "skeleton_banner",
                "level": "error",
                "message": f"스켈레톤 배너가 남아 있습니다: {rel}",
            })
        placeholders = _PLACEHOLDER_RE.findall(content)
        if placeholders:
            issues.append({
                "gate": "placeholder",
                "level": "warning",
                "message": f"미치환 플레이스홀더: {rel} → {placeholders[:5]}",
            })
    return issues


def run_gates(stage: str = "production") -> tuple[list[dict], list[dict]]:
    """모든 게이트를 실행하고 (errors, warnings)를 반환한다."""
    all_issues: list[dict] = []
    all_issues.extend(_check_validate_docs(stage))
    all_issues.extend(_check_duplicate_run_ids())
    all_issues.extend(_check_skeleton_docs())

    errors = [i for i in all_issues if i["level"] == "error"]
    warnings = [i for i in all_issues if i["level"] == "warning"]
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description="CI 게이트 — production 단계 PR 머지 전 검증")
    parser.add_argument("--stage", default="production", help="검증 단계 (prototype/mvp/production)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    errors, warnings = run_gates(args.stage)

    if args.json_output:
        print(json.dumps({"errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        if warnings:
            print(f"\n⚠ 경고 ({len(warnings)}개):")
            for w in warnings:
                print(f"  [{w['gate']}] {w['message']}")

        if errors:
            print(f"\n✗ 에러 ({len(errors)}개) — PR 머지 차단:")
            for e in errors:
                print(f"  [{e['gate']}] {e['message']}")
            print("\n[ci_gate] 실패 — 위 항목을 수정한 후 다시 시도하세요.")
        else:
            print(f"[ci_gate] ✓ 모든 게이트 통과 (warnings: {len(warnings)})")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
