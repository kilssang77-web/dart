#!/usr/bin/env python3
"""
Stop hook용 스택 자동 감지 빌드/린트/테스트 실행기.
.claude/settings.json의 Stop hook에서 호출된다.

스택 감지:
  - package.json       → npm run lint && npm run build && npm test
  - pom.xml            → mvn -q -DskipITs verify
  - build.gradle*      → ./gradlew build
  - 모노레포(동시 존재) → 순차 실행

production 단계이면 보안 스캔을 추가로 실행한다.
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_exe(name: str) -> str | None:
    """실행 파일 경로를 반환한다. Windows에서는 .cmd 확장자도 시도한다."""
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32":
        found = shutil.which(name + ".cmd")
        if found:
            return found
    return None


def _read_stage() -> str:
    """profile.json에서 stage를 읽는다. 없으면 'mvp'."""
    profile = ROOT / ".harness" / "profile.json"
    try:
        return json.loads(profile.read_text("utf-8")).get("stage", "mvp")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "mvp"


def _run(cmd: list[str], cwd: Path, label: str) -> int:
    """명령을 실행하고 출력을 스트리밍한다. 종료 코드를 반환한다."""
    print(f"\n[run_checks] {label}")
    print(f"  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=str(cwd), text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        print(f"  ✗ {label}: 실행 파일을 찾을 수 없음 — PATH를 확인하세요.")
        return 1
    if result.returncode != 0:
        print(f"  ✗ {label} 실패 (exit {result.returncode})")
    else:
        print(f"  ✓ {label} 통과")
    return result.returncode


def _npm_scripts_exist(pkg_path: Path, *scripts: str) -> list[str]:
    """package.json에 정의된 스크립트 중 존재하는 것만 반환한다."""
    try:
        pkg = json.loads(pkg_path.read_text("utf-8"))
        defined = pkg.get("scripts", {})
        return [s for s in scripts if s in defined]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def check_npm(stage: str) -> int:
    """Frontend — npm 스택 검사."""
    npm = _resolve_exe("npm")
    if npm is None:
        print("[run_checks] npm을 PATH에서 찾을 수 없음 — npm 검사 스킵")
        return 0

    pkg_json = ROOT / "package.json"
    fe_pkg = ROOT / "frontend" / "package.json"

    target = None
    if fe_pkg.exists():
        target = fe_pkg.parent
    elif pkg_json.exists():
        target = ROOT

    if target is None:
        return 0

    pkg_path = target / "package.json"
    scripts = _npm_scripts_exist(pkg_path, "lint", "build", "test")
    if not scripts:
        print("[run_checks] npm: 실행할 스크립트 없음 (lint/build/test 미정의)")
        return 0

    failures = 0
    for script in scripts:
        rc = _run([npm, "run", script], target, f"npm run {script}")
        if rc != 0:
            failures += 1

    if stage == "production" and failures == 0:
        rc = _run([npm, "audit", "--audit-level=high"], target, "npm audit (보안 스캔)")
        if rc != 0:
            failures += 1

    return failures


def check_gradle(stage: str) -> int:
    """Backend — Gradle 스택 검사."""
    be_build = ROOT / "backend" / "build.gradle"
    be_build_kts = ROOT / "backend" / "build.gradle.kts"
    root_build = ROOT / "build.gradle"
    root_build_kts = ROOT / "build.gradle.kts"

    target = None
    if be_build.exists() or be_build_kts.exists():
        target = ROOT / "backend"
    elif root_build.exists() or root_build_kts.exists():
        target = ROOT

    if target is None:
        return 0

    # Windows는 gradlew.bat, Unix는 gradlew 사용
    gradlew_bat = target / "gradlew.bat"
    gradlew_sh = target / "gradlew"
    if sys.platform == "win32" and gradlew_bat.exists():
        gradle_cmd = [str(gradlew_bat)]
    elif gradlew_sh.exists():
        gradle_cmd = [str(gradlew_sh)]
    else:
        gradle_exe = _resolve_exe("gradle")
        if gradle_exe is None:
            print("[run_checks] gradle을 PATH에서 찾을 수 없음 — Gradle 검사 스킵")
            return 0
        gradle_cmd = [gradle_exe]

    failures = 0
    rc = _run(gradle_cmd + ["build"], target, "Gradle build")
    if rc != 0:
        failures += 1

    if stage == "production" and failures == 0:
        # OWASP Dependency Check — 플러그인이 없으면 무시
        try:
            r = subprocess.run(
                gradle_cmd + ["dependencyCheckAnalyze", "--info"],
                cwd=str(target), capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        except FileNotFoundError:
            print("[run_checks] Gradle: dependencyCheckAnalyze 실행 파일 없음 — 스킵")
            return failures
        if "Task :dependencyCheckAnalyze" in r.stdout or r.returncode == 0:
            if r.returncode != 0:
                print("[run_checks] ✗ Gradle dependencyCheckAnalyze 실패")
                failures += 1
            else:
                print("[run_checks] ✓ Gradle dependencyCheckAnalyze 통과")
        else:
            print("[run_checks] Gradle: dependencyCheckAnalyze 플러그인 없음 — 스킵")

    return failures


def check_maven(stage: str) -> int:
    """Backend — Maven 스택 검사."""
    mvn = _resolve_exe("mvn")
    if mvn is None:
        print("[run_checks] mvn을 PATH에서 찾을 수 없음 — Maven 검사 스킵")
        return 0

    be_pom = ROOT / "backend" / "pom.xml"
    root_pom = ROOT / "pom.xml"

    target = None
    if be_pom.exists():
        target = ROOT / "backend"
    elif root_pom.exists():
        target = ROOT

    if target is None:
        return 0

    failures = 0
    rc = _run([mvn, "-q", "-DskipITs", "verify"], target, "Maven verify")
    if rc != 0:
        failures += 1

    if stage == "production" and failures == 0:
        rc = _run(
            [mvn, "-q", "org.owasp:dependency-check-maven:check"],
            target, "Maven OWASP dependency check"
        )
        if rc != 0:
            failures += 1

    return failures


def check_ci_gate(stage: str) -> int:
    """production 단계 — ci_gate.py를 실행하고 실패 수를 반환한다."""
    ci_gate = ROOT / ".harness" / "scripts" / "ci_gate.py"
    if not ci_gate.exists():
        print("[run_checks] ci_gate.py 없음 — 스킵")
        return 0

    print(f"\n[run_checks] CI 게이트 검사 (stage={stage})")
    result = subprocess.run(
        [sys.executable, str(ci_gate), "--stage", stage],
        cwd=str(ROOT), text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print("  ✗ CI 게이트 실패 — 위 항목을 확인하세요.")
        return 1
    print("  ✓ CI 게이트 통과")
    return 0


def main() -> int:
    # 환경변수로 명시적 스킵 지원 (긴급 상황)
    if os.environ.get("A2M_SKIP_CHECKS", "").lower() in ("1", "true", "yes"):
        print("[run_checks] A2M_SKIP_CHECKS=1 — 검사 건너뜀")
        return 0

    stage = _read_stage()
    print(f"[run_checks] stage={stage}")

    total_failures = 0
    total_failures += check_npm(stage)
    total_failures += check_gradle(stage)
    total_failures += check_maven(stage)

    if stage == "production":
        total_failures += check_ci_gate(stage)

    if total_failures == 0:
        print(f"\n[run_checks] ✓ 모든 검사 통과")
    else:
        print(f"\n[run_checks] ✗ {total_failures}개 검사 실패")

    return min(total_failures, 1)  # Stop hook은 0/1만 의미 있음


if __name__ == "__main__":
    sys.exit(main())
