#!/usr/bin/env python3
"""
review_docs.py — AI 페르소나 기반 docs 충실도 2차 평가 게이트

흐름:
  1. validate_docs.py(syntactic) 1차 게이트 — 실패 시 즉시 중단
  2. personas.yaml + profile.json + docs 로드
  3. Claude CLI 단일 호출로 멀티-페르소나 채점
  4. critical veto 및 평균 임계점수 확인
  5. 미달 시: auto_fillable gap 자동 보완(diff 확인 후 적용) → needs_decision gap Q&A → 재채점
  6. 최대 max_iterations 회 반복 후 종료

CLI:
  python .harness/scripts/review_docs.py [--stage prototype|mvp|production]
                                          [--threshold INT]
                                          [--deep]
                                          [--no-autofill]
                                          [--no-qa]
                                          [--max-iter INT]
                                          [--json]
                                          [--out PATH]
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / ".harness" / "docs"
PERSONAS_FILE = ROOT / ".harness" / "personas.yaml"
PROFILE_FILE = ROOT / ".harness" / "profile.json"
REVIEW_CACHE_DIR = DOCS_DIR / ".review"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    if not HAS_YAML:
        print(f"  WARN: PyYAML 미설치. `pip install pyyaml` 후 재실행하세요.", file=sys.stderr)
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_profile() -> dict:
    if not PROFILE_FILE.exists():
        return {}
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_personas(stage: str, project_type: str) -> list[dict]:
    """personas.yaml에서 해당 stage에 활성화된 페르소나 목록을 반환한다."""
    catalog = _load_yaml(PERSONAS_FILE)
    personas_raw = catalog.get("personas", [])
    result = []

    for p in personas_raw:
        pid = p.get("id", "")
        stages = dict(p.get("stages", {}))

        # project_type_override 적용
        override = p.get("project_type_override", {}).get(project_type, {})
        if override.get("stages"):
            stages.update(override["stages"])

        activation = stages.get(stage, "off")
        if activation == "off":
            continue

        weight_by_stage = dict(p.get("weight_by_stage", {}))
        override_weights = override.get("weight_by_stage", {})
        weight_by_stage.update(override_weights)
        weight = float(weight_by_stage.get(stage, 1.0))
        if activation == "minimal":
            weight = min(weight, 0.5)

        critical_by_stage = dict(p.get("critical_by_stage", {}))
        override_critical = override.get("critical_by_stage", {})
        critical_by_stage.update(override_critical)
        is_critical = bool(critical_by_stage.get(stage, False))

        rubric_by_stage = dict(p.get("rubric_by_stage", {}))
        override_rubric = override.get("rubric_by_stage", {})
        if stage in override_rubric:
            rubric_by_stage[stage] = override_rubric[stage]
        rubric = rubric_by_stage.get(stage, [])

        result.append({
            "id": pid,
            "name": p.get("name", pid),
            "scope": p.get("scope", ["*"]),
            "activation": activation,
            "weight": weight,
            "critical": is_critical,
            "rubric": rubric,
        })

    return result


def _load_docs_for_scope(scope: list[str]) -> str:
    """scope에 해당하는 docs 내용을 로드한다. ["*"]는 전체."""
    docs: list[str] = []
    if not DOCS_DIR.is_dir():
        return ""

    for doc_path in sorted(DOCS_DIR.glob("*.md")):
        stem = doc_path.stem
        if stem.startswith("."):
            continue
        if scope == ["*"] or stem in scope:
            try:
                content = doc_path.read_text(encoding="utf-8")
                docs.append(f"=== {stem}.md ===\n{content}")
            except OSError:
                pass

    return "\n\n".join(docs)


def _docs_hash() -> str:
    """docs 디렉토리의 해시를 계산한다 (캐시 무효화용)."""
    h = hashlib.sha256()
    if not DOCS_DIR.is_dir():
        return ""
    for p in sorted(DOCS_DIR.glob("*.md")):
        if p.stem.startswith("."):
            continue
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:16]


def _load_cached_review(stage: str) -> Optional[dict]:
    """최근 review 캐시가 있고 docs 해시가 같으면 반환한다."""
    if not REVIEW_CACHE_DIR.is_dir():
        return None
    candidates = sorted(REVIEW_CACHE_DIR.glob(f"{stage}_*.json"), reverse=True)
    if not candidates:
        return None
    try:
        cached = json.loads(candidates[0].read_text(encoding="utf-8"))
        if cached.get("docs_hash") == _docs_hash():
            return cached
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_review(result: dict, stage: str, out_path: Optional[Path]) -> Path:
    """review 결과를 캐시에 저장한다."""
    REVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    save_path = out_path or REVIEW_CACHE_DIR / f"{stage}_{ts}.json"
    save_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return save_path


def _build_review_prompt(personas: list[dict], stage: str, docs_text: str) -> str:
    """Claude에게 보낼 채점 프롬프트를 구성한다."""
    persona_section = []
    for p in personas:
        rubric_str = "\n".join(f"  - {r}" for r in p["rubric"])
        critical_label = " [CRITICAL — veto 권한]" if p["critical"] else ""
        persona_section.append(
            f"### {p['name']} (id: {p['id']}, weight: {p['weight']:.1f}{critical_label})\n"
            f"검토 범위: {', '.join(p['scope'])}\n"
            f"채점 기준:\n{rubric_str}"
        )

    persona_text = "\n\n".join(persona_section)

    return f"""당신은 소프트웨어 프로젝트 문서 품질을 평가하는 전문 심사단입니다.
아래 페르소나로서 각각 독립적으로 문서를 채점하고, 구조화된 JSON을 반환하세요.

## 현재 프로젝트 단계
{stage}

## 페르소나 및 채점 기준
{persona_text}

## 검토 대상 문서
{docs_text}

## 출력 형식 (반드시 이 JSON만 출력하세요)
{{
  "scores": [
    {{
      "persona": "<persona_id>",
      "score": <0~100 정수>,
      "weight": <가중치>,
      "critical": <true|false>,
      "summary": "<2~3줄 총평>",
      "gaps": [
        {{
          "id": "g-<001>",
          "doc": "<문서명>",
          "section": "<섹션명>",
          "kind": "auto_fillable",
          "summary": "<문제 요약>",
          "proposed_patch": "<자동 보완 내용 (명확한 경우)>",
          "rationale": "<근거>"
        }},
        {{
          "id": "g-<002>",
          "doc": "<문서명>",
          "section": "<섹션명>",
          "kind": "needs_decision",
          "summary": "<문제 요약>",
          "question": "<사용자에게 물어볼 질문>",
          "options": ["<옵션1>", "<옵션2>"]
        }}
      ]
    }}
  ]
}}

채점 원칙:
- 각 rubric 항목이 충족되면 +10점, 부분 충족 +5점, 미충족 0점으로 100점 만점 환산
- auto_fillable: 코드베이스/CLAUDE.md/profile.json/references 컨텍스트로 AI가 채울 수 있는 경우
- needs_decision: 설계 결정·사용자 선호가 필요한 경우
- JSON 이외 텍스트는 출력하지 마세요
"""


def _call_claude(prompt: str) -> Optional[dict]:
    """Claude CLI를 호출하여 JSON 결과를 반환한다."""
    cmd = ["claude", "-p", "--output-format", "text"]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        output = result.stdout.strip()
        # JSON 블록 추출
        match = re.search(r"\{[\s\S]*\}", output)
        if match:
            return json.loads(match.group())
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"  WARN: Claude 호출 실패: {e}", file=sys.stderr)
    return None


def _compute_scores(llm_result: dict, personas: list[dict]) -> dict:
    """LLM 결과에서 가중 평균 점수와 critical veto를 계산한다."""
    persona_map = {p["id"]: p for p in personas}
    scores = llm_result.get("scores", [])

    total_weight = 0.0
    weighted_sum = 0.0
    veto_by: list[str] = []
    all_gaps: list[dict] = []

    score_list = []
    for s in scores:
        pid = s.get("persona", "")
        score = float(s.get("score", 0))
        p = persona_map.get(pid, {})
        weight = p.get("weight", 1.0)
        is_critical = p.get("critical", False)

        weighted_sum += score * weight
        total_weight += weight

        if is_critical and score < 60:
            veto_by.append(pid)

        score_list.append({
            "persona": pid,
            "score": score,
            "weight": weight,
            "critical": is_critical,
            "summary": s.get("summary", ""),
        })

        for gap in s.get("gaps", []):
            all_gaps.append(gap)

    average = (weighted_sum / total_weight) if total_weight > 0 else 0.0

    return {
        "average": round(average, 1),
        "veto_by": veto_by,
        "scores": score_list,
        "gaps": all_gaps,
    }


def _apply_autofill_gap(gap: dict, interactive: bool) -> bool:
    """auto_fillable gap을 문서에 적용한다. diff 확인 후 사용자 승인 필요."""
    doc_name = gap.get("doc", "")
    patch = gap.get("proposed_patch", "")
    if not doc_name or not patch:
        return False

    doc_path = DOCS_DIR / f"{doc_name}.md"
    if not doc_path.exists():
        return False

    print(f"\n  [자동 보완 제안] {doc_name}.md — {gap.get('summary', '')}")
    print(f"  근거: {gap.get('rationale', '')}")
    print(f"  내용:\n{patch}")

    if interactive:
        answer = input("  적용하시겠습니까? [Y/n] ").strip().lower()
        if answer in ("n", "no"):
            return False

    # 문서 끝에 보완 내용 추가
    existing = doc_path.read_text(encoding="utf-8")
    section = gap.get("section", "자동 보완")
    new_content = existing.rstrip() + f"\n\n## {section} (자동 보완)\n\n{patch}\n"
    doc_path.write_text(new_content, encoding="utf-8")
    print(f"  ✓ {doc_name}.md에 반영되었습니다.")
    return True


def _ask_qa_gap(gap: dict) -> Optional[str]:
    """needs_decision gap을 사용자에게 Q&A로 종결한다."""
    if not sys.stdin.isatty():
        return None

    print(f"\n  [결정 필요] {gap.get('doc', '')} — {gap.get('summary', '')}")
    question = gap.get("question", "")
    options = gap.get("options", [])
    if question:
        print(f"  {question}")
    if options:
        for i, opt in enumerate(options, 1):
            print(f"    {i}. {opt}")
    answer = input("  답변: ").strip()
    return answer if answer else None


def _print_result(result: dict):
    verdict = result.get("verdict", "unknown")
    stage = result.get("stage", "?")
    icon = "✓" if verdict == "pass" else "✗"
    print(f"\n[페르소나 리뷰] stage={stage}  {icon} {verdict.upper()}")

    # 조기 반환(error/skip/syntactic_gate 등) 경우 상세 없이 사유만 출력
    reason = result.get("reason", "")
    if reason:
        print(f"  사유: {reason}")

    average = result.get("average")
    threshold = result.get("threshold")
    if average is not None and threshold is not None:
        print(f"  평균 점수: {average:.1f} / 임계: {threshold}")

    veto_by = result.get("veto_by")
    if veto_by:
        print(f"  Veto 페르소나: {', '.join(veto_by)}")

    scores = result.get("scores", [])
    if scores:
        print()
        for s in scores:
            crit = " [CRITICAL]" if s.get("critical") else ""
            persona = s.get("persona", "?")
            score = s.get("score", 0)
            weight = s.get("weight", 1.0)
            print(f"  {persona:20s} {score:5.1f}점 (x{weight:.1f}){crit}")
            if s.get("summary"):
                print(f"    └ {s['summary']}")

    gaps = result.get("gaps", [])
    if gaps:
        print(f"\n  갭 {len(gaps)}건:")
        for g in gaps:
            kind_icon = "🔧" if g.get("kind") == "auto_fillable" else "❓"
            print(f"    {kind_icon} [{g.get('doc', '')}] {g.get('summary', '')}")


def review(
    stage: str,
    threshold: Optional[int],
    deep: bool,
    no_autofill: bool,
    no_qa: bool,
    max_iter: int,
    out_path: Optional[Path],
) -> dict:
    """페르소나 리뷰 메인 로직. 결과 dict를 반환한다."""

    # ─── Step 1: validate_docs.py syntactic 1차 게이트 ───
    val_result = subprocess.run(
        [sys.executable, str(ROOT / ".harness" / "scripts" / "validate_docs.py"),
         "--stage", stage, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        val_data = json.loads(val_result.stdout)
        if val_data.get("summary", {}).get("errors", 0) > 0:
            print("  ✗ syntactic 검사 실패. 먼저 오류를 수정하세요.", file=sys.stderr)
            return {
                "stage": stage,
                "verdict": "fail",
                "reason": "syntactic_gate",
                "validate_result": val_data,
            }
    except (json.JSONDecodeError, OSError):
        pass

    # ─── Step 2: 설정 로드 ───
    profile = _load_profile()
    project_type = profile.get("project_type", "")
    review_cfg = profile.get("review", {})

    # 임계점수 결정 (profile override > 인수 > personas.yaml > 기본값)
    personas_catalog = _load_yaml(PERSONAS_FILE)
    catalog_thresholds = personas_catalog.get("thresholds", {}).get(stage, {})
    default_avg_threshold = catalog_thresholds.get("average", {"prototype": 70, "mvp": 80, "production": 90}.get(stage, 80))
    default_critical_min = catalog_thresholds.get("critical_min", {"prototype": 50, "mvp": 60, "production": 70}.get(stage, 60))

    profile_thresholds = review_cfg.get("thresholds", {})
    avg_threshold = threshold or profile_thresholds.get(stage, default_avg_threshold)
    critical_min_cfg = review_cfg.get("critical_min", {})
    if isinstance(critical_min_cfg, dict):
        critical_min = critical_min_cfg.get(stage, default_critical_min)
    else:
        critical_min = default_critical_min

    effective_max_iter = review_cfg.get("max_iterations", max_iter)

    # ─── Step 3: 페르소나 로드 ───
    personas = _load_personas(stage, project_type)
    if not personas:
        return {
            "stage": stage,
            "verdict": "skip",
            "reason": "no_active_personas",
        }

    # ─── Step 4: 캐시 확인 ───
    cached = _load_cached_review(stage)
    if cached and cached.get("threshold") == avg_threshold:
        print(f"  INFO: 캐시된 리뷰 결과 사용 (docs 변경 없음). --no-cache 옵션으로 강제 재실행 가능.")
        return cached

    # ─── Step 5: 반복 채점 루프 ───
    iteration = 0
    prev_average = -1.0
    decline_count = 0
    all_applied_patches = 0

    while iteration < effective_max_iter:
        iteration += 1
        print(f"\n  [리뷰 iteration {iteration}/{effective_max_iter}] 페르소나 {len(personas)}명 채점 중...")

        # docs 로드 (매 iteration 새로 읽음)
        if deep:
            # 페르소나별 분리 호출
            all_scores: list[dict] = []
            all_gaps: list[dict] = []
            for p in personas:
                docs_text = _load_docs_for_scope(p["scope"])
                prompt = _build_review_prompt([p], stage, docs_text)
                llm_raw = _call_claude(prompt)
                if llm_raw:
                    for s in llm_raw.get("scores", []):
                        all_scores.append(s)
                        all_gaps.extend(s.get("gaps", []))
            computed = _compute_scores({"scores": all_scores}, personas)
        else:
            docs_text = _load_docs_for_scope(["*"])
            prompt = _build_review_prompt(personas, stage, docs_text)
            llm_raw = _call_claude(prompt)
            if not llm_raw:
                return {"stage": stage, "verdict": "error", "reason": "llm_call_failed"}
            computed = _compute_scores(llm_raw, personas)

        average = computed["average"]
        veto_by = computed["veto_by"]
        gaps = computed["gaps"]

        # 연속 점수 하락 감지
        if prev_average >= 0:
            if average < prev_average:
                decline_count += 1
            else:
                decline_count = 0
        if decline_count >= 2:
            print("  WARN: 연속 2회 점수 하락. 자동 보완 루프 중단.")
            break
        prev_average = average

        # 통과 여부 확인
        critical_pass = all(
            next((s["score"] for s in computed["scores"] if s["persona"] == vid), 0) >= critical_min
            for vid in veto_by
        ) if veto_by else True
        passed = (average >= avg_threshold) and critical_pass

        if passed:
            break

        if iteration >= effective_max_iter:
            break

        # ─── auto_fillable 갭 처리 ───
        if not no_autofill:
            interactive = not no_qa and sys.stdin.isatty()
            auto_gaps = [g for g in gaps if g.get("kind") == "auto_fillable"]
            for gap in auto_gaps:
                if _apply_autofill_gap(gap, interactive):
                    all_applied_patches += 1

        # ─── needs_decision 갭 처리 ───
        if not no_qa and sys.stdin.isatty():
            decision_gaps = [g for g in gaps if g.get("kind") == "needs_decision"]
            for gap in decision_gaps:
                _ask_qa_gap(gap)

    # ─── 최종 결과 조립 ───
    critical_pass = all(
        next((s["score"] for s in computed["scores"] if s["persona"] == vid), 0) >= critical_min
        for vid in veto_by
    ) if veto_by else True
    verdict = "pass" if (average >= avg_threshold and critical_pass) else "fail"

    result: dict[str, Any] = {
        "stage": stage,
        "threshold": avg_threshold,
        "critical_min": critical_min,
        "average": average,
        "iteration": iteration,
        "scores": computed["scores"],
        "verdict": verdict,
        "veto_by": veto_by,
        "gaps": computed["gaps"],
        "docs_hash": _docs_hash(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "applied_patches": all_applied_patches,
    }

    save_path = _save_review(result, stage, out_path)
    print(f"  리뷰 결과 저장: {save_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="AI 페르소나 docs 충실도 2차 평가 게이트")
    parser.add_argument("--stage", choices=["prototype", "mvp", "production"], default="mvp")
    parser.add_argument("--threshold", type=int, default=None, help="평균 임계점수 override")
    parser.add_argument("--deep", action="store_true", help="페르소나별 분리 호출 (비용 주의)")
    parser.add_argument("--no-autofill", action="store_true", help="자동 보완 비활성화")
    parser.add_argument("--no-qa", action="store_true", help="비대화형(CI용) — Q&A 없음")
    parser.add_argument("--max-iter", type=int, default=3, help="최대 반복 횟수")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON 출력")
    parser.add_argument("--out", type=Path, default=None, help="결과 저장 경로")
    args = parser.parse_args()

    # profile.json에서 stage 자동 감지
    if args.stage == "mvp":
        profile = _load_profile()
        detected_stage = profile.get("stage", "mvp")
        if detected_stage in ("prototype", "mvp", "production"):
            args.stage = detected_stage

    result = review(
        stage=args.stage,
        threshold=args.threshold,
        deep=args.deep,
        no_autofill=args.no_autofill,
        no_qa=args.no_qa,
        max_iter=args.max_iter,
        out_path=args.out,
    )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_result(result)

    verdict = result.get("verdict", "fail")
    sys.exit(0 if verdict == "pass" else 1)


if __name__ == "__main__":
    main()
