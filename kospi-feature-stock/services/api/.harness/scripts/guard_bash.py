#!/usr/bin/env python3
"""
Bash 명령어의 위험 패턴을 차단한다.
.claude/settings.json PreToolUse(Bash) hook에서 호출된다.

Windows PowerShell 환경에서 grep이 없는 경우를 위해 Python으로 구현.
"""

from __future__ import annotations

import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

DANGEROUS_PATTERNS = [
    # 파일 삭제
    (r"rm\s+-[^\s]*r[^\s]*f|rm\s+-[^\s]*f[^\s]*r", "rm -rf / rm -fr 명령어"),
    # git — 비가역적 또는 원격 강제 push
    (r"git\s+push\s+--force-with-lease", "git push --force-with-lease"),
    (r"git\s+push\s+(--force(?!-with-lease)|-f)\b", "git push --force / -f"),
    (r"git\s+reset\s+--hard", "git reset --hard"),
    (r"git\s+clean\s+-[fdxXn]*f", "git clean -f (추적 안 된 파일 비가역적 삭제)"),
    (r"git\s+stash\s+(drop|clear)\b", "git stash drop/clear (스태시 비가역적 삭제)"),
    # 원격 코드 실행
    (r"curl\b.+\|\s*(ba|da|z)?sh\b", "curl | sh (원격 코드 실행)"),
    (r"wget\b.+\|\s*(ba|da|z)?sh\b", "wget | sh (원격 코드 실행)"),
    # DDL
    (r"DROP\s+TABLE", "DROP TABLE"),
    (r"DROP\s+DATABASE", "DROP DATABASE"),
    (r"TRUNCATE\s+TABLE", "TRUNCATE TABLE (데이터 비가역적 삭제)"),
]


def main():
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not tool_input_str:
        if len(sys.argv) > 1:
            tool_input_str = sys.argv[1]
        else:
            sys.exit(0)

    try:
        tool_input = json.loads(tool_input_str)
        command = tool_input.get("command", "")
        if not command:
            command = tool_input_str
    except (json.JSONDecodeError, AttributeError):
        command = tool_input_str

    for pattern, label in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"BLOCKED: 위험한 명령어가 감지되었습니다: {label}", file=sys.stderr)
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
