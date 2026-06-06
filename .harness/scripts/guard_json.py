#!/usr/bin/env python3
"""
PostToolUse(Edit|Write) hook — critical harness 파일의 JSON/YAML 유효성 검사.
.claude/settings.json의 PostToolUse hook에서 호출된다.

검사 대상 (ROOT 기준 상대 경로):
  - .harness/profile.json
  - .harness/phases/index.json
  - .harness/phases/*/index.json   (run별 index)
  - .harness/answers.json
  - .harness/references.json
  - .harness/guard.yaml

동작:
  - 대상 파일이 아니면 즉시 exit 0
  - JSON 파싱 실패 시 오류 메시지 출력 후 exit 1
  - YAML은 PyYAML 없이 기본 파싱 시도, 실패 시 경고만 출력 (exit 0)

성능 목표: 10ms 이내 완료 (파싱만 수행)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent

# JSON 검사 대상 — glob 패턴 없이 직접 목록 + 동적 감지
JSON_EXACT = {
    ".harness/profile.json",
    ".harness/phases/index.json",
    ".harness/answers.json",
    ".harness/references.json",
}

# phases/*/index.json 패턴 (task 폴더 아래 run별 index)
_RUN_INDEX_RE = re.compile(
    r"^\.harness[/\\]phases[/\\][^/\\]+[/\\][^/\\]+[/\\]index\.json$",
    re.IGNORECASE,
)

YAML_EXACT = {
    ".harness/guard.yaml",
    ".harness/personas.yaml",
}


def _extract_target_path(tool_input_str: str) -> str | None:
    """CLAUDE_TOOL_INPUT에서 대상 파일 경로를 추출한다."""
    if not tool_input_str:
        return None
    try:
        data = json.loads(tool_input_str)
        for key in ("path", "file_path", "target", "filename", "target_file",
                    "notebook_path", "source", "destination", "src", "dst"):
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    return val
        if "paths" in data and isinstance(data["paths"], list) and data["paths"]:
            return str(data["paths"][0])
        for val in data.values():
            if isinstance(val, str) and ("/" in val or "\\" in val):
                return val
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass

    if "/" in tool_input_str or "\\" in tool_input_str:
        return tool_input_str.strip()
    return None


def _to_rel(path_str: str) -> str | None:
    """절대 또는 상대 경로를 ROOT 기준 상대 경로 문자열로 변환한다."""
    target = Path(path_str)
    if not target.is_absolute():
        target = ROOT / target
    try:
        target = target.resolve(strict=False)
        rel = target.relative_to(ROOT.resolve(strict=False))
        return str(rel).replace("\\", "/")
    except ValueError:
        return None


def _is_json_target(rel_str: str) -> bool:
    return rel_str in JSON_EXACT or bool(_RUN_INDEX_RE.match(rel_str))


def _is_yaml_target(rel_str: str) -> bool:
    return rel_str in YAML_EXACT


def _check_json(path: Path, rel_str: str) -> int:
    """JSON 파일 유효성 검사. 실패 시 1 반환."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[guard_json] ✗ 파일 읽기 실패: {rel_str}\n  {e}", file=sys.stderr)
        return 1

    try:
        json.loads(content)
        return 0
    except json.JSONDecodeError as e:
        print(
            f"[guard_json] ✗ JSON 파싱 오류: {rel_str}\n"
            f"  줄 {e.lineno}, 열 {e.colno}: {e.msg}\n"
            f"  이 파일은 harness 핵심 설정입니다. 올바른 JSON으로 수정하세요.",
            file=sys.stderr,
        )
        return 1


def _check_yaml(path: Path, rel_str: str) -> int:
    """YAML 파일 유효성 검사. PyYAML 없으면 경고만 출력(exit 0)."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[guard_json] ✗ 파일 읽기 실패: {rel_str}\n  {e}", file=sys.stderr)
        return 1

    try:
        import yaml
        yaml.safe_load(content)
        return 0
    except ImportError:
        # PyYAML 없음 — 경고만 출력하고 통과
        print(
            f"[guard_json] ⚠ PyYAML 미설치 — {rel_str} YAML 검사 생략\n"
            f"  pip install pyyaml 으로 설치하면 YAML도 검사합니다.",
            file=sys.stderr,
        )
        return 0
    except Exception as e:
        print(
            f"[guard_json] ✗ YAML 파싱 오류: {rel_str}\n"
            f"  {e}\n"
            f"  이 파일은 harness 설정입니다. 올바른 YAML로 수정하세요.",
            file=sys.stderr,
        )
        return 1


def main() -> int:
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if len(sys.argv) > 1:
        tool_input = tool_input or sys.argv[1]

    target_str = _extract_target_path(tool_input)
    if not target_str:
        return 0

    rel_str = _to_rel(target_str)
    if rel_str is None:
        return 0  # ROOT 외부 파일 — 무시

    target_path = ROOT / rel_str

    if _is_json_target(rel_str):
        if not target_path.exists():
            return 0  # 삭제된 파일 — 검사 불필요
        return _check_json(target_path, rel_str)

    if _is_yaml_target(rel_str):
        if not target_path.exists():
            return 0
        return _check_yaml(target_path, rel_str)

    return 0  # 검사 대상 아님


if __name__ == "__main__":
    sys.exit(main())
