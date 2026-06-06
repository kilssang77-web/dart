#!/usr/bin/env python3
"""
PreToolUse(Edit|Write) hook — 보호 경로 차단 및 경고.
.claude/settings.json의 PreToolUse hook에서 호출된다.

차단 티어:
  Tier 1 — Hard Block: .git/, .env 시크릿, 완료 run, 타인 run, 공유 상태 파일
  Tier 2 — Soft Warn: lockfile, CI 워크플로, Dockerfile, gitignore 등
  Tier 3 — Context-sensitive: docs(A2M_NO_DOCS_EDIT), harness 스크립트

성능 목표: 100ms 이내 완료

CLI:
  python guard_paths.py --list-rules       모든 룰 ID·level 출력
  python guard_paths.py --test <path>      특정 경로에 대한 룰 매칭 결과
  python guard_paths.py --explain <path>   차단 시 상세 안내
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent

# ─── mtime 기반 캐시 ───

_cache: dict[str, tuple] = {}


def _cached_load(path: Path, loader):
    mtime = path.stat().st_mtime if path.exists() else 0
    cached = _cache.get(str(path))
    if cached and cached[1] == mtime:
        return cached[0]
    val = loader(path)
    _cache[str(path)] = (val, mtime)
    return val


# ─── 데이터 로더 ───

def _read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _load_completed_run_dirs_inner(index_path: Path) -> set[str]:
    top = _read_json_safe(index_path)
    return {
        r["dir"]
        for r in top.get("runs", [])
        if r.get("status") == "completed" and r.get("dir")
    }


def _load_completed_run_dirs() -> set[str]:
    return _cached_load(
        ROOT / ".harness" / "phases" / "index.json",
        _load_completed_run_dirs_inner,
    )


def _load_synced_release_notes_inner(index_path: Path) -> set[str]:
    synced = set()
    if not index_path.exists():
        return synced
    content = index_path.read_text(encoding="utf-8", errors="ignore")
    for line in content.splitlines():
        if "✅" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts:
                fname = parts[0].lstrip("#").strip()
                if fname.endswith(".md"):
                    synced.add(fname)
    return synced


def _load_synced_release_notes() -> set[str]:
    return _cached_load(
        ROOT / ".harness" / "release-notes" / "INDEX.md",
        _load_synced_release_notes_inner,
    )


def _get_current_author_email() -> str:
    env_val = os.environ.get("HARNESS_AUTHOR", "")
    if env_val:
        return env_val
    try:
        import subprocess
        r = subprocess.run(["git", "config", "--get", "user.email"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=str(ROOT))
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (FileNotFoundError, Exception):
        pass
    return os.environ.get("USERNAME", "unknown") + "@unknown"


def _load_foreign_run_dirs() -> set[str]:
    """현재 사용자가 아닌 미완료 run의 dir 목록을 반환한다."""
    index_path = ROOT / ".harness" / "phases" / "index.json"
    top = _cached_load(index_path, _load_completed_run_dirs_inner.__wrapped__
                       if hasattr(_load_completed_run_dirs_inner, '__wrapped__') else
                       lambda p: _read_json_safe(p))
    # top은 set이 아니라 dict — index.json을 직접 읽어야 함
    raw = _read_json_safe(ROOT / ".harness" / "phases" / "index.json")
    current = _get_current_author_email()
    foreign = set()
    for r in raw.get("runs", []):
        if r.get("status") not in ("completed",) and r.get("dir"):
            run_author = r.get("author", "")
            if run_author and run_author != current:
                foreign.add(r["dir"])
    return foreign


# ─── 경로 매처 보강 ───

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
        # paths 배열이면 첫 번째 반환 (다중 파일 도구)
        if "paths" in data and isinstance(data["paths"], list) and data["paths"]:
            return str(data["paths"][0])
        # 위 어느 키도 없으면 첫 string-value 후보
        for val in data.values():
            if isinstance(val, str) and ("/" in val or "\\" in val):
                return val
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass

    if "/" in tool_input_str or "\\" in tool_input_str:
        return tool_input_str.strip()

    return None


# ─── 패턴 헬퍼 ───

_ENV_SECRET_RE = re.compile(
    r"(^|/)\.env(\.[^/]*)?$",
    re.IGNORECASE,
)
_ENV_EXAMPLE_RE = re.compile(
    r"(^|/)\.env(\.[^/]*)?\.(example|sample|template)$",
    re.IGNORECASE,
)
_SECRET_FILE_RE = re.compile(
    r"(id_rsa|id_ed25519|id_ecdsa|id_dsa|\.pem|\.key|\.p12|\.pfx|"
    r"credentials\.json|secrets\.json|\.kdbx|service.account\.json)$",
    re.IGNORECASE,
)
_LOCKFILE_RE = re.compile(
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|"
    r"Pipfile\.lock|Gemfile\.lock|Cargo\.lock)$",
    re.IGNORECASE,
)
_CI_RE = re.compile(
    r"(^|/)(\.(github/workflows|gitlab-ci\.yml|circleci/config\.yml)|"
    r"Jenkinsfile|azure-pipelines\.yml)($|/)",
    re.IGNORECASE,
)
_DOCKER_RE = re.compile(
    r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*|compose\.[^/]+\.yml)$",
    re.IGNORECASE,
)
_MIGRATION_RE = re.compile(
    r"(^|/)(db/migration|flyway|liquibase)/V\d+__",
    re.IGNORECASE,
)

# 공유 상태 파일 — docs 세션 외에는 자동 변경 금지
SHARED_STATE_FILES = {
    "CLAUDE.md",
    ".harness/profile.json",
    ".harness/personas.yaml",
    ".harness/questions.yaml",
    ".harness/answers.json",
    ".harness/references.json",
    ".harness/release-notes/INDEX.md",
    ".harness/phases/index.json",
}

DOCS_LIVE_SYNC = {".harness/docs/SCHEMA.md"}


def _load_guard_config() -> dict:
    """
    .harness/guard.yaml 또는 profile.json.guard 를 읽어 룰 설정을 반환한다.
    우선순위: guard.yaml > profile.json.guard
    """
    guard_yaml_path = ROOT / ".harness" / "guard.yaml"
    profile_path = ROOT / ".harness" / "profile.json"

    def _from_guard_yaml(p: Path) -> dict:
        if not p.exists():
            return {}
        try:
            # PyYAML 없이 기본 파싱 (간단한 key: [list] 형식만 지원)
            import yaml
            with p.open(encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            return {}
        except Exception:
            return {}

    def _from_profile(p: Path) -> dict:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d.get("guard", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    config = _cached_load(guard_yaml_path, _from_guard_yaml)
    if not config:
        config = _cached_load(profile_path, _from_profile)
    return config or {}


def _is_rule_disabled(rule_id: str) -> bool:
    cfg = _load_guard_config()
    disabled = cfg.get("disable_rules", [])
    return rule_id in disabled


def _is_path_whitelisted(rel_str: str) -> bool:
    cfg = _load_guard_config()
    whitelist = cfg.get("whitelist_paths", [])
    for pattern in whitelist:
        if rel_str == pattern or rel_str.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def check(target_path_str: str | None) -> tuple[str, str]:
    """
    경로를 검사하고 (action, message)를 반환한다.
    action: "allow" | "block" | "warn"
    """
    if not target_path_str:
        return "allow", ""

    target = Path(target_path_str)
    if not target.is_absolute():
        target = ROOT / target

    # .. 세그먼트 해소
    try:
        target = target.resolve(strict=False)
    except Exception:
        pass

    try:
        rel = target.relative_to(ROOT.resolve(strict=False))
        rel_str = str(rel).replace("\\", "/")
    except ValueError:
        return "allow", ""  # ROOT 외부 — 허용 (external rule)

    # guard.yaml whitelist 경로 — 모든 룰을 우회
    if _is_path_whitelisted(rel_str):
        return "allow", ""

    # ─── Tier 1: Hard Block ───

    # .git/ 내부
    if not _is_rule_disabled("git_internal") and (rel_str == ".git" or rel_str.startswith(".git/")):
        return (
            "block",
            f"✗ 차단: .git/ 내부 파일은 직접 수정할 수 없습니다.\n"
            f"  경로: {rel_str}",
        )

    # .env 시크릿 (example 제외)
    if not _is_rule_disabled("env_secret") and _ENV_SECRET_RE.search(rel_str) and not _ENV_EXAMPLE_RE.search(rel_str):
        return (
            "block",
            f"✗ 차단: .env 파일은 시크릿입니다.\n"
            f"  경로: {rel_str}\n"
            f"  - 비밀값을 추가하려면 .env.example에 키만 추가하고 실제 값은 로컬 .env에 직접 입력하세요.\n"
            f"  - 정말 필요하다면 A2M_ALLOW_SECRET_EDIT=1 환경변수를 명시하세요.",
        )
    if not _is_rule_disabled("secret_file") and os.environ.get("A2M_ALLOW_SECRET_EDIT", "").lower() not in ("1", "true", "yes"):
        if _SECRET_FILE_RE.search(rel_str):
            return (
                "block",
                f"✗ 차단: 인증/시크릿 파일은 수정할 수 없습니다.\n"
                f"  경로: {rel_str}\n"
                f"  - A2M_ALLOW_SECRET_EDIT=1 환경변수로 한 세션에서만 허용할 수 있습니다.",
            )

    # 완료된 run 폴더
    if not _is_rule_disabled("completed_run") and rel_str.startswith(".harness/phases/"):
        completed_dirs = _load_completed_run_dirs()
        for completed_dir in completed_dirs:
            if rel_str.startswith(f".harness/phases/{completed_dir}/"):
                return (
                    "block",
                    f"✗ 차단: 완료(completed)된 run 폴더는 수정할 수 없습니다.\n"
                    f"  경로: {rel_str}\n"
                    f"  새 run을 시작하거나 /a2m_start 명령을 사용하세요.",
                )

    # 타인 미완료 run (takeover 없이)
    if not _is_rule_disabled("foreign_run") and rel_str.startswith(".harness/phases/") and os.environ.get("A2M_TAKEOVER") != "1":
        foreign_dirs = _load_foreign_run_dirs()
        for foreign_dir in foreign_dirs:
            if rel_str.startswith(f".harness/phases/{foreign_dir}/"):
                return (
                    "block",
                    f"✗ 차단: 타인이 시작한 미완료 run 폴더는 수정할 수 없습니다.\n"
                    f"  경로: {rel_str}\n"
                    f"  인계받으려면: execute.py {foreign_dir} --takeover <author_email>",
                )

    # 공유 상태 파일 (docs 세션 외에는 차단)
    is_docs_session = os.environ.get("A2M_DOCS_SESSION", "") == "1"
    if not _is_rule_disabled("shared_state") and rel_str in SHARED_STATE_FILES and not is_docs_session:
        return (
            "block",
            f"✗ 차단: 공유 상태 파일은 docs 세션(A2M_DOCS_SESSION=1)에서만 수정 가능합니다.\n"
            f"  경로: {rel_str}\n"
            f"  - /a2m_docs 또는 /a2m_start 명령으로 진입 시 자동으로 세션이 활성화됩니다.\n"
            f"  - 독립적인 변경이 필요하면 별도 PR을 만드세요.",
        )

    # .harness/docs/** 보호 (A2M_NO_DOCS_EDIT=1 시)
    if (
        not _is_rule_disabled("docs_no_edit")
        and rel_str.startswith(".harness/docs/")
        and rel_str not in DOCS_LIVE_SYNC
        and os.environ.get("A2M_NO_DOCS_EDIT") == "1"
    ):
        return (
            "block",
            f"✗ 차단: 현재 컨텍스트(a2m_improve)에서 .harness/docs/**를 직접 수정할 수 없습니다.\n"
            f"  변경 내역은 release-note에 자동 기록됩니다.\n"
            f"  docs 동기화는 /a2m_sync_docs 명령으로 수행하세요.\n"
            f"  (예외: .harness/docs/SCHEMA.md는 마이그레이션 파일과 함께 즉시 수정 가능)",
        )

    # ─── Tier 2: Soft Warn ───

    # synced release-note
    if not _is_rule_disabled("synced_release_note") and rel_str.startswith(".harness/release-notes/") and rel_str.endswith(".md"):
        fname = Path(rel_str).name
        synced = _load_synced_release_notes()
        if fname in synced:
            return (
                "warn",
                f"⚠ 경고: 이미 docs에 반영(synced)된 release-note를 편집하려 합니다.\n"
                f"  파일: {rel_str}\n"
                f"  변경 시 docs와 이력이 어긋날 수 있습니다.",
            )

    # lockfile
    if not _is_rule_disabled("lockfile") and _LOCKFILE_RE.search(rel_str):
        return (
            "warn",
            f"⚠ 경고: 패키지 매니저 lockfile을 직접 수정하려 합니다.\n"
            f"  파일: {rel_str}\n"
            f"  패키지 매니저(npm/yarn/pip 등)가 자동 재생성해야 합니다. 수동 편집은 예외적인 경우에만.",
        )

    # CI 워크플로
    if not _is_rule_disabled("ci_workflow") and _CI_RE.search(rel_str):
        return (
            "warn",
            f"⚠ 경고: CI/CD 워크플로 파일을 수정하려 합니다.\n"
            f"  파일: {rel_str}\n"
            f"  모든 PR에 영향을 줍니다. 의도된 변경인지 확인하세요.",
        )

    # Dockerfile / docker-compose
    if not _is_rule_disabled("dockerfile") and _DOCKER_RE.search(rel_str):
        return (
            "warn",
            f"⚠ 경고: Docker 설정 파일을 수정하려 합니다.\n"
            f"  파일: {rel_str}\n"
            f"  팀 전체 로컬·배포 환경에 영향을 줍니다. 의도된 변경인지 확인하세요.",
        )

    # .gitignore
    if not _is_rule_disabled("gitignore") and (rel_str == ".gitignore" or rel_str.endswith("/.gitignore")):
        return (
            "warn",
            f"⚠ 경고: .gitignore를 수정하려 합니다.\n"
            f"  파일: {rel_str}\n"
            f"  추가/삭제가 시크릿·산출물 추적 정책에 영향을 줄 수 있습니다.",
        )

    # 기존 마이그레이션 파일 (커밋된 것)
    if not _is_rule_disabled("migration_file") and _MIGRATION_RE.search(rel_str):
        return (
            "warn",
            f"⚠ 경고: 기존 마이그레이션 파일을 수정하려 합니다.\n"
            f"  파일: {rel_str}\n"
            f"  Flyway/Liquibase의 immutability 규칙상 기존 파일 수정은 환경 간 불일치를 유발합니다.\n"
            f"  새 파일(V{'{n+1}'}__...sql)을 추가하세요.",
        )

    return "allow", ""


def _list_rules():
    rules = [
        ("git_internal", "block", ".git/ 내부 파일 보호"),
        ("env_secret", "block", ".env 시크릿 파일 보호 (.env.example 제외)"),
        ("secret_file", "block", "인증/키/시크릿 파일 보호"),
        ("completed_run", "block", "완료 run 폴더 보호"),
        ("foreign_run", "block", "타인 미완료 run 보호 (takeover 필요)"),
        ("shared_state", "block", "공유 상태 파일 (CLAUDE.md/profile.json 등) 보호"),
        ("docs_no_edit", "block", "A2M_NO_DOCS_EDIT=1 시 .harness/docs/** 보호"),
        ("synced_release_note", "warn", "이미 synced된 release-note 경고"),
        ("lockfile", "warn", "패키지 매니저 lockfile 직접 편집 경고"),
        ("ci_workflow", "warn", "CI/CD 워크플로 변경 경고"),
        ("dockerfile", "warn", "Docker 설정 파일 변경 경고"),
        ("gitignore", "warn", ".gitignore 변경 경고"),
        ("migration_file", "warn", "기존 마이그레이션 파일 수정 경고"),
    ]
    print(f"{'ID':<25} {'Level':<8} 설명")
    print("-" * 60)
    for rule_id, level, desc in rules:
        print(f"{rule_id:<25} {level:<8} {desc}")


def main():
    parser = argparse.ArgumentParser(description="Guard Paths — 보호 경로 차단/경고")
    parser.add_argument("input", nargs="?", default="",
                        help="CLAUDE_TOOL_INPUT JSON 또는 파일 경로")
    parser.add_argument("--list-rules", action="store_true", help="모든 룰 목록 출력")
    parser.add_argument("--test", metavar="PATH", help="특정 경로에 대한 룰 매칭 결과")
    parser.add_argument("--explain", metavar="PATH", help="차단 시 상세 안내")
    args = parser.parse_args()

    if args.list_rules:
        _list_rules()
        sys.exit(0)

    test_path = args.test or args.explain
    if test_path:
        action, message = check(test_path)
        print(f"Path : {test_path}")
        print(f"Action: {action}")
        if message:
            print(f"Message:\n{message}")
        sys.exit(0)

    tool_input = args.input or os.environ.get("CLAUDE_TOOL_INPUT", "")
    target_path = _extract_target_path(tool_input)

    action, message = check(target_path)

    if action == "block":
        print(message, file=sys.stderr)
        sys.exit(1)
    elif action == "warn":
        print(message, file=sys.stderr)
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
