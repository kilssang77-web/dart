#!/usr/bin/env python3
"""
실행 완료 후 release-notes/<runId>_<task>.md를 자동 생성하고 INDEX.md를 갱신한다.
execute.py의 _finalize에서 호출된다.

Usage:
    python3 scripts/release_notes.py <task> <run_id> [--no-ai] [--detailed]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_NOTES_DIR = ROOT / ".harness" / "release-notes"
TZ = timezone(timedelta(hours=9))

MAX_INDEX_ENTRIES = 20


def _stamp() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _run_git(*args, default: str = "") -> str:
    """git 명령을 실행하고 stdout을 반환한다."""
    r = subprocess.run(["git"] + list(args), cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else default


def _get_merge_base(branch: str) -> str:
    """현재 브랜치와 main/master의 merge base를 반환한다."""
    for base_branch in ("main", "master", "develop"):
        r = subprocess.run(
            ["git", "merge-base", base_branch, "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode == 0:
            return r.stdout.strip()
    return ""


def _collect_inputs(task: str, run_id: str, detailed: bool = False) -> dict:
    """release-note 생성에 필요한 입력 자료를 수집한다."""
    run_dir = ROOT / ".harness" / "phases" / task / run_id
    run_index = _read_json_safe(run_dir / "index.json")

    # step summary 수집
    step_summaries = []
    for step in run_index.get("steps", []):
        if step.get("status") == "completed" and step.get("summary"):
            step_summaries.append(f"- Step {step['step']} ({step['name']}): {step['summary']}")

    # profile
    profile = _read_json_safe(ROOT / ".harness" / "profile.json")

    # git 정보
    merge_base = _get_merge_base(run_index.get("branch", "HEAD"))
    range_spec = f"{merge_base}..HEAD" if merge_base else "HEAD~10..HEAD"

    git_log = _run_git("log", "--oneline", range_spec, default="(git 로그 없음)")
    git_stat = _run_git("diff", "--stat", range_spec, default="(변경 통계 없음)")
    git_diff = ""
    if detailed:
        git_diff = _run_git("diff", range_spec, default="")[:3000]  # 3KB 상한

    # references
    refs = _read_json_safe(ROOT / ".harness" / "references.json")
    ref_names = [r["name"] for r in refs.get("references", [])]

    return {
        "task": task,
        "run_id": run_id,
        "stage": profile.get("stage", "mvp"),
        "project_name": profile.get("project_name", "project"),
        "branch": run_index.get("branch", ""),
        "step_summaries": step_summaries,
        "git_log": git_log,
        "git_stat": git_stat,
        "git_diff": git_diff,
        "references": ref_names,
        "started_at": run_index.get("created_at", ""),
    }


def _build_template(inputs: dict) -> str:
    """자료로 release-note 기본 템플릿을 생성한다."""
    steps_text = "\n".join(inputs["step_summaries"]) or "(step 요약 없음)"
    refs_text = ", ".join(inputs["references"]) if inputs["references"] else "없음"

    return f"""# Release: {inputs['run_id']} — {inputs['task']}

- task: {inputs['task']} / runId: {inputs['run_id']} / stage: {inputs['stage']} / branch: {inputs['branch']}
- 참고 프로젝트: {refs_text}
- 시작: {inputs['started_at']} / 생성: {_stamp()}

## Step 산출물 요약

{steps_text}

## Git 커밋

```
{inputs['git_log']}
```

## 변경 통계

```
{inputs['git_stat']}
```

## 변경 요약

- (Added) {'{자동 분석 또는 수동 작성}'}
- (Changed) {'{자동 분석 또는 수동 작성}'}
- (Removed) {'{자동 분석 또는 수동 작성}'}

## 영향도 및 마이그레이션

- DB 스키마: {'{없음 또는 명세}'}
- API 클라이언트: {'{없음 또는 명세}'}
- 환경변수: {'{없음 또는 명세}'}

## Breaking Changes

- 없음

## 관련 docs 갱신 권고

- {'{해당 docs 파일과 갱신 내용을 명시}'}
"""


def _call_ai_for_summary(inputs: dict) -> str:
    """Claude를 호출하여 변경 요약 섹션을 생성한다."""
    steps_text = "\n".join(inputs["step_summaries"]) or "(step 요약 없음)"

    prompt = f"""아래 정보를 바탕으로 소프트웨어 릴리즈 노트의 '변경 요약', '영향도 및 마이그레이션', 'Breaking Changes', '관련 docs 갱신 권고' 섹션만 마크다운으로 작성하라.

## 프로젝트 단계
{inputs['stage']}

## Step 산출물 요약
{steps_text}

## Git 커밋 목록
{inputs['git_log']}

## 변경 파일 통계
{inputs['git_stat']}

## 형식 (이 형식만 출력, 추가 설명 금지)
### 변경 요약
- (Added) ...
- (Changed) ...
- (Removed) ...

### 영향도 및 마이그레이션
- DB 스키마: ...
- API 클라이언트: ...
- 환경변수: ...

### Breaking Changes
- 없음 또는 명세

### 관련 docs 갱신 권고
- 파일명: 갱신 내용
"""
    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions"],
            input=prompt,
            cwd=str(ROOT), capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _write_note_meta(note_file: Path, inputs: dict):
    """per-note 메타 파일(.meta.json)을 기록한다. synced 상태의 진실이 여기 있다."""
    meta_path = note_file.with_suffix(".meta.json")
    meta = {
        "file": note_file.name,
        "task": inputs.get("task", ""),
        "run_id": inputs.get("run_id", ""),
        "stage": inputs.get("stage", ""),
        "generated_at": _stamp(),
        "synced": False,
    }
    if not meta_path.exists():
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _rebuild_index():
    """release-notes/INDEX.md를 .meta.json 파일 기반으로 재생성한다 (generate-only)."""
    RELEASE_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    index_path = RELEASE_NOTES_DIR / "INDEX.md"

    entries = []
    for meta_file in sorted(RELEASE_NOTES_DIR.glob("*.meta.json"), reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        synced_icon = "✅" if meta.get("synced") else "❌"
        note_name = meta.get("file", meta_file.stem)
        entries.append(
            f"| [{note_name}]({note_name}) | {meta.get('task', '')} | "
            f"{meta.get('stage', '')} | {meta.get('generated_at', '')[:10]} | {synced_icon} |"
        )

    entries = entries[:MAX_INDEX_ENTRIES]
    header = """# Release Notes Index

> **이 파일은 자동 생성됩니다.** 직접 수정하지 마세요.
> synced 상태는 각 release-note의 `.meta.json` 파일에서 관리됩니다.
> `/a2m_sync_docs` 명령으로 ❌ 항목을 docs/*에 동기화하고 synced=true로 마킹합니다.

| 파일 | task | stage | 날짜 | synced |
|------|------|-------|------|--------|
"""
    index_path.write_text(header + "\n".join(entries) + "\n", encoding="utf-8")


def _update_index(note_file: Path, inputs: dict):
    """per-note .meta.json을 기록하고 INDEX.md를 재생성한다."""
    RELEASE_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    _write_note_meta(note_file, inputs)
    _rebuild_index()


def generate(task: str, run_id: str, no_ai: bool = False, detailed: bool = False) -> Path:
    """release-note를 생성하고 파일 경로를 반환한다."""
    RELEASE_NOTES_DIR.mkdir(parents=True, exist_ok=True)

    inputs = _collect_inputs(task, run_id, detailed)
    template = _build_template(inputs)

    if not no_ai:
        print("[release_notes] AI로 변경 요약 생성 중...")
        ai_summary = _call_ai_for_summary(inputs)
        if ai_summary:
            # 템플릿의 변경 요약 섹션을 AI 결과로 교체
            sections_to_replace = ["변경 요약", "영향도 및 마이그레이션", "Breaking Changes", "관련 docs 갱신 권고"]
            start_marker = "## 변경 요약"
            if start_marker in template:
                pre = template[: template.index(start_marker)]
                template = pre + ai_summary
        else:
            print("[release_notes] AI 호출 실패 — 기본 템플릿으로 저장")

    file_name = f"{run_id}_{task}.md"
    out_path = RELEASE_NOTES_DIR / file_name
    out_path.write_text(template, encoding="utf-8")

    _update_index(out_path, inputs)

    print(f"[release_notes] ✓ {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Release Note 생성기")
    parser.add_argument("task", nargs="?", help="task 이름")
    parser.add_argument("run_id", nargs="?", help="run ID")
    parser.add_argument("--no-ai", action="store_true", help="AI 호출 없이 템플릿만 생성")
    parser.add_argument("--detailed", action="store_true", help="전체 git diff 포함 (토큰 비용 큼)")
    parser.add_argument("--rebuild-index", action="store_true",
                        help=".meta.json 기반으로 INDEX.md 재생성")
    args = parser.parse_args()

    if args.rebuild_index:
        _rebuild_index()
        print("[release_notes] INDEX.md 재생성 완료")
        return

    if not args.task or not args.run_id:
        parser.error("task와 run_id가 필요합니다 (또는 --rebuild-index 사용)")

    out = generate(args.task, args.run_id, no_ai=args.no_ai, detailed=args.detailed)
    print(f"[release_notes] 완료: {out}")


if __name__ == "__main__":
    main()
