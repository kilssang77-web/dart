#!/usr/bin/env python3
"""
docs/ 폴더의 문서 충실도를 검사하고 결과를 JSON으로 출력한다.

Usage:
    python3 scripts/validate_docs.py [--stage prototype|mvp|production] [--json]

Exit codes:
    0 — 에러 없음 (경고만 있을 수 있음)
    1 — 에러 1건 이상
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = ROOT / ".harness" / "docs"

# 단계별 필수 문서
REQUIRED_DOCS_BY_STAGE = {
    "prototype": ["PRD", "ARCHITECTURE", "ADR", "UI_GUIDE"],
    "mvp": ["PRD", "ARCHITECTURE", "ADR", "UI_GUIDE", "CODING_CONVENTION",
            "PROJECT_STRUCTURE", "SECURITY", "TESTING", "API_GUIDE", "SCHEMA", "SCREEN_MAP"],
    "production": ["PRD", "ARCHITECTURE", "ADR", "UI_GUIDE", "CODING_CONVENTION",
                   "PROJECT_STRUCTURE", "SECURITY", "TESTING", "API_GUIDE", "SCHEMA",
                   "SCREEN_MAP", "DEPLOYMENT"],
}

# 단계별 필수 섹션 키워드 (문서명 → 필수 헤더 패턴)
REQUIRED_SECTIONS_BY_STAGE: dict[str, dict[str, list[str]]] = {
    "production": {
        "SECURITY": ["OWASP", "의존성"],
        "TESTING": ["커버리지", "통합"],
        "API_GUIDE": ["에러", "인증"],
        "SCHEMA": ["마이그레이션", "인덱스"],
        "SCREEN_MAP": ["사이트맵", "화면 목록"],
        "DEPLOYMENT": ["배포", "환경"],
    },
    "mvp": {
        "SECURITY": ["인증"],
        "TESTING": ["단위"],
        "SCHEMA": ["테이블"],
        "SCREEN_MAP": ["사이트맵", "화면 목록"],
    },
    "prototype": {},
}

SKELETON_BANNER_PATTERNS = [
    "이 문서는 스켈레톤입니다",
    "AUTO-GENERATED SKELETON",
    "이 파일은 /a2m_docs 질문",
]
# ${VAR}, $VAR 같은 환경변수 치환 구문을 먼저 공백으로 제거한 뒤 플레이스홀더 검사
_ENV_VAR_PATTERN = re.compile(r"\$\{[^}]+\}|\$[A-Z_][A-Z0-9_]*")
PLACEHOLDER_PATTERN = re.compile(r"\{[^}]{1,80}\}")
TODO_PATTERN = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)
EXAMPLE_CONTEXT = re.compile(r"(게시판|board-app|BoardApplication|PostService|board/|spring-petclinic)", re.IGNORECASE)

# 하네스 자체 운영 문서 — 내용(플레이스홀더·빈섹션) 검사 제외, 존재 여부만 확인
HARNESS_INTERNAL_DOCS = {"MCP_GUIDE"}


def check_file(path: Path, stage: str) -> list[dict]:
    """단일 문서 파일을 검사하여 이슈 목록을 반환한다."""
    issues: list[dict] = []
    stem = path.stem
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return [{"level": "error", "doc": stem, "message": f"파일 읽기 실패: {e}"}]

    # 하네스 내부 운영 문서는 내용 검사 생략
    if stem in HARNESS_INTERNAL_DOCS:
        return issues

    lines = text.splitlines()

    # 스켈레톤 배너 잔존
    if any(banner in text for banner in SKELETON_BANNER_PATTERNS):
        issues.append({
            "level": "error",
            "doc": stem,
            "message": "스켈레톤 배너가 그대로 남아 있습니다. 문서를 실제 프로젝트 내용으로 채우세요.",
        })

    # 플레이스홀더 잔존 — ${ENV_VAR} 등 환경변수 구문은 제외하고 검사
    text_no_env = _ENV_VAR_PATTERN.sub("", text)
    placeholders = PLACEHOLDER_PATTERN.findall(text_no_env)
    if placeholders:
        sample = placeholders[:3]
        issues.append({
            "level": "warning",
            "doc": stem,
            "message": f"{len(placeholders)}개 플레이스홀더 잔존: {sample}",
        })

    # TODO/TBD 잔존
    todos = TODO_PATTERN.findall(text)
    if todos:
        issues.append({
            "level": "warning",
            "doc": stem,
            "message": f"TODO/TBD 마커 {len(todos)}건 잔존",
        })

    # 빈 섹션 (헤더 바로 다음이 빈 줄 또는 다음 헤더)
    empty_sections = []
    for i, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("### "):
            content_lines = []
            for j in range(i + 1, min(i + 10, len(lines))):
                l = lines[j].strip()
                if l.startswith("#"):
                    break
                if l and not l.startswith(">"):
                    content_lines.append(l)
            if not content_lines:
                empty_sections.append(line.strip())
    if empty_sections:
        issues.append({
            "level": "warning",
            "doc": stem,
            "message": f"내용 없는 섹션 {len(empty_sections)}개: {empty_sections[:3]}",
        })

    # 단계별 필수 섹션 검사
    stage_sections = REQUIRED_SECTIONS_BY_STAGE.get(stage, {})
    required_for_doc = stage_sections.get(stem, [])
    for keyword in required_for_doc:
        if keyword not in text:
            issues.append({
                "level": "error",
                "doc": stem,
                "message": f"'{keyword}' 관련 섹션이 없습니다 ({stage} 단계 필수)",
            })

    # 예시 항목이 그대로 남아 있는지 확인 (정보성)
    if EXAMPLE_CONTEXT.search(text) and "<!-- 예시 -->" in text:
        issues.append({
            "level": "info",
            "doc": stem,
            "message": "예시 항목(게시판 컨텍스트)이 그대로 남아 있습니다. 실제 프로젝트로 교체하세요.",
        })

    return issues


def validate(stage: str = "mvp") -> dict:
    """docs/ 전체를 검사하고 결과 딕셔너리를 반환한다."""
    if not DOCS_DIR.is_dir():
        return {
            "stage": stage,
            "summary": {"errors": 1, "warnings": 0, "info": 0},
            "issues": [{"level": "error", "doc": "docs/", "message": ".harness/docs/ 디렉토리가 없습니다."}],
        }

    required_docs = REQUIRED_DOCS_BY_STAGE.get(stage, REQUIRED_DOCS_BY_STAGE["mvp"])

    # 디렉토리화된 문서도 인식: SCHEMA/ → SCHEMA, API_GUIDE/ → API_GUIDE 등
    existing_stems: set[str] = set()
    for p in DOCS_DIR.glob("*.md"):
        existing_stems.add(p.stem)
    for p in DOCS_DIR.iterdir():
        if p.is_dir() and (p / "INDEX.md").exists():
            existing_stems.add(p.name)

    all_issues: list[dict] = []

    # 필수 문서 존재 여부
    for doc_name in required_docs:
        if doc_name not in existing_stems:
            all_issues.append({
                "level": "error",
                "doc": doc_name,
                "message": (
                    f".harness/docs/{doc_name}.md 또는 "
                    f".harness/docs/{doc_name}/INDEX.md 파일이 없습니다 ({stage} 단계 필수)"
                ),
            })

    # 각 문서 내용 검사 (단일 파일)
    for path in sorted(DOCS_DIR.glob("*.md")):
        all_issues.extend(check_file(path, stage))

    # 디렉토리화된 문서 내용 검사 (INDEX.md + 하위 파일)
    for sub_dir in sorted(DOCS_DIR.iterdir()):
        if sub_dir.is_dir():
            for path in sorted(sub_dir.glob("*.md")):
                all_issues.extend(check_file(path, stage))

    errors = sum(1 for i in all_issues if i["level"] == "error")
    warnings = sum(1 for i in all_issues if i["level"] == "warning")
    info = sum(1 for i in all_issues if i["level"] == "info")

    return {
        "stage": stage,
        "summary": {"errors": errors, "warnings": warnings, "info": info},
        "issues": all_issues,
    }


def _print_human(result: dict):
    summary = result["summary"]
    print(f"\n[docs 검증] stage={result['stage']}")
    print(f"  오류: {summary['errors']}  경고: {summary['warnings']}  정보: {summary['info']}")

    by_level = {"error": "✗", "warning": "⚠", "info": "ℹ"}
    for issue in result["issues"]:
        icon = by_level.get(issue["level"], "·")
        print(f"  {icon} [{issue['doc']}] {issue['message']}")

    if summary["errors"] == 0 and summary["warnings"] == 0:
        print("  ✓ 문서 충실도 검사 통과")


def main():
    parser = argparse.ArgumentParser(description="docs/ 충실도 검사기")
    parser.add_argument(
        "--stage",
        choices=["prototype", "mvp", "production"],
        default="mvp",
        help="프로젝트 단계 (기본: mvp)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    # .harness/profile.json에서 stage 자동 감지 (--stage 없을 때)
    profile_path = ROOT / ".harness" / "profile.json"
    effective_stage = args.stage
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            effective_stage = profile.get("stage", args.stage)
        except (json.JSONDecodeError, OSError):
            pass

    result = validate(effective_stage)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)

    sys.exit(1 if result["summary"]["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
