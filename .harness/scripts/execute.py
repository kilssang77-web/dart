#!/usr/bin/env python3
"""
Harness Step Executor — phases/<task>/<runId>/ 구조로 step을 순차 실행한다.

Usage:
    # 새 run (task 이름만)
    python3 scripts/execute.py <task>

    # 특정 run 지정
    python3 scripts/execute.py <task>/<runId>

    # 가장 최근 미완료 run 자동 재개
    python3 scripts/execute.py --resume

    # 특정 task의 가장 최근 run
    python3 scripts/execute.py --latest <task>

    # 옵션
    python3 scripts/execute.py <task> --push --auto-review --pr --skip-preflight
    python3 scripts/execute.py <task> --no-release-note --detailed-release-notes
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).parent))

try:
    from _resumable import scan_resumable_runs, first_pending_step, is_resumable_state
except ImportError:
    def scan_resumable_runs(d): return []  # type: ignore
    def first_pending_step(i): return None  # type: ignore
    def is_resumable_state(s): return s in ("pending", "blocked", "error")  # type: ignore


@contextlib.contextmanager
def progress_indicator(label: str):
    frames = "◐◓◑◒"
    stop = threading.Event()
    t0 = time.monotonic()

    def _animate():
        idx = 0
        while not stop.wait(0.12):
            sec = int(time.monotonic() - t0)
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {label} [{sec}s]")
            sys.stderr.flush()
            idx += 1
        sys.stderr.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stderr.flush()

    th = threading.Thread(target=_animate, daemon=True)
    th.start()
    info = types.SimpleNamespace(elapsed=0.0)
    try:
        yield info
    finally:
        stop.set()
        th.join()
        info.elapsed = time.monotonic() - t0


class StepExecutor:
    MAX_RETRIES = 3
    FEAT_MSG = "{type}({task}): step {num} — {name}"
    CHORE_MSG = "chore({task}): step {num} output"

    _STEP_TYPE_HEURISTICS = [
        (re.compile(r"(fix|버그|오류|수정|patch)", re.IGNORECASE), "fix"),
        (re.compile(r"(refactor|리팩|정리|cleanup)", re.IGNORECASE), "refactor"),
        (re.compile(r"(test|테스트|spec)", re.IGNORECASE), "test"),
        (re.compile(r"(docs|문서|document)", re.IGNORECASE), "docs"),
        (re.compile(r"(chore|설정|config|인프라|lint)", re.IGNORECASE), "chore"),
        (re.compile(r"(perf|성능|optimize)", re.IGNORECASE), "perf"),
    ]
    TZ = timezone(timedelta(hours=9))
    OUTPUT_MAX_BYTES = 4096  # step output.json 요약 상한

    def __init__(
        self,
        task: str,
        run_id: str,
        *,
        auto_push: bool = False,
        auto_review: bool = False,
        create_pr: bool = False,
        skip_preflight: bool = False,
        no_release_note: bool = False,
        detailed_release_notes: bool = False,
        takeover_from: str = "",
        run_as: str = "",
        no_chore_commit: bool = False,
        squash_on_finalize: bool = False,
    ):
        self._root = str(ROOT)
        self._phases_dir = ROOT / ".harness" / "phases"
        self._task = task
        self._run_id = run_id
        self._run_dir = self._phases_dir / task / run_id
        self._auto_push = auto_push
        self._auto_review = auto_review
        self._create_pr = create_pr
        self._skip_preflight = skip_preflight
        self._no_release_note = no_release_note
        self._detailed_release_notes = detailed_release_notes
        self._takeover_from = takeover_from
        self._run_as = run_as
        self._no_chore_commit = no_chore_commit
        self._squash_on_finalize = squash_on_finalize

        if not self._run_dir.is_dir():
            print(f"ERROR: {self._run_dir} not found")
            sys.exit(1)

        self._index_file = self._run_dir / "index.json"
        if not self._index_file.exists():
            print(f"ERROR: {self._index_file} not found")
            sys.exit(1)

        idx = self._read_json(self._index_file)
        self._project = idx.get("project", "project")
        self._phase_name = idx.get("phase", task)
        self._total = len(idx["steps"])

        # 가드레일 캐시 파일
        self._guardrail_hash_file = self._run_dir / ".guardrail_hash"

    # ─── 타임스탬프 ───

    def _stamp(self) -> str:
        return datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # ─── JSON I/O ───

    @staticmethod
    def _read_json(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(p: Path, data: dict):
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ─── git ───

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        cmd = ["git"] + list(args)
        return subprocess.run(cmd, cwd=self._root, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def _branch_name(self) -> str:
        """PR 단위 브랜치명: feat/<task>-<runId> (run 1개 = PR 1개)."""
        return f"feat/{self._task}-{self._run_id}"

    def _checkout_branch(self):
        branch = self._branch_name()
        r = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            print(f"  ERROR: git을 사용할 수 없거나 git repo가 아닙니다.")
            sys.exit(1)
        if r.stdout.strip() == branch:
            return
        r = self._run_git("rev-parse", "--verify", branch)
        r = (self._run_git("checkout", branch)
             if r.returncode == 0
             else self._run_git("checkout", "-b", branch))
        if r.returncode != 0:
            print(f"  ERROR: 브랜치 '{branch}' checkout 실패: {r.stderr.strip()}")
            sys.exit(1)
        print(f"  Branch: {branch}")

    def _infer_commit_type(self, step_num: int, step_name: str) -> str:
        """step frontmatter의 commit_type을 읽거나 이름에서 휴리스틱으로 추론한다."""
        fm = self._parse_step_frontmatter(step_num)
        explicit = fm.get("commit_type", "")
        if explicit and explicit in ("feat", "fix", "refactor", "test", "docs", "chore", "perf"):
            return explicit
        for pattern, ctype in self._STEP_TYPE_HEURISTICS:
            if pattern.search(step_name):
                return ctype
        return "feat"

    def _get_paths_allow(self, step_num: int) -> list[str] | None:
        """step frontmatter의 paths_allow를 반환한다. None이면 run 폴더만 허용."""
        fm = self._parse_step_frontmatter(step_num)
        return fm.get("paths_allow")  # None 또는 list[str]

    def _commit_step(self, step_num: int, step_name: str):
        run_rel = f".harness/phases/{self._task}/{self._run_id}"
        output_rel = f"{run_rel}/step{step_num}-output.json"
        index_rel = f"{run_rel}/index.json"

        # paths_allow 기반 add — git add -A 대신 명시 경로만 add
        paths_allow = self._get_paths_allow(step_num)
        if paths_allow is not None:
            # frontmatter 명시 경로 + run 폴더
            add_paths = list(paths_allow) + [run_rel]
        else:
            # 기본: run 폴더만 (공유 상태 오염 방지)
            add_paths = [run_rel]

        for p in add_paths:
            self._run_git("add", "--", p)

        # output.json · index.json은 chore 커밋으로 분리
        self._run_git("reset", "HEAD", "--", output_rel)
        self._run_git("reset", "HEAD", "--", index_rel)

        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            commit_type = self._infer_commit_type(step_num, step_name)
            msg = self.FEAT_MSG.format(type=commit_type, task=self._task, num=step_num, name=step_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")
            else:
                print(f"  WARN: 코드 커밋 실패: {r.stderr.strip()}")

        if not self._no_chore_commit:
            for p in add_paths:
                self._run_git("add", "--", p)
            if self._run_git("diff", "--cached", "--quiet").returncode != 0:
                msg = self.CHORE_MSG.format(task=self._task, num=step_num)
                self._run_git("commit", "-m", msg)

    # ─── 글로벌 레지스트리 ───

    def _update_top_index(self, status: str):
        top_path = self._phases_dir / "index.json"
        if not top_path.exists():
            return
        top = self._read_json(top_path)
        ts = self._stamp()
        run_dir_rel = f"{self._task}/{self._run_id}"
        for run in top.get("runs", []):
            if run.get("dir") == run_dir_rel:
                run["status"] = status
                ts_key = {
                    "completed": "completed_at",
                    "error": "failed_at",
                    "blocked": "blocked_at",
                }.get(status)
                if ts_key:
                    run[ts_key] = ts
                break
        self._write_json(top_path, top)

    # ─── 프리플라이트 ───

    def _preflight(self):
        if self._skip_preflight:
            print("  [preflight] --skip-preflight: 건너뜀")
            return

        print("\n[Preflight 검사]")

        # 1. 작업 트리 클린 확인
        r = self._run_git("status", "--porcelain")
        if r.returncode == 0 and r.stdout.strip():
            unstaged = r.stdout.strip()
            print(f"  ⚠ 커밋되지 않은 변경사항이 있습니다:")
            print(f"    {unstaged[:200]}")
            noninteractive = (
                os.environ.get("A2M_NONINTERACTIVE", "").lower() in ("1", "true", "yes")
                or not sys.stdin.isatty()
            )
            if noninteractive:
                print("  비대화형 환경 감지 — 변경사항이 있어 자동으로 중단합니다.")
                print("  Hint: --skip-preflight 플래그로 이 검사를 건너뛸 수 있습니다.")
                sys.exit(1)
            answer = input("  계속 진행하시겠습니까? [y/N] ").strip().lower()
            if answer != "y":
                print("  변경사항을 커밋하거나 stash 후 다시 시도하세요.")
                sys.exit(1)

        # 2. profile.json 존재 확인
        profile_path = ROOT / ".harness" / "profile.json"
        if not profile_path.exists():
            print("  ✗ .harness/profile.json이 없습니다.")
            print("  /a2m_start 또는 /a2m_docs 명령으로 프로젝트 단계를 먼저 설정하세요.")
            sys.exit(1)

        profile = self._read_json(profile_path) if profile_path.exists() else {}
        stage = profile.get("stage", "prototype")
        print(f"  ✓ 프로젝트 단계: {stage}")

        # 3. docs 충실도 검사 (경고 수준)
        try:
            result = subprocess.run(
                [sys.executable, ".harness/scripts/validate_docs.py", "--stage", stage, "--json"],
                cwd=self._root, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                val = json.loads(result.stdout)
                errors = val.get("summary", {}).get("errors", 0)
                warnings = val.get("summary", {}).get("warnings", 0)
                if errors > 0:
                    print(f"  ⚠ docs 검증: {errors}개 오류, {warnings}개 경고")
                    print("  문서를 보완하거나 --skip-preflight로 우회하세요.")
                    answer = input("  오류가 있어도 계속 진행하시겠습니까? [y/N] ").strip().lower()
                    if answer != "y":
                        sys.exit(1)
                else:
                    print(f"  ✓ docs 검증: 오류 없음 ({warnings}개 경고)")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            print("  ⚠ docs 검증 스크립트 실행 실패 — 건너뜀")

        # 4. production 단계: 캐시된 페르소나 리뷰 점수 확인 (경고만, LLM 호출 안 함)
        if stage == "production":
            review_cache_dir = ROOT / ".harness" / "docs" / ".review"
            if review_cache_dir.is_dir():
                candidates = sorted(review_cache_dir.glob(f"{stage}_*.json"), reverse=True)
                if candidates:
                    try:
                        cached = json.loads(candidates[0].read_text(encoding="utf-8"))
                        cached_verdict = cached.get("verdict", "unknown")
                        cached_avg = cached.get("average", 0)
                        cached_threshold = cached.get("threshold", 90)
                        if cached_verdict == "fail":
                            print(f"  ⚠ 캐시된 페르소나 리뷰: 미통과 (평균 {cached_avg:.1f} / 임계 {cached_threshold})")
                            print("  /a2m_check_docs 또는 review_docs.py로 문서를 보완하세요.")
                        else:
                            print(f"  ✓ 캐시된 페르소나 리뷰: 통과 (평균 {cached_avg:.1f}점)")
                    except (json.JSONDecodeError, OSError):
                        pass

        # 5. production 단계: 보안 스캔
        if stage == "production":
            self._run_security_scan()

        print()

    def _run_security_scan(self):
        """production 단계에서 보안 스캔을 실행한다."""
        print("  [보안 스캔 — production 단계]")

        # npm audit
        npm = shutil.which("npm") or (shutil.which("npm.cmd") if sys.platform == "win32" else None)
        if npm is None:
            print("  ⚠ npm audit: npm을 PATH에서 찾을 수 없음 — 스킵")
        else:
            for npm_pkg in [ROOT / "frontend" / "package.json", ROOT / "package.json"]:
                if npm_pkg.exists():
                    try:
                        r = subprocess.run(
                            [npm, "audit", "--audit-level=high"],
                            cwd=str(npm_pkg.parent), capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
                        )
                        if r.returncode != 0:
                            print("  ⚠ npm audit: 취약점 발견. 상세 내용을 확인하세요.")
                        else:
                            print("  ✓ npm audit: 통과")
                    except FileNotFoundError:
                        print("  ⚠ npm audit: 실행 파일을 찾을 수 없음 — 스킵")
                    break

    # ─── 가드레일 & 컨텍스트 ───

    def _load_profile_section(self) -> str:
        """profile.json 기반 가드레일 섹션을 생성한다."""
        profile_path = ROOT / ".harness" / "profile.json"
        if not profile_path.exists():
            return ""

        profile = self._read_json(profile_path)
        stage = profile.get("stage", "mvp")

        requirements = {
            "prototype": [
                "빌드가 통과해야 한다.",
                "핵심 기능이 동작해야 한다.",
            ],
            "mvp": [
                "빌드 + 단위 테스트가 통과해야 한다.",
                "외부 입력 검증 및 기본 에러 핸들링이 있어야 한다.",
                "비밀값은 환경변수로 관리한다.",
            ],
            "production": [
                "모든 신규 함수에 단위 테스트가 있어야 한다.",
                "외부 입력 검증 및 에러 핸들링이 완비되어야 한다.",
                "로깅(레벨 구분), 메트릭 노출 지점이 있어야 한다.",
                "비밀값은 환경변수, 절대 하드코딩 금지.",
                "보안 스캔(npm audit/dependencyCheck) 통과 기준.",
            ],
        }

        reqs = requirements.get(stage, requirements["mvp"])
        reqs_text = "\n".join(f"- {r}" for r in reqs)

        return (
            f"## 프로젝트 단계: {stage}\n\n"
            f"이 단계의 코드는 다음을 만족해야 합니다:\n"
            f"{reqs_text}\n"
        )

    def _load_references_section(self, relevant_refs: Optional[list[str]] = None) -> str:
        """references.json 기반 가드레일 섹션을 생성한다."""
        refs_path = ROOT / ".harness" / "references.json"
        if not refs_path.exists():
            return ""

        refs_data = self._read_json(refs_path)
        refs = refs_data.get("references", [])
        if not refs:
            return ""

        if relevant_refs is not None:
            refs = [r for r in refs if r["name"] in relevant_refs]

        if not refs:
            return ""

        lines = ["## 참고 프로젝트\n"]
        for ref in refs:
            lines.append(f"### {ref['name']} ({ref.get('kind', 'git')})")
            lines.append(f"- 소스: {ref['source']}")
            lines.append(f"- 용도: {ref.get('purpose') or '(미지정)'}")

            # summary.md 읽기 (summary만 주입, 전체 소스는 filesystem MCP로)
            summary_path = ref.get("summary_path") or str(
                ROOT / ".harness" / "references" / ref["name"] / "summary.md"
            )
            sp = Path(summary_path)
            if sp.exists():
                summary = sp.read_text(encoding="utf-8", errors="ignore")
                lines.append(f"\n요약:\n{summary[:1000]}")
            lines.append("")

        return "\n".join(lines)

    def _parse_step_frontmatter(self, step_num: int) -> dict:
        """step{N}.md의 YAML frontmatter를 파싱하여 relevant_docs/references를 반환한다."""
        step_file = self._run_dir / f"step{step_num}.md"
        if not step_file.exists():
            return {}

        content = step_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return {}

        try:
            end = content.index("---", 3)
            fm_text = content[3:end]
        except ValueError:
            return {}

        result = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if line.startswith("relevant_docs:"):
                val = line.split(":", 1)[1].strip()
                if val.startswith("["):
                    import re
                    result["relevant_docs"] = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\w+)', val)
                    result["relevant_docs"] = [
                        (a or b or c).strip()
                        for a, b, c in result["relevant_docs"]
                        if (a or b or c).strip()
                    ]
            elif line.startswith("relevant_references:"):
                val = line.split(":", 1)[1].strip()
                if val.startswith("["):
                    import re
                    result["relevant_references"] = re.findall(r'"([^"]+)"|\'([^\']+)\'|(\w+)', val)
                    result["relevant_references"] = [
                        (a or b or c).strip()
                        for a, b, c in result["relevant_references"]
                        if (a or b or c).strip()
                    ]
        return result

    def _get_always_inject_docs(self) -> list[str]:
        """profile.json의 context.always_inject_docs 또는 기본값을 반환한다."""
        profile_path = ROOT / ".harness" / "profile.json"
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                ctx = profile.get("context", {})
                if "always_inject_docs" in ctx:
                    return ctx["always_inject_docs"]
            except (json.JSONDecodeError, OSError):
                pass
        return ["PRD", "CODING_CONVENTION"]

    def _get_max_doc_kb(self) -> int:
        """profile.json의 context.max_doc_kb_per_step 또는 기본값(64KB)을 반환한다."""
        profile_path = ROOT / ".harness" / "profile.json"
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                ctx = profile.get("context", {})
                if "max_doc_kb_per_step" in ctx:
                    return int(ctx["max_doc_kb_per_step"])
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        return 64

    def _read_doc(self, doc_path: Path, max_kb: int = 0) -> str:
        """문서를 읽어 최대 크기 제한을 적용한다."""
        try:
            content = doc_path.read_text(encoding="utf-8")
            if max_kb > 0 and len(content) > max_kb * 1024:
                content = content[: max_kb * 1024] + f"\n\n... (문서가 {max_kb}KB를 초과하여 잘렸습니다)"
            return content
        except OSError:
            return ""

    def _build_doc_index_line(self, doc_path: Path) -> str:
        """문서의 첫 번째 설명 줄(Tier 2 인덱스용)을 추출한다."""
        try:
            content = doc_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("<!--"):
                    return line[:80]
        except OSError:
            pass
        return ""

    def _load_guardrails(self, step_num: Optional[int] = None) -> str:
        """
        가드레일을 3-Tier 모델로 조립한다.

        Tier 1 (Always): CLAUDE.md, profile 단계 섹션, always_inject_docs (PRD, CODING_CONVENTION 기본)
        Tier 2 (Index): 나머지 docs의 이름 + 1줄 요약
        Tier 3 (On-demand): step frontmatter relevant_docs 명시분 전문
        """
        frontmatter = self._parse_step_frontmatter(step_num) if step_num is not None else {}
        relevant_docs: Optional[list[str]] = frontmatter.get("relevant_docs")
        relevant_refs: Optional[list[str]] = frontmatter.get("relevant_references")

        always_inject = set(self._get_always_inject_docs())
        max_kb = self._get_max_doc_kb()
        sections = []
        docs_dir = ROOT / ".harness" / "docs"

        # ─── Tier 1: 항상 주입 ───

        claude_md = ROOT / "CLAUDE.md"
        if claude_md.exists():
            sections.append(f"## 프로젝트 규칙 (CLAUDE.md)\n\n{self._read_doc(claude_md, max_kb)}")

        stage_section = self._load_profile_section()
        if stage_section:
            sections.append(stage_section)

        tier1_injected: set[str] = set()
        if docs_dir.is_dir():
            for doc_name in sorted(always_inject):
                doc_path = docs_dir / f"{doc_name}.md"
                if doc_path.exists():
                    sections.append(f"## {doc_name} (항상 포함)\n\n{self._read_doc(doc_path, max_kb)}")
                    tier1_injected.add(doc_name)

        # ─── Tier 3: relevant_docs 명시분 전문 주입 ───

        tier3_injected: set[str] = set()
        if relevant_docs is not None and docs_dir.is_dir():
            for doc_name in relevant_docs:
                # 점 경로 지원: "SCHEMA.users" → SCHEMA/users.md 또는 SCHEMA.md
                if "." in doc_name:
                    parts = doc_name.split(".", 1)
                    sub_path = docs_dir / parts[0] / f"{parts[1]}.md"
                    flat_path = docs_dir / f"{parts[0]}.md"
                    doc_path = sub_path if sub_path.exists() else flat_path
                    display_name = doc_name
                else:
                    doc_path = docs_dir / f"{doc_name}.md"
                    display_name = doc_name

                if doc_path.exists() and doc_name.split(".")[0] not in tier1_injected:
                    sections.append(f"## {display_name} (참조)\n\n{self._read_doc(doc_path, max_kb)}")
                    tier3_injected.add(doc_name.split(".")[0])
        elif relevant_docs is None and step_num is not None:
            print(f"  INFO: step{step_num}.md에 relevant_docs가 없습니다. Tier 2 인덱스만 주입합니다.")
            print(f"  Hint: frontmatter에 relevant_docs: [\"DOC1\", \"DOC2\"] 를 추가하세요.")

        # ─── Tier 2: 나머지 docs의 인덱스(이름 + 1줄 요약) ───

        if docs_dir.is_dir():
            index_lines = []
            for doc in sorted(docs_dir.glob("*.md")):
                stem = doc.stem
                if stem in tier1_injected or stem in tier3_injected:
                    continue
                summary = self._build_doc_index_line(doc)
                index_lines.append(f"- **{stem}**: {summary}")
            if index_lines:
                sections.append(
                    "## 참조 가능한 문서 인덱스 (Tier 2)\n"
                    "> 필요한 문서는 step frontmatter의 `relevant_docs`에 명시하세요.\n\n"
                    + "\n".join(index_lines)
                )

        # ─── Tier 4: 참고 프로젝트 ───

        refs_section = self._load_references_section(relevant_refs)
        if refs_section:
            sections.append(refs_section)

        return "\n\n---\n\n".join(sections) if sections else ""

    def _compute_guardrail_hash(self, guardrails: str) -> str:
        return hashlib.sha256(guardrails.encode("utf-8")).hexdigest()[:16]

    def _load_cached_guardrail_hash(self) -> str:
        if self._guardrail_hash_file.exists():
            return self._guardrail_hash_file.read_text(encoding="utf-8").strip()
        return ""

    def _save_guardrail_hash(self, hash_val: str):
        self._guardrail_hash_file.write_text(hash_val, encoding="utf-8")

    # ─── step context (이전 step 요약) ───

    @staticmethod
    def _build_step_context(index: dict, current_step: int) -> str:
        """이전 step 요약을 빌드한다. 최신 3개 full, 그 이전은 80자 trim."""
        completed = [
            s for s in index["steps"]
            if s["status"] == "completed" and s.get("summary") and s["step"] < current_step
        ]
        if not completed:
            return ""

        lines = []
        for i, s in enumerate(reversed(completed)):
            summary = s["summary"]
            if i >= 3:
                summary = summary[:80] + ("..." if len(summary) > 80 else "")
            lines.append(f"- Step {s['step']} ({s['name']}): {summary}")

        return "## 이전 Step 산출물\n\n" + "\n".join(lines) + "\n\n"

    def _build_preamble(
        self,
        guardrails: str,
        step_context: str,
        step_num: int,
        prev_error: Optional[str] = None,
        is_retry: bool = False,
    ) -> str:
        commit_example = self.FEAT_MSG.format(type="feat", task=self._task, num="N", name="<step-name>")

        # 가드레일 캐시 처리 — 재시도 시 변경된 부분만
        guardrail_section = guardrails
        if is_retry:
            current_hash = self._compute_guardrail_hash(guardrails)
            cached_hash = self._load_cached_guardrail_hash()
            if current_hash == cached_hash:
                guardrail_section = f"[GUARDRAIL_UNCHANGED: {current_hash}] (가드레일 변경 없음 — 이전 컨텍스트 참조)"
            else:
                self._save_guardrail_hash(current_hash)
        else:
            current_hash = self._compute_guardrail_hash(guardrails)
            self._save_guardrail_hash(current_hash)

        retry_section = ""
        if prev_error:
            # 재시도 에러 로그 1KB 상한, 핵심 오류 라인만 필터링
            import re
            error_lines = [
                l for l in prev_error.splitlines()
                if re.search(r"error|fail|exception|cannot|traceback", l, re.IGNORECASE)
            ]
            trimmed_error = "\n".join(error_lines)[:1024] or prev_error[:1024]
            retry_section = (
                f"\n## ⚠ 이전 시도 실패 — 아래 에러를 반드시 참고하여 수정하라\n\n"
                f"{trimmed_error}\n\n---\n\n"
            )

        run_rel = f".harness/phases/{self._task}/{self._run_id}"

        return (
            f"당신은 {self._project} 프로젝트의 개발자입니다. 아래 step을 수행하세요.\n\n"
            f"{guardrail_section}\n\n---\n\n"
            f"{step_context}{retry_section}"
            f"## 작업 규칙\n\n"
            f"1. 이전 step에서 작성된 코드를 확인하고 일관성을 유지하라.\n"
            f"2. 이 step에 명시된 작업만 수행하라. 추가 기능이나 파일을 만들지 마라.\n"
            f"3. 기존 테스트를 깨뜨리지 마라.\n"
            f"4. AC(Acceptance Criteria) 검증을 직접 실행하라.\n"
            f"5. /{run_rel}/index.json의 해당 step status를 업데이트하라:\n"
            f"   - AC 통과 → \"completed\" + \"summary\" 필드에 이 step의 산출물을 한 줄로 요약\n"
            f"   - {self.MAX_RETRIES}회 수정 시도 후에도 실패 → \"error\" + \"error_message\" 기록\n"
            f"   - 사용자 개입이 필요한 경우 → \"blocked\" + \"blocked_reason\" 기록 후 즉시 중단\n"
            f"6. 모든 변경사항을 커밋하라:\n"
            f"   {commit_example}\n\n---\n\n"
        )

    # ─── Claude 호출 ───

    def _invoke_claude(self, step: dict, preamble: str) -> dict:
        step_num, step_name = step["step"], step["name"]
        step_file = self._run_dir / f"step{step_num}.md"

        if not step_file.exists():
            print(f"  ERROR: {step_file} not found")
            sys.exit(1)

        prompt = preamble + step_file.read_text(encoding="utf-8")

        import shutil as _shutil
        _claude_cmd = _shutil.which("claude") or "claude"
        result = subprocess.run(
            [_claude_cmd, "-p", "--dangerously-skip-permissions", "--output-format", "json"],
            input=prompt,
            cwd=self._root, capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )

        if result.returncode != 0:
            print(f"\n  WARN: Claude가 비정상 종료됨 (code {result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")

        # 출력 분리 저장 — stdout은 별도 로그 파일 (.gitignore)
        stdout_log = self._run_dir / f"step{step_num}-stdout.log"
        stdout_log.write_text(result.stdout, encoding="utf-8")

        # output.json은 메타 + 요약 + 에러만 (4KB 상한)
        summary_text = result.stdout[:self.OUTPUT_MAX_BYTES]
        output = {
            "step": step_num,
            "name": step_name,
            "exitCode": result.returncode,
            "stdout_summary": summary_text,
            "stderr": result.stderr[:512] if result.stderr else "",
            "stdout_log": (
                str(stdout_log.relative_to(ROOT)).replace("\\", "/")
                if stdout_log.is_relative_to(ROOT)
                else str(stdout_log).replace("\\", "/")
            ),
        }
        out_path = self._run_dir / f"step{step_num}-output.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output

    # ─── Auto Review ───

    def _run_auto_review(self, step_num: int, step_name: str):
        """step 완료 후 a2m_review를 자동 실행한다."""
        review_cmd_file = ROOT / ".claude" / "commands" / "a2m_review.md"
        if not review_cmd_file.exists():
            return

        review_content = review_cmd_file.read_text(encoding="utf-8")
        prompt = f"코드 리뷰를 수행하라. 리뷰 결과를 JSON으로 반환하라.\n\n{review_content}"

        try:
            import shutil as _shutil
            _claude_cmd = _shutil.which("claude") or "claude"
            result = subprocess.run(
                [_claude_cmd, "-p", "--dangerously-skip-permissions", "--output-format", "json"],
                input=prompt,
                cwd=self._root, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace",
                shell=(sys.platform == "win32"),
            )
            review_out = {
                "step": step_num,
                "name": step_name,
                "exitCode": result.returncode,
                "review": result.stdout[:2048],
            }
            review_path = self._run_dir / f"step{step_num}-review.json"
            with open(review_path, "w", encoding="utf-8") as f:
                json.dump(review_out, f, indent=2, ensure_ascii=False)
            print(f"  ✓ Auto-review: step{step_num}-review.json 저장")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  ⚠ Auto-review 실패: {e}")

    # ─── 헤더 & 검증 ───

    def _print_header(self):
        print(f"\n{'='*60}")
        print(f"  Harness Step Executor")
        print(f"  Task: {self._task} | Run: {self._run_id} | Steps: {self._total}")
        options = []
        if self._auto_push:
            options.append("push")
        if self._auto_review:
            options.append("auto-review")
        if self._create_pr:
            options.append("pr")
        if options:
            print(f"  Options: {', '.join(options)}")
        print(f"{'='*60}")

    def _check_blockers(self):
        index = self._read_json(self._index_file)
        for s in reversed(index["steps"]):
            if s["status"] == "error":
                print(f"\n  ✗ Step {s['step']} ({s['name']}) failed.")
                print(f"  Error: {s.get('error_message', 'unknown')}")
                print(f"  Fix and reset status to 'pending' to retry.")
                sys.exit(1)
            if s["status"] == "blocked":
                print(f"\n  ⏸ Step {s['step']} ({s['name']}) blocked.")
                print(f"  Reason: {s.get('blocked_reason', 'unknown')}")
                print(f"  Resolve and reset status to 'pending' to retry.")
                sys.exit(2)
            if s["status"] != "pending":
                break

    def _ensure_created_at(self):
        index = self._read_json(self._index_file)
        if "created_at" not in index:
            index["created_at"] = self._stamp()
            self._write_json(self._index_file, index)

    # ─── 실행 루프 ───

    def _execute_single_step(self, step: dict) -> bool:
        step_num, step_name = step["step"], step["name"]
        done = sum(1 for s in self._read_json(self._index_file)["steps"] if s["status"] == "completed")
        prev_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            index = self._read_json(self._index_file)
            step_context = StepExecutor._build_step_context(index, step_num)
            guardrails = self._load_guardrails(step_num)
            preamble = self._build_preamble(
                guardrails, step_context, step_num, prev_error, is_retry=(attempt > 1)
            )

            tag = f"Step {step_num}/{self._total - 1} ({done} done): {step_name}"
            if attempt > 1:
                tag += f" [retry {attempt}/{self.MAX_RETRIES}]"

            with progress_indicator(tag) as pi:
                self._invoke_claude(step, preamble)
                elapsed = int(pi.elapsed)

            index = self._read_json(self._index_file)
            status = next(
                (s.get("status", "pending") for s in index["steps"] if s["step"] == step_num),
                "pending",
            )
            ts = self._stamp()

            if status == "completed":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["completed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✓ Step {step_num}: {step_name} [{elapsed}s]")

                # auto-review
                if self._auto_review:
                    self._run_auto_review(step_num, step_name)

                return True

            if status == "blocked":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["blocked_at"] = ts
                self._write_json(self._index_file, index)
                reason = next(
                    (s.get("blocked_reason", "") for s in index["steps"] if s["step"] == step_num),
                    "",
                )
                print(f"  ⏸ Step {step_num}: {step_name} blocked [{elapsed}s]")
                print(f"    Reason: {reason}")
                self._update_top_index("blocked")
                sys.exit(2)

            err_msg = next(
                (
                    s.get("error_message", "Step did not update status")
                    for s in index["steps"]
                    if s["step"] == step_num
                ),
                "Step did not update status",
            )

            if attempt < self.MAX_RETRIES:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "pending"
                        s.pop("error_message", None)
                self._write_json(self._index_file, index)
                prev_error = err_msg
                print(f"  ↻ Step {step_num}: retry {attempt}/{self.MAX_RETRIES} — {err_msg}")
            else:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "error"
                        s["error_message"] = f"[{self.MAX_RETRIES}회 시도 후 실패] {err_msg}"
                        s["failed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✗ Step {step_num}: {step_name} failed after {self.MAX_RETRIES} attempts [{elapsed}s]")
                print(f"    Error: {err_msg}")
                self._update_top_index("error")
                sys.exit(1)

        return False

    def _execute_all_steps(self):
        while True:
            index = self._read_json(self._index_file)
            pending = next((s for s in index["steps"] if s["status"] == "pending"), None)
            if pending is None:
                print("\n  All steps completed!")
                return

            step_num = pending["step"]
            for s in index["steps"]:
                if s["step"] == step_num and "started_at" not in s:
                    s["started_at"] = self._stamp()
                    self._write_json(self._index_file, index)
                    break

            self._execute_single_step(pending)

    # ─── Finalize ───

    def _generate_report(self) -> str:
        """phases/<task>/<runId>/REPORT.md를 생성한다."""
        index = self._read_json(self._index_file)
        steps = index.get("steps", [])

        # 소요 시간 계산
        created_at = index.get("created_at", "")
        completed_at = index.get("completed_at", "")

        # 커밋 목록
        git_log = self._run_git("log", "--oneline", "-10")
        commits = git_log.stdout.strip() if git_log.returncode == 0 else "(없음)"

        # 변경 통계
        git_stat = self._run_git("diff", "--stat", "HEAD~5..HEAD")
        diff_stat = git_stat.stdout.strip() if git_stat.returncode == 0 else "(없음)"

        # step 요약
        step_lines = []
        for s in steps:
            icon = {"completed": "✓", "error": "✗", "blocked": "⏸", "pending": "⏳"}.get(s["status"], "?")
            summary = s.get("summary") or s.get("error_message") or s.get("blocked_reason") or ""
            step_lines.append(f"| {s['step']} | {s['name']} | {icon} {s['status']} | {summary[:80]} |")

        step_table = "\n".join(step_lines) if step_lines else "(없음)"

        # 참고 프로젝트
        refs = self._read_json(ROOT / ".harness" / "references.json").get("references", []) \
            if (ROOT / ".harness" / "references.json").exists() else []
        ref_text = ", ".join(r["name"] for r in refs) if refs else "없음"

        report = f"""# 실행 리포트: {self._task}/{self._run_id}

## 개요

| 항목 | 값 |
|------|------|
| task | {self._task} |
| run_id | {self._run_id} |
| 시작 | {created_at} |
| 완료 | {completed_at} |
| 참고 프로젝트 | {ref_text} |

## Step 결과

| step | 이름 | 상태 | 요약 |
|------|------|------|------|
{step_table}

## 커밋 목록

```
{commits}
```

## 변경 통계

```
{diff_stat}
```

## 다음 단계 제안

- 이 run에서 생성된 release-note를 확인하세요: `.harness/release-notes/{self._run_id}_{self._task}.md`
- docs 동기화가 필요하면: `/a2m_sync_docs`
- 추가 개선이 필요하면: `/a2m_improve`
"""
        report_path = self._run_dir / "REPORT.md"
        report_path.write_text(report, encoding="utf-8")
        return str(report_path)

    def _create_pr_mr(self):
        """GitLab MR 또는 GitHub PR을 자동 생성한다."""
        origin = self._run_git("remote", "get-url", "origin")
        if origin.returncode != 0:
            print("  ⚠ git remote origin 없음 — PR/MR 생성 건너뜀")
            return

        remote_url = origin.stdout.strip()
        branch = self._branch_name()

        report_path = self._run_dir / "REPORT.md"
        body = report_path.read_text(encoding="utf-8")[:4000] if report_path.exists() else ""

        if "gitlab" in remote_url:
            result = subprocess.run(
                ["glab", "mr", "create", "--title", f"feat({self._task}): {self._run_id}",
                 "--description", body, "--source-branch", branch],
                cwd=self._root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        elif "github" in remote_url:
            result = subprocess.run(
                ["gh", "pr", "create", "--title", f"feat({self._task}): {self._run_id}",
                 "--body", body, "--head", branch],
                cwd=self._root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        else:
            print("  ⚠ GitLab/GitHub 원격이 아님 — PR/MR 생성 건너뜀")
            return

        if result.returncode == 0:
            print(f"  ✓ PR/MR 생성 완료: {result.stdout.strip()}")
        else:
            print(f"  ⚠ PR/MR 생성 실패: {result.stderr.strip()}")
            print("  Hint: glab 또는 gh CLI가 설치되어 있는지 확인하세요.")

    def _squash_run_commits(self):
        """run의 step 커밋들을 1개로 squash한다. PR 노이즈를 줄이기 위해 사용."""
        # merge-base를 기준으로 squash
        merge_base = ""
        for base_branch in ("main", "master", "develop"):
            r = self._run_git("merge-base", base_branch, "HEAD")
            if r.returncode == 0:
                merge_base = r.stdout.strip()
                break

        if not merge_base:
            print("  ⚠ squash 건너뜀: merge-base를 찾을 수 없습니다.")
            return

        squash_msg = f"feat({self._task}): {self._run_id} — run 완료 (squashed)"
        r = self._run_git("reset", "--soft", merge_base)
        if r.returncode != 0:
            print(f"  ⚠ squash reset 실패: {r.stderr.strip()}")
            return
        r = self._run_git("commit", "-m", squash_msg)
        if r.returncode == 0:
            print(f"  ✓ Squash 완료: {squash_msg}")
        else:
            print(f"  ⚠ squash commit 실패: {r.stderr.strip()}")

    def _finalize(self):
        index = self._read_json(self._index_file)
        index["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._update_top_index("completed")

        # REPORT.md 생성
        report_path = self._generate_report()
        print(f"  ✓ REPORT.md: {report_path}")

        run_rel = f".harness/phases/{self._task}/{self._run_id}"
        self._run_git("add", "--", run_rel)
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = f"chore({self._task}): run {self._run_id} completed"
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")

        # Squash 옵션 — run의 step 커밋들을 1개로 합침
        if self._squash_on_finalize:
            self._squash_run_commits()

        # Release Notes 생성
        if not self._no_release_note:
            try:
                rn_args = [sys.executable, ".harness/scripts/release_notes.py", self._task, self._run_id]
                if self._detailed_release_notes:
                    rn_args.append("--detailed")
                subprocess.run(rn_args, cwd=self._root, timeout=180, encoding="utf-8", errors="replace", text=True)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"  ⚠ release_notes.py 실행 실패: {e}")

        # Push
        if self._auto_push:
            branch = self._branch_name()
            r = self._run_git("push", "-u", "origin", branch)
            if r.returncode != 0:
                print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  ✓ Pushed to origin/{branch}")

        # PR/MR 생성
        if self._create_pr:
            self._create_pr_mr()

        print(f"\n{'='*60}")
        print(f"  Task '{self._task}' / Run '{self._run_id}' completed!")
        print(f"{'='*60}")

    def _check_author_ownership(self):
        """run.json의 author가 현재 사용자와 일치하는지 확인한다."""
        run_json_path = self._run_dir / "run.json"
        if not run_json_path.exists():
            return  # run.json 없으면 레거시 run — 패스

        try:
            run_data = self._read_json(run_json_path)
        except (json.JSONDecodeError, OSError):
            return

        author_info = run_data.get("author", {})
        run_author = author_info.get("email", "") if isinstance(author_info, dict) else str(author_info)

        if not run_author:
            return

        if self._run_as:
            current_author = self._run_as
        else:
            current = _get_current_author()
            current_author = current["email"]

        if run_author == current_author:
            return  # 본인 run — OK

        if self._takeover_from:
            # 명시적 takeover 요청
            if run_author != self._takeover_from:
                print(f"  ⚠ run의 author({run_author})가 --takeover 지정({self._takeover_from})과 다릅니다.")
                print(f"  Hint: --takeover {run_author} 로 다시 시도하세요.")
                sys.exit(1)
            # ownership 이전
            print(f"  [author] {run_author} → {current_author} 인계 처리 중...")
            new_current = _get_current_author()
            history_entry = {
                "from": run_author,
                "to": current_author,
                "at": datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "reason": "takeover",
            }
            if isinstance(run_data.get("author"), dict):
                run_data["author"]["email"] = current_author
                run_data["author"]["name"] = new_current.get("name", current_author)
                run_data["author"]["host"] = new_current.get("host", "unknown")
            else:
                run_data["author"] = new_current
            run_data.setdefault("ownership_history", []).append(history_entry)
            self._write_json(run_json_path, run_data)
            print(f"  ✓ Ownership 이전 완료: {current_author}")
            return

        # 타인 run이지만 takeover 없음
        print(f"\n  ✗ 차단: 이 run은 {run_author}가 시작했습니다.")
        print(f"  현재 사용자: {current_author}")
        print(f"  인계받으려면: --takeover {run_author}")
        print(f"  모든 run 목록: python .harness/scripts/find_resumable.py --show-all")
        sys.exit(1)

    def run(self):
        self._print_header()
        self._check_author_ownership()
        self._preflight()
        self._check_blockers()
        self._checkout_branch()
        self._ensure_created_at()
        self._execute_all_steps()
        self._finalize()


# ─── 팩토리 함수 ───

def _get_current_author() -> dict:
    """현재 git user.email/name과 호스트 정보를 반환한다."""
    def _git_config(key: str) -> str:
        try:
            r = subprocess.run(["git", "config", "--get", key],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            return r.stdout.strip() if r.returncode == 0 else ""
        except FileNotFoundError:
            return ""

    email = (
        os.environ.get("HARNESS_AUTHOR")
        or _git_config("user.email")
        or f"{os.environ.get('USERNAME', 'unknown')}@{os.uname().nodename if hasattr(os, 'uname') else 'host'}"
    )
    name = _git_config("user.name") or email.split("@")[0]
    try:
        import socket
        host = socket.gethostname()
    except Exception:
        host = "unknown"

    return {"email": email, "name": name, "host": host}


def _author_short(email: str) -> str:
    """이메일에서 8자 이내 안전한 식별자를 반환한다."""
    import re as _re
    local = email.split("@")[0]
    safe = _re.sub(r"[^\w]", "", local)
    return safe[:8] or "anon"


def _make_run_id(author_email: str = "") -> str:
    """타임스탬프 + author 단축식별자 기반 runId를 생성한다."""
    TZ = timezone(timedelta(hours=9))
    base = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    if author_email:
        return f"{base}_{_author_short(author_email)}"
    return base


def _ensure_unique_run_id(task_dir: Path, base_id: str) -> str:
    """runId 충돌 방지 — 존재하면 _2, _3 접미를 붙인다."""
    if not (task_dir / base_id).exists():
        return base_id
    for i in range(2, 100):
        candidate = f"{base_id}_{i}"
        if not (task_dir / candidate).exists():
            return candidate
    return base_id


def _register_run(phases_dir: Path, task: str, run_id: str, stage: str, branch: str,
                  author: Optional[dict] = None):
    """phases/index.json에 새 run을 등록하고, run.json에 author 정보를 기록한다."""
    top_path = phases_dir / "index.json"
    if top_path.exists():
        try:
            top = json.loads(top_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            top = {"runs": []}
    else:
        top = {"runs": []}

    TZ = timezone(timedelta(hours=9))
    started_at = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+09:00")

    author_info = author or _get_current_author()
    author_info["started_at"] = started_at

    run_entry = {
        "task": task,
        "run_id": run_id,
        "dir": f"{task}/{run_id}",
        "status": "pending",
        "stage": stage,
        "branch": branch,
        "started_at": started_at,
        "author": author_info["email"],
    }
    top["runs"].append(run_entry)
    top_path.write_text(json.dumps(top, indent=2, ensure_ascii=False), encoding="utf-8")

    # per-run run.json 기록
    run_dir = phases_dir / task / run_id
    if run_dir.is_dir():
        run_json_path = run_dir / "run.json"
        run_data = {
            "task": task,
            "run_id": run_id,
            "author": author_info,
            "ownership_history": [],
            "status": "pending",
            "stage": stage,
            "branch": branch,
            "started_at": started_at,
        }
        if not run_json_path.exists():
            run_json_path.write_text(json.dumps(run_data, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_run_from_arg(arg: str, phases_dir: Path):
    """
    인자를 파싱하여 (task, run_id)를 반환한다.
    - "<task>/<runId>" 형식
    - "<task>" 형식 (레거시 또는 새 run)
    """
    if "/" in arg:
        parts = arg.split("/", 1)
        return parts[0], parts[1]

    # 레거시 단일 폴더 구조 감지
    legacy_dir = phases_dir / arg
    if legacy_dir.is_dir() and (legacy_dir / "index.json").exists():
        idx = json.loads((legacy_dir / "index.json").read_text(encoding="utf-8"))
        if "steps" in idx and not (phases_dir / arg).parent.name == "phases":
            print(f"  ⚠ 레거시 phases 구조 감지: {legacy_dir}")
            print(f"  → 레거시 모드로 실행합니다 (새 run부터 신규 구조 사용 권장)")

    return arg, None  # run_id=None이면 새 run 생성 필요


def _find_latest_incomplete(phases_dir: Path, task: Optional[str] = None):
    """가장 최근 미완료 run을 찾는다."""
    runs = scan_resumable_runs(phases_dir)
    if task:
        runs = [r for r in runs if r["task"] == task]
    if not runs:
        return None, None
    # started_at 기준 최신
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[0]["task"], runs[0]["run_id"]


def main():
    parser = argparse.ArgumentParser(description="Harness Step Executor")
    parser.add_argument("phase_dir", nargs="?", default="",
                        help="task 이름 또는 task/runId")
    parser.add_argument("--push", action="store_true", help="완료 후 브랜치 push")
    parser.add_argument("--auto-review", action="store_true",
                        help="각 step 완료 후 a2m_review 자동 실행")
    parser.add_argument("--pr", action="store_true", help="완료 후 PR/MR 자동 생성")
    parser.add_argument("--skip-preflight", action="store_true", help="Preflight 검사 건너뜀")
    parser.add_argument("--resume", action="store_true", help="가장 최근 미완료 run 자동 재개")
    parser.add_argument("--latest", metavar="TASK", help="특정 task의 가장 최근 run")
    parser.add_argument("--no-release-note", action="store_true", help="release note 생성 안 함")
    parser.add_argument("--detailed-release-notes", action="store_true",
                        help="release note에 전체 git diff 포함")
    parser.add_argument("--takeover", metavar="AUTHOR_EMAIL",
                        help="타인의 미완료 run을 인계받아 실행 (ownership 이전)")
    parser.add_argument("--as", dest="run_as", metavar="AUTHOR_EMAIL",
                        help="테스트용: 지정 author로 가장하여 실행")
    parser.add_argument("--show-all", action="store_true",
                        help="본인 run뿐만 아니라 모든 author의 run을 표시")
    parser.add_argument("--no-chore-commit", action="store_true",
                        help="step output·index의 자동 chore 커밋 비활성화")
    parser.add_argument("--squash-on-finalize", action="store_true",
                        help="run 완료 시 step 커밋들을 1개로 squash (PR 노이즈 감소)")
    args = parser.parse_args()

    phases_dir = ROOT / ".harness" / "phases"

    # production 단계이면 auto-review 기본 on
    profile_path = ROOT / ".harness" / "profile.json"
    auto_review = args.auto_review
    if not auto_review and profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if profile.get("stage") == "production":
                auto_review = True
        except (json.JSONDecodeError, OSError):
            pass

    # --resume 모드
    if args.resume:
        task, run_id = _find_latest_incomplete(phases_dir)
        if not task:
            print("재개 가능한 미완료 run이 없습니다.")
            sys.exit(0)
        print(f"재개: {task}/{run_id}")

    # --latest 모드
    elif args.latest:
        task, run_id = _find_latest_incomplete(phases_dir, args.latest)
        if not task:
            print(f"'{args.latest}'에 재개 가능한 run이 없습니다.")
            sys.exit(0)
        print(f"최근 run: {task}/{run_id}")

    # phase_dir 인자
    elif args.phase_dir:
        task, run_id = _resolve_run_from_arg(args.phase_dir, phases_dir)

        if run_id is None:
            # DEPRECATED: task만 지정하는 경로. /a2m_start 또는 /a2m_improve에서 task/runId를 명시하세요.
            print(f"  ⚠ DEPRECATED: execute.py에 task 이름만 전달하는 방식은 더 이상 권장되지 않습니다.")
            print(f"  → /a2m_start 또는 /a2m_improve 명령을 통해 task/runId 형식으로 실행하세요.")
            task_dir = phases_dir / task
            if task_dir.is_dir():
                # 2단 구조 run 폴더 탐색
                run_dirs = sorted(
                    [d for d in task_dir.iterdir() if d.is_dir() and (d / "index.json").exists()],
                    reverse=True,
                )
                if run_dirs:
                    run_id = run_dirs[0].name
                    print(f"  → {task}의 최근 run 사용: {run_id}")
                else:
                    print(f"  ⚠ DEPRECATED: 레거시 phases 구조. 향후 task/runId 형식을 사용하세요.")
                    run_id = "_legacy"
            else:
                print(f"ERROR: phases/{task} not found")
                sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    StepExecutor(
        task,
        run_id,
        auto_push=args.push,
        auto_review=auto_review,
        create_pr=args.pr,
        skip_preflight=args.skip_preflight,
        no_release_note=args.no_release_note,
        detailed_release_notes=args.detailed_release_notes,
        takeover_from=args.takeover or "",
        run_as=args.run_as or "",
        no_chore_commit=args.no_chore_commit,
        squash_on_finalize=args.squash_on_finalize,
    ).run()


if __name__ == "__main__":
    main()
