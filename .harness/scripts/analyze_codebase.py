#!/usr/bin/env python3
"""
기존 코드베이스를 분석하여 docs/* 초안을 생성한다.
/a2m_start EXISTING 모드에서 사용자가 "예"를 선택했을 때 호출된다.

분석 항목:
  - 스택/의존성: package.json, pom.xml, build.gradle
  - 디렉토리 트리 (3단계)
  - 진입점: Application.java, main.tsx, index.tsx
  - README/기존 문서
  - CI 설정: .github/, .gitlab-ci.yml

Usage:
    python .harness/scripts/analyze_codebase.py [--output-dir .harness/docs/] [--json]
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


def _read_safe(path: Path, max_lines: int = 200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... (이하 {len(lines) - max_lines}줄 생략)"
        return text
    except OSError:
        return ""


def _tree(directory: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
    """디렉토리 트리를 문자열 목록으로 반환한다."""
    if depth > max_depth:
        return []

    lines = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return []

    skip = {".git", "node_modules", "__pycache__", ".gradle", "build",
            "target", "dist", ".next", "out", ".harness"}
    children = [c for c in children if c.name not in skip]

    for i, child in enumerate(children):
        is_last = (i == len(children) - 1)
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{child.name}{'/' if child.is_dir() else ''}")
        if child.is_dir():
            extension = "    " if is_last else "│   "
            lines.extend(_tree(child, prefix + extension, depth + 1, max_depth))

    return lines


def _detect_java_stack(root: Path) -> dict:
    """Spring Boot / Java 스택을 감지한다."""
    result = {"framework": None, "version": None, "java_version": None, "dependencies": []}

    # pom.xml
    pom_candidates = list(root.glob("**/pom.xml"))
    if pom_candidates:
        pom = pom_candidates[0].read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"spring-boot.*?<version>([^<]+)</version>", pom, re.DOTALL)
        if m:
            result["framework"] = "spring-boot"
            result["version"] = m.group(1).strip()
        m_java = re.search(r"<java.version>([^<]+)</java.version>", pom)
        if m_java:
            result["java_version"] = m_java.group(1).strip()
        deps = re.findall(r"<artifactId>([^<]+)</artifactId>", pom)
        result["dependencies"] = list({d for d in deps if "spring" in d.lower() or "jpa" in d.lower()})[:10]

    # build.gradle
    gradle_candidates = list(root.glob("**/build.gradle")) + list(root.glob("**/build.gradle.kts"))
    if gradle_candidates and not result["framework"]:
        content = gradle_candidates[0].read_text(encoding="utf-8", errors="ignore")
        if "spring-boot" in content:
            result["framework"] = "spring-boot"
            m = re.search(r"springBoot.*?(\d+\.\d+\.\d+)", content)
            if m:
                result["version"] = m.group(1)

    return result


def _detect_node_stack(root: Path) -> dict:
    """Node.js / React 스택을 감지한다."""
    result = {"framework": None, "version": None, "dependencies": [], "devDependencies": []}

    pkg_candidates = [
        root / "frontend" / "package.json",
        root / "package.json",
    ]

    for pkg_path in pkg_candidates:
        if not pkg_path.exists():
            continue
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})

        if "react" in deps:
            result["framework"] = "react"
            result["version"] = deps["react"]
        elif "next" in deps:
            result["framework"] = "nextjs"
            result["version"] = deps["next"]

        result["dependencies"] = list(deps.keys())[:15]
        result["devDependencies"] = list(dev_deps.keys())[:10]
        break

    return result


def _detect_db_migrations(root: Path) -> dict:
    """Flyway / Liquibase 마이그레이션 파일을 탐지하고 요약한다."""
    result = {
        "tool": None,
        "migration_dir": None,
        "file_count": 0,
        "tables": [],
        "files": [],
    }

    # Flyway: V{n}__{name}.sql
    flyway_dirs = [
        root / "src" / "main" / "resources" / "db" / "migration",
        root / "backend" / "src" / "main" / "resources" / "db" / "migration",
    ]
    flyway_patterns = ["V*.sql", "R*.sql", "U*.sql"]

    for migration_dir in flyway_dirs:
        sql_files: list[Path] = []
        for pat in flyway_patterns:
            sql_files.extend(sorted(migration_dir.glob(pat)))
        if sql_files:
            result["tool"] = "flyway"
            result["migration_dir"] = str(migration_dir.relative_to(root)).replace("\\", "/")
            result["file_count"] = len(sql_files)
            result["files"] = [f.name for f in sql_files[:20]]

            # CREATE TABLE 구문에서 테이블 이름 추출
            tables = set()
            for sql_file in sql_files:
                content = _read_safe(sql_file, 200)
                for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?(\w+)[`\"]?", content, re.IGNORECASE):
                    tables.add(m.group(1).lower())
            result["tables"] = sorted(tables)
            break

    if result["tool"]:
        return result

    # Liquibase: changelog 파일
    liquibase_candidates = list(root.glob("**/db/changelog/**/*.xml")) + list(root.glob("**/db/changelog/**/*.yaml")) + list(root.glob("**/db/changelog/**/*.sql"))
    if liquibase_candidates:
        result["tool"] = "liquibase"
        result["migration_dir"] = str(liquibase_candidates[0].parent.relative_to(root)).replace("\\", "/")
        result["file_count"] = len(liquibase_candidates)
        result["files"] = [f.name for f in liquibase_candidates[:20]]

    return result


def _generate_schema_draft(analysis: dict) -> str:
    """마이그레이션 분석 결과로 SCHEMA.md 초안을 생성한다."""
    db = analysis.get("db_migrations", {})

    tool_info = f"마이그레이션 도구: {db.get('tool', '미감지')}"
    dir_info = f"마이그레이션 위치: `{db.get('migration_dir', '-')}`" if db.get("migration_dir") else ""
    tables_info = ""
    if db.get("tables"):
        tables_info = "### 감지된 테이블\n" + "\n".join(f"- `{t}`" for t in db["tables"])
    files_info = ""
    if db.get("files"):
        files_info = "### 마이그레이션 파일 목록\n" + "\n".join(f"- `{f}`" for f in db["files"])

    existing = ""
    schema_path = ROOT / ".harness" / "docs" / "SCHEMA.md"
    if schema_path.exists():
        existing = schema_path.read_text(encoding="utf-8")

    return f"""<!-- AUTO-GENERATED by analyze_codebase.py — 내용을 검토하고 수정하세요 -->

> 이 문서는 코드베이스 자동 분석으로 생성된 초안입니다. 실제 내용으로 보완하세요.

# 데이터베이스 스키마 (초안)

## 자동 감지 결과

- {tool_info}
- {dir_info}

{tables_info}

{files_info}

---

{existing}
"""


def _detect_stage_hint(root: Path) -> str:
    """CI 설정, 테스트 규모, docker 존재로 단계 힌트를 추론한다."""
    hints = []

    # CI 설정
    if (root / ".github" / "workflows").is_dir():
        hints.append("github-actions")
    if (root / ".gitlab-ci.yml").exists():
        hints.append("gitlab-ci")

    # Docker/Kubernetes
    if (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists():
        hints.append("docker-compose")
    if (root / "kubernetes").is_dir() or (root / "k8s").is_dir():
        hints.append("kubernetes")

    # 테스트 규모
    test_files = list(root.glob("**/*Test.java")) + list(root.glob("**/*.test.ts")) + list(root.glob("**/*.spec.ts"))
    test_count = len(test_files)

    if "kubernetes" in hints or test_count > 50:
        return "production"
    elif ("docker-compose" in hints or test_count > 10) and ("github-actions" in hints or "gitlab-ci" in hints):
        return "mvp"
    else:
        return "prototype"


def _find_entry_points(root: Path) -> list[str]:
    """주요 진입점 파일을 탐색한다."""
    entries = []
    candidates = [
        "**/Application.java", "**/App.java",
        "**/main.tsx", "**/main.ts",
        "**/index.tsx", "**/index.ts",
        "**/manage.py",
    ]
    for pattern in candidates:
        for match in root.glob(pattern):
            rel = str(match.relative_to(root)).replace("\\", "/")
            if "node_modules" not in rel and ".gradle" not in rel and "build/" not in rel:
                entries.append(rel)

    return entries[:5]


def analyze(root: Path = ROOT) -> dict:
    """코드베이스를 분석하고 결과를 반환한다."""
    java_stack = _detect_java_stack(root)
    node_stack = _detect_node_stack(root)
    db_migrations = _detect_db_migrations(root)
    stage_hint = _detect_stage_hint(root)
    entry_points = _find_entry_points(root)

    tree_lines = [f"{root.name}/"] + _tree(root)
    dir_tree = "\n".join(tree_lines)

    readme = ""
    for candidate in ["README.md", "README.rst", "README.txt"]:
        p = root / candidate
        if p.exists():
            readme = _read_safe(p, 100)
            break

    return {
        "stage_hint": stage_hint,
        "java_stack": java_stack,
        "node_stack": node_stack,
        "db_migrations": db_migrations,
        "entry_points": entry_points,
        "dir_tree": dir_tree,
        "readme": readme,
        "has_docker": (root / "docker-compose.yml").exists() or (root / "Dockerfile").exists(),
        "has_ci": (root / ".github" / "workflows").is_dir() or (root / ".gitlab-ci.yml").exists(),
    }


def _generate_architecture_draft(analysis: dict) -> str:
    """분석 결과로 ARCHITECTURE.md 초안을 생성한다."""
    java = analysis["java_stack"]
    node = analysis["node_stack"]

    stack_desc = []
    if java.get("framework"):
        stack_desc.append(f"Backend: {java['framework']} {java.get('version', '')}")
    if node.get("framework"):
        stack_desc.append(f"Frontend: {node['framework']} {node.get('version', '')}")

    existing_arch = ""
    arch_path = ROOT / ".harness" / "docs" / "ARCHITECTURE.md"
    if arch_path.exists():
        existing_arch = arch_path.read_text(encoding="utf-8")

    return f"""<!-- AUTO-GENERATED by analyze_codebase.py — 내용을 검토하고 수정하세요 -->

> 이 문서는 코드베이스 자동 분석으로 생성된 초안입니다. 실제 내용으로 보완하세요.

# 아키텍처 (초안)

## 감지된 스택
{chr(10).join(f'- {s}' for s in stack_desc) or '- (감지된 스택 없음)'}

## 디렉토리 구조 (자동 감지)

```
{analysis['dir_tree']}
```

## 진입점
{chr(10).join(f'- `{e}`' for e in analysis['entry_points']) or '- (감지 없음)'}

## 기반 설정
- Docker: {'있음' if analysis['has_docker'] else '없음'}
- CI/CD: {'있음' if analysis['has_ci'] else '없음'}

---

{existing_arch}
"""


def _generate_prd_draft(analysis: dict) -> str:
    """분석 결과로 PRD.md 초안을 생성한다."""
    readme = analysis.get("readme", "")
    prd_path = ROOT / ".harness" / "docs" / "PRD.md"
    existing = prd_path.read_text(encoding="utf-8") if prd_path.exists() else ""

    return f"""<!-- AUTO-GENERATED by analyze_codebase.py — 내용을 검토하고 수정하세요 -->

> 이 문서는 코드베이스 자동 분석으로 생성된 초안입니다. 실제 내용으로 보완하세요.

# PRD (초안)

## 기존 README 발췌 (목표 섹션 참고용)

{readme[:500] if readme else '(README 없음)'}

---

{existing}
"""


def main():
    parser = argparse.ArgumentParser(description="코드베이스 자동 분석기")
    parser.add_argument("--output-dir", default="", help="초안 저장 디렉토리 (비어 있으면 출력만)")
    parser.add_argument("--json", action="store_true", help="분석 결과를 JSON으로 출력")
    args = parser.parse_args()

    print("[analyze_codebase] 코드베이스 분석 중...", file=sys.stderr)
    result = analyze()

    if args.json:
        safe_result = {k: v for k, v in result.items() if k != "readme"}
        print(json.dumps(safe_result, ensure_ascii=False, indent=2))
        return

    print(f"\n[analyze_codebase] 분석 결과")
    print(f"  단계 힌트:    {result['stage_hint']}")
    print(f"  Backend:     {result['java_stack'].get('framework') or '없음'} {result['java_stack'].get('version', '')}")
    print(f"  Frontend:    {result['node_stack'].get('framework') or '없음'} {result['node_stack'].get('version', '')}")
    db = result["db_migrations"]
    if db.get("tool"):
        print(f"  DB 마이그레이션: {db['tool']} — {db['file_count']}개 파일, 테이블 {len(db['tables'])}개 감지")
    else:
        print(f"  DB 마이그레이션: 감지 없음")
    print(f"  진입점:      {result['entry_points']}")
    print(f"  Docker:      {'있음' if result['has_docker'] else '없음'}")
    print(f"  CI/CD:       {'있음' if result['has_ci'] else '없음'}")

    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # ARCHITECTURE.md 초안
        arch_draft = _generate_architecture_draft(result)
        arch_out = out_dir / "ARCHITECTURE.draft.md"
        arch_out.write_text(arch_draft, encoding="utf-8")
        print(f"\n[analyze_codebase] 초안 생성: {arch_out}")

        # PRD.md 초안
        prd_draft = _generate_prd_draft(result)
        prd_out = out_dir / "PRD.draft.md"
        prd_out.write_text(prd_draft, encoding="utf-8")
        print(f"[analyze_codebase] 초안 생성: {prd_out}")

        # SCHEMA.md 초안 (마이그레이션 파일이 있을 때)
        if db.get("tool") or db.get("tables"):
            schema_draft = _generate_schema_draft(result)
            schema_out = out_dir / "SCHEMA.draft.md"
            schema_out.write_text(schema_draft, encoding="utf-8")
            print(f"[analyze_codebase] 초안 생성: {schema_out}")

        print(f"\n  다음 단계: 초안 파일을 검토하고 승인하면 실제 .harness/docs/*.md로 복사하세요.")

    print(f"\n  추천 단계: {result['stage_hint']}")


if __name__ == "__main__":
    main()
