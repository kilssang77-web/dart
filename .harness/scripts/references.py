#!/usr/bin/env python3
"""
외부 참고 프로젝트 관리.
git URL 또는 로컬 경로를 .harness/references/<name>/에 등록하고,
README를 요약한 summary.md를 생성한다.

Usage:
    python3 scripts/references.py add <git-url-or-local-path> [--purpose "설명"]
    python3 scripts/references.py list
    python3 scripts/references.py remove <name>
    python3 scripts/references.py summarize <name>  # summary.md 재생성
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
HARNESS_DIR = ROOT / ".harness"
REFS_DIR = HARNESS_DIR / "references"
REFS_JSON = HARNESS_DIR / "references.json"
TZ = timezone(timedelta(hours=9))
SUMMARY_MAX_LINES = 50


def _stamp() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _load_refs() -> dict:
    try:
        return json.loads(REFS_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"references": []}


def _save_refs(data: dict):
    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    REFS_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_name(source: str) -> str:
    """URL 또는 경로에서 사람이 읽을 수 있는 이름을 생성한다."""
    name = source.rstrip("/").split("/")[-1]
    name = name.replace(".git", "")
    name = re.sub(r"[^\w\-]", "_", name)
    return name or "reference"


def _generate_summary(ref_dir: Path) -> str:
    """README 파일을 최대 SUMMARY_MAX_LINES줄로 요약한다."""
    readme_candidates = ["README.md", "README.rst", "README.txt", "README"]
    readme = None
    for candidate in readme_candidates:
        p = ref_dir / candidate
        if p.exists():
            readme = p
            break

    lines = []
    if readme:
        try:
            content = readme.read_text(encoding="utf-8", errors="ignore")
            content_lines = content.splitlines()
            lines = content_lines[:SUMMARY_MAX_LINES]
            if len(content_lines) > SUMMARY_MAX_LINES:
                lines.append(f"\n... (총 {len(content_lines)}줄 중 상위 {SUMMARY_MAX_LINES}줄만 표시)")
        except OSError:
            pass

    if not lines:
        # README 없으면 디렉토리 구조 요약
        try:
            tree_lines = []
            for item in sorted(ref_dir.iterdir())[:20]:
                if item.name.startswith("."):
                    continue
                prefix = "├── " if item.is_file() else "└── "
                tree_lines.append(f"{prefix}{item.name}/")
            lines = [f"# {ref_dir.name}", "", "## 디렉토리 구조", "```"] + tree_lines + ["```"]
        except OSError:
            lines = [f"# {ref_dir.name}", "", "요약을 생성할 수 없습니다."]

    return "\n".join(lines)


def cmd_add(source: str, purpose: str = "", name: str = "") -> int:
    """참고 프로젝트를 추가한다."""
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    refs_data = _load_refs()

    if not name:
        name = _safe_name(source)

    ref_dir = REFS_DIR / name

    # 이미 존재하는지 확인
    existing = next((r for r in refs_data["references"] if r["name"] == name), None)
    if existing:
        print(f"[references] '{name}'은 이미 등록되어 있습니다. 업데이트하려면 remove 후 add하세요.")
        return 1

    # git URL인지 로컬 경로인지 판단
    is_git_url = source.startswith(("http://", "https://", "git@", "ssh://"))
    local_path = Path(source).resolve() if not is_git_url else None

    if is_git_url:
        print(f"[references] shallow clone: {source} → {ref_dir}")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", source, str(ref_dir)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            print(f"[references] ✗ clone 실패: {result.stderr.strip()}")
            print("[references] Hint: SSH 키 또는 액세스 토큰이 필요할 수 있습니다.")
            return 1
        kind = "git"
        path = str(ref_dir)
    elif local_path and local_path.exists():
        # 심볼릭 링크로 등록
        print(f"[references] 로컬 경로 등록: {local_path}")
        try:
            if not ref_dir.exists():
                os.symlink(local_path, ref_dir)
        except OSError as e:
            # 심볼릭 링크 실패 시 메타만 등록
            print(f"[references] 심볼릭 링크 생성 실패: {e}. 메타로만 등록합니다.")
            ref_dir.mkdir(exist_ok=True)
        kind = "local"
        path = str(local_path)
    else:
        print(f"[references] ✗ '{source}'는 유효한 git URL 또는 로컬 경로가 아닙니다.")
        return 1

    # summary.md 생성
    actual_dir = local_path if kind == "local" and local_path else ref_dir
    summary_text = _generate_summary(actual_dir)
    summary_path = ref_dir / "summary.md" if ref_dir.is_dir() else REFS_DIR / f"{name}_summary.md"
    try:
        if ref_dir.is_dir() and not ref_dir.is_symlink():
            (ref_dir / "summary.md").write_text(summary_text, encoding="utf-8")
        else:
            # 심볼릭 링크 디렉토리 — summary를 refs 상위에 저장
            summary_path = REFS_DIR / f"{name}_summary.md"
            summary_path.write_text(summary_text, encoding="utf-8")
        print(f"[references] ✓ summary.md 생성 완료")
    except OSError as e:
        print(f"[references] ⚠ summary.md 생성 실패: {e}")
        summary_path = None

    # references.json 업데이트 — alphabetical sort + ID 충돌 검사
    new_entry = {
        "name": name,
        "source": source,
        "kind": kind,
        "path": path,
        "purpose": purpose,
        "added_at": _stamp(),
        "summary_path": str(summary_path) if summary_path else "",
    }
    refs_data["references"].append(new_entry)
    refs_data["references"].sort(key=lambda r: r["name"].lower())
    _save_refs(refs_data)
    print(f"[references] ✓ '{name}' 등록 완료")
    return 0


def cmd_list() -> int:
    """등록된 참고 프로젝트 목록을 출력한다."""
    refs_data = _load_refs()
    refs = refs_data.get("references", [])
    if not refs:
        print("[references] 등록된 참고 프로젝트가 없습니다.")
        return 0

    print(f"\n{'='*60}")
    print(f"  참고 프로젝트 목록 ({len(refs)}개)")
    print(f"{'='*60}")
    for r in refs:
        print(f"\n  이름:    {r['name']}")
        print(f"  소스:    {r['source']}")
        print(f"  종류:    {r['kind']}")
        print(f"  용도:    {r.get('purpose') or '(미지정)'}")
        print(f"  추가일:  {r.get('added_at', '')}")
    return 0


def cmd_remove(name: str) -> int:
    """참고 프로젝트를 목록에서 제거한다 (clone 폴더는 유지)."""
    refs_data = _load_refs()
    before = len(refs_data["references"])
    refs_data["references"] = [r for r in refs_data["references"] if r["name"] != name]
    if len(refs_data["references"]) == before:
        print(f"[references] '{name}'을 찾을 수 없습니다.")
        return 1
    _save_refs(refs_data)
    print(f"[references] '{name}' 제거 완료 (폴더는 .harness/references/{name}에 남아 있음)")
    return 0


def cmd_summarize(name: str) -> int:
    """summary.md를 재생성한다."""
    refs_data = _load_refs()
    ref = next((r for r in refs_data["references"] if r["name"] == name), None)
    if not ref:
        print(f"[references] '{name}'을 찾을 수 없습니다.")
        return 1

    ref_dir = REFS_DIR / name
    actual_dir = Path(ref["path"]) if ref["kind"] == "local" else ref_dir
    summary_text = _generate_summary(actual_dir)

    if ref_dir.is_dir() and not ref_dir.is_symlink():
        out = ref_dir / "summary.md"
    else:
        out = REFS_DIR / f"{name}_summary.md"

    out.write_text(summary_text, encoding="utf-8")
    print(f"[references] ✓ summary.md 재생성: {out}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="참고 프로젝트 관리")
    sub = parser.add_subparsers(dest="cmd")

    add_p = sub.add_parser("add", help="참고 프로젝트 추가")
    add_p.add_argument("source", help="git URL 또는 로컬 절대경로")
    add_p.add_argument("--name", default="", help="등록할 이름 (기본: URL/경로 마지막 부분)")
    add_p.add_argument("--purpose", default="", help="이 참고 프로젝트의 용도 설명")

    sub.add_parser("list", help="등록된 목록 출력")

    rm_p = sub.add_parser("remove", help="참고 프로젝트 제거")
    rm_p.add_argument("name", help="제거할 이름")

    sum_p = sub.add_parser("summarize", help="summary.md 재생성")
    sum_p.add_argument("name", help="대상 이름")

    args = parser.parse_args()

    if args.cmd == "add":
        sys.exit(cmd_add(args.source, args.purpose, args.name))
    elif args.cmd == "list":
        sys.exit(cmd_list())
    elif args.cmd == "remove":
        sys.exit(cmd_remove(args.name))
    elif args.cmd == "summarize":
        sys.exit(cmd_summarize(args.name))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
