#!/usr/bin/env python3
"""
ask_questions.py — stateless interpreter for .harness/questions.yaml

Usage:
  python ask_questions.py next      [--answers FILE] [--profile FILE] [--stage STAGE]
  python ask_questions.py answer ID VALUE [--answers FILE]
  python ask_questions.py done      [--answers FILE] [--profile FILE]
  python ask_questions.py missing   [--answers FILE] [--profile FILE]
  python ask_questions.py list      [--answers FILE] [--profile FILE]
  python ask_questions.py explain ID [--answers FILE] [--profile FILE]
  python ask_questions.py reset     --confirm [--answers FILE]

Exit codes:
  0  — done / ok
  1  — not done / error
"""

from __future__ import annotations

import io
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure stdout is UTF-8 on Windows (cp949 cannot encode Korean + em-dash etc.)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
QUESTIONS_YAML = BASE_DIR / "questions.yaml"
DEFAULT_ANSWERS = BASE_DIR / "answers.json"
DEFAULT_PROFILE = BASE_DIR / "profile.json"

# ─── yaml loader (graceful fallback) ─────────────────────────────────────────
def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        print(
            "[ask_questions] WARNING: PyYAML not installed. "
            "Install with: pip install pyyaml\n"
            "Falling back to AI direct interpretation of questions.yaml.",
            file=sys.stderr,
        )
        sys.exit(1)
    except FileNotFoundError:
        print(f"[ask_questions] ERROR: {path} not found.", file=sys.stderr)
        sys.exit(1)

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ask_questions] ERROR: {path} is not valid JSON: {e}", file=sys.stderr)
        return {}

def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── condition evaluation ─────────────────────────────────────────────────────
def _get_nested(data: dict, dot_path: str, default=None):
    """Get value from nested dict using dot-notation key (e.g. 'q3.backend')."""
    keys = dot_path.split(".")
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, None)
        if cur is None:
            return default
    return cur

def _eval_condition(condition: Any, answers: dict, profile: dict) -> bool:
    """Evaluate a condition dict: {key: value_or_list}."""
    if not condition:
        return True
    if not isinstance(condition, dict):
        return True

    def resolve(key: str):
        # Try answers first, then profile
        if "." in key:
            val = _get_nested(answers.get("answers", {}), key)
            if val is None:
                val = _get_nested(profile, key)
            return val
        return answers.get("answers", {}).get(key) or _get_nested(profile, key)

    for key, expected in condition.items():
        actual = resolve(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False
    return True

# ─── question helpers ─────────────────────────────────────────────────────────
def _is_required(q: dict, answers: dict, profile: dict) -> bool:
    if q.get("required") is False:
        # Check required_if
        req_if = q.get("required_if")
        if req_if and _eval_condition(req_if, answers, profile):
            return True
        return False
    return True

def _is_skipped(q: dict, answers: dict, profile: dict) -> bool:
    skip_if = q.get("skip_if")
    if skip_if and _eval_condition(skip_if, answers, profile):
        return True
    return False

def _is_answered(q: dict, answers: dict) -> bool:
    ans = answers.get("answers", {})
    qid = q["id"]
    return qid in ans

def _get_effective_stage(answers: dict, profile: dict, cli_stage: str | None) -> str:
    if cli_stage:
        return cli_stage
    ans = answers.get("answers", {}).get("q0a")
    if ans:
        return ans
    return profile.get("stage", "prototype")

STAGE_ORDER = ["prototype", "mvp", "production"]

def _stage_gte(a: str, b: str) -> bool:
    return STAGE_ORDER.index(a) >= STAGE_ORDER.index(b)

# ─── matrix filtering ────────────────────────────────────────────────────────
def _filter_matrix(q: dict, answers: dict, profile: dict) -> list:
    """Return filtered options from choice_matrix based on current answers/profile."""
    matrix = q.get("matrix", [])
    result = []
    for row in matrix:
        when = row.get("when", {})
        if _eval_condition(when, answers, profile):
            result.extend(row.get("options", []))
    if not result:
        # fallback: return all options from first matrix row
        if matrix:
            result = matrix[0].get("options", [])
    return result

# ─── display helpers ─────────────────────────────────────────────────────────
def _render_question(q: dict, answers: dict, profile: dict, stage: str) -> dict:
    """Build a display dict for the question (with filtered options)."""
    out: dict = {
        "id": q["id"],
        "title": q["title"],
        "type": q["type"],
        "required": _is_required(q, answers, profile),
    }
    if q["type"] in ("choice", "multi_choice"):
        out["options"] = q.get("options", [])
    elif q["type"] == "choice_matrix":
        out["options"] = _filter_matrix(q, answers, profile)
    elif q["type"] == "choice_with_followups":
        out["options"] = q.get("options", [])
    elif q["type"] in ("composite",):
        out["fields"] = q.get("fields", [])
    elif q["type"] == "free_text":
        out["prompt"] = q.get("notes", "")
    elif q["type"] == "bool":
        out["default"] = q.get("default", False)

    if q.get("notes"):
        out["notes"] = q["notes"]
    if q.get("depends_on"):
        out["depends_on"] = q["depends_on"]
    return out

# ─── profile update ──────────────────────────────────────────────────────────
def _apply_affects(q: dict, value: Any, profile: dict) -> None:
    """Update profile.json keys listed in q.affects that start with 'profile.json.'."""
    for affect in q.get("affects", []):
        if not affect.startswith("profile.json."):
            continue
        dot_path = affect[len("profile.json."):]
        keys = dot_path.split(".")
        cur = profile
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = value

# ─── commands ────────────────────────────────────────────────────────────────

def cmd_list(args, all_questions: list, answers: dict, profile: dict, stage: str) -> int:
    print(f"{'ID':<20} {'TYPE':<20} {'STATUS':<10} TITLE")
    print("-" * 80)
    for q in all_questions:
        qid = q["id"]
        skipped = _is_skipped(q, answers, profile)
        answered = _is_answered(q, answers)
        required = _is_required(q, answers, profile)
        status = "SKIP" if skipped else ("DONE" if answered else ("REQ" if required else "OPT"))
        print(f"{qid:<20} {q['type']:<20} {status:<10} {q['title']}")
    return 0


def cmd_next(args, all_questions: list, answers: dict, profile: dict, stage: str) -> int:
    for q in all_questions:
        if _is_skipped(q, answers, profile):
            continue
        if _is_answered(q, answers):
            continue
        if not _is_required(q, answers, profile):
            continue
        rendered = _render_question(q, answers, profile, stage)
        print(json.dumps(rendered, ensure_ascii=False, indent=2))
        return 1  # 1 = there are still questions left
    print(json.dumps({"done": True, "message": "모든 필수 질문이 완료되었습니다."}, ensure_ascii=False))
    return 0  # 0 = done


def cmd_done(args, all_questions: list, answers: dict, profile: dict, stage: str) -> int:
    missing = []
    for q in all_questions:
        if _is_skipped(q, answers, profile):
            continue
        if _is_answered(q, answers):
            continue
        if _is_required(q, answers, profile):
            missing.append(q["id"])
    if missing:
        print(json.dumps({"done": False, "missing": missing}, ensure_ascii=False))
        return 1
    print(json.dumps({"done": True}, ensure_ascii=False))
    return 0


def cmd_missing(args, all_questions: list, answers: dict, profile: dict, stage: str) -> int:
    missing = []
    for q in all_questions:
        if _is_skipped(q, answers, profile):
            continue
        if _is_answered(q, answers):
            continue
        if _is_required(q, answers, profile):
            missing.append({"id": q["id"], "title": q["title"]})
    print(json.dumps(missing, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


def cmd_answer(args, all_questions: list, answers: dict, profile: dict, stage: str,
               answers_path: Path, profile_path: Path) -> int:
    qid = args.question_id
    value_str = args.value

    # Find question
    question = next((q for q in all_questions if q["id"] == qid), None)
    if question is None:
        print(f"[ask_questions] ERROR: 질문 ID '{qid}'를 찾을 수 없습니다.", file=sys.stderr)
        return 1

    # Parse value
    try:
        value = json.loads(value_str)
    except (json.JSONDecodeError, ValueError):
        value = value_str  # treat as plain string

    # Record answer
    if "answers" not in answers:
        answers["answers"] = {}
    answers["answers"][qid] = value
    answers["answered_by"] = answers.get("answered_by", "")
    answers["answered_at"] = datetime.now(tz=timezone.utc).isoformat()

    # Update profile.json via affects
    _apply_affects(question, value, profile)
    profile["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

    _save_json(answers_path, answers)
    _save_json(profile_path, profile)

    print(json.dumps({"recorded": qid, "value": value}, ensure_ascii=False))
    return 0


def cmd_explain(args, all_questions: list, answers: dict, profile: dict, stage: str) -> int:
    qid = args.question_id
    question = next((q for q in all_questions if q["id"] == qid), None)
    if question is None:
        print(f"[ask_questions] ERROR: 질문 ID '{qid}'를 찾을 수 없습니다.", file=sys.stderr)
        return 1

    skipped = _is_skipped(question, answers, profile)
    answered = _is_answered(question, answers)
    required = _is_required(question, answers, profile)
    rendered = _render_question(question, answers, profile, stage)

    out = {
        "id": qid,
        "title": question["title"],
        "type": question["type"],
        "required": required,
        "skipped": skipped,
        "answered": answered,
        "current_answer": answers.get("answers", {}).get(qid),
        "rendered": rendered,
    }
    if question["type"] == "choice_matrix":
        out["matrix_all"] = question.get("matrix", [])
        out["matrix_filtered"] = _filter_matrix(question, answers, profile)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_reset(args, answers_path: Path) -> int:
    if not getattr(args, "confirm", False):
        print("[ask_questions] 위험한 작업입니다. --confirm 플래그를 추가하세요.", file=sys.stderr)
        return 1
    template = {
        "schema_version": 1,
        "answered_by": "",
        "answered_at": "",
        "answers": {}
    }
    _save_json(answers_path, template)
    print(f"[ask_questions] answers.json 초기화 완료: {answers_path}")
    return 0

# ─── main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="ask_questions.py — stateless interpreter for questions.yaml"
    )
    parser.add_argument(
        "--answers", default=str(DEFAULT_ANSWERS),
        help="answers.json 경로 (기본: .harness/answers.json)"
    )
    parser.add_argument(
        "--profile", default=str(DEFAULT_PROFILE),
        help="profile.json 경로 (기본: .harness/profile.json)"
    )
    parser.add_argument(
        "--stage", default=None,
        choices=["prototype", "mvp", "production"],
        help="단계 강제 지정 (없으면 answers.json → profile.json 순으로 자동 감지)"
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list",    help="전체 질문 목록 및 상태 출력")
    subparsers.add_parser("next",    help="다음 미답 필수 질문 JSON 출력")
    subparsers.add_parser("done",    help="모든 필수 질문 완료 여부 확인 (exit 0=완료)")
    subparsers.add_parser("missing", help="남은 필수 질문 목록 JSON 출력")

    ans_parser = subparsers.add_parser("answer", help="답변 1개 기록")
    ans_parser.add_argument("question_id", help="질문 ID (예: q0a, q6a)")
    ans_parser.add_argument("value", help="값 (JSON 리터럴 또는 문자열)")

    exp_parser = subparsers.add_parser("explain", help="특정 질문의 분기 매트릭스 확인")
    exp_parser.add_argument("question_id", help="질문 ID")

    reset_parser = subparsers.add_parser("reset", help="answers.json 초기화 (위험)")
    reset_parser.add_argument("--confirm", action="store_true", help="반드시 명시해야 초기화됨")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    answers_path = Path(args.answers)
    profile_path = Path(args.profile)

    # reset does not need yaml
    if args.command == "reset":
        return cmd_reset(args, answers_path)

    # Load data
    yaml_data = _load_yaml(QUESTIONS_YAML)
    all_questions: list = yaml_data.get("questions", [])
    answers: dict = _load_json(answers_path)
    if not answers:
        answers = {"schema_version": 1, "answered_by": "", "answered_at": "", "answers": {}}
    profile: dict = _load_json(profile_path)

    stage = _get_effective_stage(answers, profile, args.stage)

    if args.command == "list":
        return cmd_list(args, all_questions, answers, profile, stage)
    elif args.command == "next":
        return cmd_next(args, all_questions, answers, profile, stage)
    elif args.command == "done":
        return cmd_done(args, all_questions, answers, profile, stage)
    elif args.command == "missing":
        return cmd_missing(args, all_questions, answers, profile, stage)
    elif args.command == "answer":
        return cmd_answer(args, all_questions, answers, profile, stage, answers_path, profile_path)
    elif args.command == "explain":
        return cmd_explain(args, all_questions, answers, profile, stage)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
