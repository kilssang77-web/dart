"""
execute.py 단위 테스트.
새로운 phases/<task>/<runId>/ 2단 구조와 추가된 기능(preflight, auto-review, report, pr, references)을 검증한다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import execute as ex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project(tmp_path):
    """.harness/{phases,docs,release-notes,scripts}, CLAUDE.md 를 갖춘 임시 프로젝트 구조."""
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()

    phases_dir = harness_dir / "phases"
    phases_dir.mkdir()
    (phases_dir / "index.json").write_text(json.dumps({"runs": []}, ensure_ascii=False), encoding="utf-8")

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Rules\n- rule one\n- rule two", encoding="utf-8")

    docs_dir = harness_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "ARCHITECTURE.md").write_text("# Architecture\nSome content", encoding="utf-8")
    (docs_dir / "API_GUIDE.md").write_text("# API Guide\nAnother doc", encoding="utf-8")

    (harness_dir / "profile.json").write_text(
        json.dumps({"stage": "mvp", "project_name": "TestProject"}, ensure_ascii=False), encoding="utf-8"
    )
    (harness_dir / "references.json").write_text(json.dumps({"references": []}, ensure_ascii=False), encoding="utf-8")

    return tmp_path


@pytest.fixture
def run_dir(tmp_project):
    """step 3개를 가진 run 디렉토리 (.harness/phases/mvp/2026-05-13_20-00-00/)."""
    d = tmp_project / ".harness" / "phases" / "mvp" / "2026-05-13_20-00-00"
    d.mkdir(parents=True)

    index = {
        "project": "TestProject",
        "phase": "mvp",
        "branch": "feat-mvp",
        "stage": "mvp",
        "steps": [
            {"step": 0, "name": "setup", "status": "completed", "summary": "프로젝트 초기화 완료"},
            {"step": 1, "name": "core", "status": "completed", "summary": "핵심 로직 구현"},
            {"step": 2, "name": "ui", "status": "pending"},
        ],
    }
    (d / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=True), encoding="utf-8")
    (d / "step2.md").write_text("# Step 2: UI\n\nUI impl.", encoding="utf-8")

    # 글로벌 index.json에 등록
    top = tmp_project / ".harness" / "phases" / "index.json"
    top_data = json.loads(top.read_text(encoding="utf-8"))
    top_data["runs"].append({
        "task": "mvp", "run_id": "2026-05-13_20-00-00",
        "dir": "mvp/2026-05-13_20-00-00", "status": "pending",
        "stage": "mvp", "branch": "feat-mvp",
        "started_at": "2026-05-13T20:00:00+09:00",
    })
    top.write_text(json.dumps(top_data, indent=2, ensure_ascii=True), encoding="utf-8")

    return d


@pytest.fixture
def executor(tmp_project, run_dir):
    """테스트용 StepExecutor 인스턴스."""
    with patch.object(ex, "ROOT", tmp_project):
        inst = ex.StepExecutor("mvp", "2026-05-13_20-00-00", skip_preflight=True)

    inst._root = str(tmp_project)
    inst._phases_dir = tmp_project / ".harness" / "phases"
    inst._run_dir = run_dir
    inst._index_file = run_dir / "index.json"
    inst._guardrail_hash_file = run_dir / ".guardrail_hash"
    return inst


# ---------------------------------------------------------------------------
# _stamp
# ---------------------------------------------------------------------------

class TestStamp:
    def test_returns_kst_timestamp(self, executor):
        result = executor._stamp()
        assert "+0900" in result

    def test_format_is_iso(self, executor):
        result = executor._stamp()
        dt = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S%z")
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# _read_json / _write_json
# ---------------------------------------------------------------------------

class TestJsonHelpers:
    def test_roundtrip(self, tmp_path):
        data = {"key": "값", "nested": [1, 2, 3]}
        p = tmp_path / "test.json"
        ex.StepExecutor._write_json(p, data)
        loaded = ex.StepExecutor._read_json(p)
        assert loaded == data

    def test_save_ensures_ascii_false(self, tmp_path):
        p = tmp_path / "test.json"
        ex.StepExecutor._write_json(p, {"hangeul": "test"})
        raw = p.read_text(encoding="utf-8")
        assert "hangeul" in raw


# ---------------------------------------------------------------------------
# _load_guardrails (선택적 주입 포함)
# ---------------------------------------------------------------------------

class TestLoadGuardrails:
    def test_loads_claude_md_and_docs(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "# Rules" in result
        assert "# Architecture" in result

    def test_loads_profile_section(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "mvp" in result  # 단계 주입

    def test_selective_docs_with_relevant_docs_frontmatter(self, executor, tmp_project, run_dir):
        """relevant_docs frontmatter가 있으면 해당 파일만 주입한다."""
        (run_dir / "step2.md").write_text(
            '---\nrelevant_docs: ["ARCHITECTURE"]\n---\n\n# Step 2', encoding="utf-8"
        )
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails(step_num=2)
        assert "ARCHITECTURE" in result
        # API_GUIDE는 포함되지 않아야 함
        assert "API Guide" not in result

    def test_full_docs_injection_when_no_frontmatter(self, executor, tmp_project, run_dir):
        """frontmatter 없으면 전체 docs 주입."""
        (run_dir / "step2.md").write_text("# Step 2: No frontmatter", encoding="utf-8")
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails(step_num=2)
        assert "# Architecture" in result
        assert "# API Guide" in result

    def test_no_docs_dir(self, executor, tmp_project):
        import shutil
        shutil.rmtree(tmp_project / ".harness" / "docs")
        with patch.object(ex, "ROOT", tmp_project):
            result = executor._load_guardrails()
        assert "# Rules" in result


# ---------------------------------------------------------------------------
# _build_step_context (최신 3개 full, 이전 80자 trim)
# ---------------------------------------------------------------------------

class TestBuildStepContext:
    def test_includes_completed_with_summary(self, run_dir):
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        result = ex.StepExecutor._build_step_context(index, 2)
        assert "Step 0 (setup): 프로젝트 초기화 완료" in result
        assert "Step 1 (core): 핵심 로직 구현" in result

    def test_excludes_pending(self, run_dir):
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        result = ex.StepExecutor._build_step_context(index, 2)
        assert "ui" not in result

    def test_empty_when_no_completed(self):
        index = {"steps": [{"step": 0, "name": "a", "status": "pending"}]}
        result = ex.StepExecutor._build_step_context(index, 0)
        assert result == ""

    def test_has_header(self, run_dir):
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        result = ex.StepExecutor._build_step_context(index, 2)
        assert result.startswith("## 이전 Step 산출물")

    def test_old_steps_are_trimmed(self, executor, run_dir):
        """4번째 이상 이전 step은 80자로 trim된다."""
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        long_summary = "a" * 200
        for i in range(5):
            index["steps"].insert(0, {
                "step": -(i + 1), "name": f"old{i}",
                "status": "completed", "summary": long_summary,
            })
        result = ex.StepExecutor._build_step_context(index, 2)
        assert "..." in result  # trim 발생


# ---------------------------------------------------------------------------
# _build_preamble
# ---------------------------------------------------------------------------

class TestBuildPreamble:
    def test_includes_project_name(self, executor):
        result = executor._build_preamble("", "", step_num=0)
        assert "TestProject" in result

    def test_includes_guardrails(self, executor):
        result = executor._build_preamble("GUARD_CONTENT", "", step_num=0)
        assert "GUARD_CONTENT" in result

    def test_includes_rules(self, executor):
        result = executor._build_preamble("", "", step_num=0)
        assert "작업 규칙" in result

    def test_no_retry_section_by_default(self, executor):
        result = executor._build_preamble("", "", step_num=0)
        assert "이전 시도 실패" not in result

    def test_retry_section_with_prev_error(self, executor):
        result = executor._build_preamble("", "", step_num=0, prev_error="타입 에러 발생")
        assert "이전 시도 실패" in result

    def test_guardrail_unchanged_on_retry(self, executor, run_dir):
        """재시도 시 가드레일이 동일하면 [GUARDRAIL_UNCHANGED]로 교체한다."""
        guardrails = "original guardrail content"
        h = executor._compute_guardrail_hash(guardrails)
        executor._save_guardrail_hash(h)
        result = executor._build_preamble(guardrails, "", step_num=0, is_retry=True)
        assert "GUARDRAIL_UNCHANGED" in result

    def test_guardrail_new_on_first_attempt(self, executor):
        """첫 시도면 가드레일을 그대로 포함한다."""
        result = executor._build_preamble("MY_GUARD", "", step_num=0, is_retry=False)
        assert "MY_GUARD" in result


# ---------------------------------------------------------------------------
# _update_top_index (새 구조: runs[])
# ---------------------------------------------------------------------------

class TestUpdateTopIndex:
    def test_completed(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            executor._phases_dir = tmp_project / ".harness" / "phases"
            executor._update_top_index("completed")
        data = json.loads((tmp_project / ".harness" / "phases" / "index.json").read_text(encoding="utf-8"))
        run = next(r for r in data["runs"] if r["dir"] == "mvp/2026-05-13_20-00-00")
        assert run["status"] == "completed"
        assert "completed_at" in run

    def test_error(self, executor, tmp_project):
        with patch.object(ex, "ROOT", tmp_project):
            executor._phases_dir = tmp_project / ".harness" / "phases"
            executor._update_top_index("error")
        data = json.loads((tmp_project / ".harness" / "phases" / "index.json").read_text(encoding="utf-8"))
        run = next(r for r in data["runs"] if r["dir"] == "mvp/2026-05-13_20-00-00")
        assert run["status"] == "error"
        assert "failed_at" in run

    def test_other_runs_unchanged(self, executor, tmp_project):
        """다른 run은 변경되지 않는다."""
        top = tmp_project / ".harness" / "phases" / "index.json"
        data = json.loads(top.read_text(encoding="utf-8"))
        data["runs"].append({
            "task": "other", "run_id": "2026-05-14_10-00-00",
            "dir": "other/2026-05-14_10-00-00", "status": "pending",
        })
        top.write_text(json.dumps(data), encoding="utf-8")

        with patch.object(ex, "ROOT", tmp_project):
            executor._phases_dir = tmp_project / ".harness" / "phases"
            executor._update_top_index("completed")

        updated = json.loads(top.read_text(encoding="utf-8"))
        other = next(r for r in updated["runs"] if r["dir"] == "other/2026-05-14_10-00-00")
        assert other["status"] == "pending"


# ---------------------------------------------------------------------------
# _preflight
# ---------------------------------------------------------------------------

class TestPreflight:
    def test_skip_preflight_flag(self, executor):
        """--skip-preflight 시 preflight가 실행되지 않는다."""
        executor._skip_preflight = True
        # 어떤 git/subprocess 호출도 없어야 함
        with patch.object(executor, "_run_git", side_effect=AssertionError("git called")) as m:
            with patch.object(executor, "_run_security_scan", side_effect=AssertionError):
                executor._preflight()  # AssertionError가 발생하면 실패

    def test_profile_missing_exits(self, executor, tmp_project):
        """profile.json 없으면 sys.exit(1)."""
        executor._skip_preflight = False
        (tmp_project / ".harness" / "profile.json").unlink()

        # git status clean 반환
        executor._run_git = MagicMock(return_value=MagicMock(returncode=0, stdout=""))

        with patch.object(ex, "ROOT", tmp_project):
            with pytest.raises(SystemExit) as exc_info:
                executor._preflight()
        assert exc_info.value.code == 1

    def test_production_triggers_security_scan(self, executor, tmp_project):
        """production 단계이면 보안 스캔을 실행한다."""
        executor._skip_preflight = False
        (tmp_project / ".harness" / "profile.json").write_text(
            json.dumps({"stage": "production"}), encoding="utf-8"
        )
        executor._run_git = MagicMock(return_value=MagicMock(returncode=0, stdout=""))

        scan_called = []
        executor._run_security_scan = lambda: scan_called.append(True)

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout='{"summary":{"errors":0}}')
            with patch.object(ex, "ROOT", tmp_project):
                executor._preflight()

        assert scan_called


# ---------------------------------------------------------------------------
# _invoke_claude (출력 분리 저장)
# ---------------------------------------------------------------------------

class TestInvokeClaude:
    def test_invokes_claude_with_correct_args(self, executor):
        mock_result = MagicMock(returncode=0, stdout='{"result": "ok"}', stderr="")
        step = {"step": 2, "name": "ui"}

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            executor._invoke_claude(step, "PREAMBLE\n")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "--dangerously-skip-permissions" in cmd
        assert "PREAMBLE" in cmd[-1]

    def test_saves_output_json_with_metadata_only(self, executor):
        """output.json은 메타+요약만 저장한다 (전체 stdout은 별도)."""
        long_stdout = "x" * 10000
        mock_result = MagicMock(returncode=0, stdout=long_stdout, stderr="")
        step = {"step": 2, "name": "ui"}

        with patch("subprocess.run", return_value=mock_result):
            executor._invoke_claude(step, "preamble")

        output_file = executor._run_dir / "step2-output.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(data["stdout_summary"]) <= ex.StepExecutor.OUTPUT_MAX_BYTES
        assert "stdout_log" in data

    def test_saves_full_stdout_to_log_file(self, executor):
        """전체 stdout은 step{N}-stdout.log에 저장된다."""
        long_stdout = "full output " * 1000
        mock_result = MagicMock(returncode=0, stdout=long_stdout, stderr="")
        step = {"step": 2, "name": "ui"}

        with patch("subprocess.run", return_value=mock_result):
            executor._invoke_claude(step, "preamble")

        log_file = executor._run_dir / "step2-stdout.log"
        assert log_file.exists()
        assert log_file.read_text(encoding="utf-8") == long_stdout

    def test_nonexistent_step_file_exits(self, executor):
        step = {"step": 99, "name": "nonexistent"}
        with pytest.raises(SystemExit) as exc_info:
            executor._invoke_claude(step, "preamble")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_creates_report_md(self, executor, run_dir):
        """_generate_report가 REPORT.md를 생성한다."""
        executor._run_git = MagicMock(
            return_value=MagicMock(returncode=0, stdout="abc123 feat: test\n", stderr="")
        )

        # completed_at 설정
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        index["completed_at"] = "2026-05-13T21:00:00+09:00"
        (run_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

        with patch.object(ex, "ROOT", executor._phases_dir.parent):
            executor._generate_report()

        report = run_dir / "REPORT.md"
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "mvp" in content
        assert "2026-05-13_20-00-00" in content

    def test_report_contains_step_table(self, executor, run_dir):
        """리포트에 step 결과 표가 포함된다."""
        executor._run_git = MagicMock(
            return_value=MagicMock(returncode=0, stdout="", stderr="")
        )
        with patch.object(ex, "ROOT", executor._phases_dir.parent):
            executor._generate_report()

        report = (run_dir / "REPORT.md").read_text(encoding="utf-8")
        assert "setup" in report
        assert "core" in report


# ---------------------------------------------------------------------------
# _create_pr_mr (mocked)
# ---------------------------------------------------------------------------

class TestCreatePrMr:
    def test_gitlab_mr_created(self, executor):
        """GitLab origin이면 glab mr create를 호출한다."""
        executor._run_git = MagicMock(
            return_value=MagicMock(returncode=0, stdout="https://gitlab.com/user/repo.git\n")
        )
        executor._run_dir.joinpath("REPORT.md").write_text("report content", encoding="utf-8")

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout="https://mr-url", stderr="")
            executor._create_pr_mr()

        call_args = mock_sub.call_args[0][0]
        assert "glab" in call_args

    def test_github_pr_created(self, executor):
        """GitHub origin이면 gh pr create를 호출한다."""
        executor._run_git = MagicMock(
            return_value=MagicMock(returncode=0, stdout="https://github.com/user/repo.git\n")
        )
        executor._run_dir.joinpath("REPORT.md").write_text("report", encoding="utf-8")

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout="https://pr-url", stderr="")
            executor._create_pr_mr()

        call_args = mock_sub.call_args[0][0]
        assert "gh" in call_args

    def test_no_remote_skips_pr(self, executor):
        """원격 없으면 PR/MR 건너뜀."""
        executor._run_git = MagicMock(
            return_value=MagicMock(returncode=1, stdout="", stderr="no remote")
        )
        with patch("subprocess.run") as mock_sub:
            executor._create_pr_mr()
        mock_sub.assert_not_called()


# ---------------------------------------------------------------------------
# _check_blockers
# ---------------------------------------------------------------------------

class TestCheckBlockers:
    def test_error_step_exits_1(self, executor, run_dir):
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        index["steps"][1]["status"] = "error"
        index["steps"][1]["error_message"] = "fail"
        (run_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            executor._check_blockers()
        assert exc_info.value.code == 1

    def test_blocked_step_exits_2(self, executor, run_dir):
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        index["steps"][1]["status"] = "blocked"
        index["steps"][1]["blocked_reason"] = "API key"
        (run_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            executor._check_blockers()
        assert exc_info.value.code == 2

    def test_all_pending_no_exit(self, executor, run_dir):
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        for s in index["steps"]:
            s["status"] = "pending"
        (run_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
        executor._check_blockers()  # should not raise


# ---------------------------------------------------------------------------
# progress_indicator
# ---------------------------------------------------------------------------

class TestProgressIndicator:
    def test_context_manager(self):
        import time
        with ex.progress_indicator("test") as pi:
            time.sleep(0.15)
        assert pi.elapsed >= 0.1

    def test_elapsed_increases(self):
        import time
        with ex.progress_indicator("test") as pi:
            time.sleep(0.2)
        assert pi.elapsed > 0


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------

class TestMainCli:
    def test_no_args_exits(self):
        with patch("sys.argv", ["execute.py"]):
            with pytest.raises(SystemExit):
                ex.main()

    def test_resume_no_runs_exits(self, tmp_project):
        with patch("sys.argv", ["execute.py", "--resume"]):
            with patch.object(ex, "ROOT", tmp_project):
                with patch("execute.scan_resumable_runs", return_value=[]):
                    with pytest.raises(SystemExit) as exc_info:
                        ex.main()
        assert exc_info.value.code == 0  # "재개 가능한 run 없음"은 0으로 종료

    def test_invalid_run_dir_exits(self, tmp_project):
        with patch("sys.argv", ["execute.py", "nonexistent/2026-01-01_00-00-00"]):
            with patch.object(ex, "ROOT", tmp_project):
                with pytest.raises(SystemExit) as exc_info:
                    ex.main()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _register_run
# ---------------------------------------------------------------------------

class TestRegisterRun:
    def test_appends_to_runs(self, tmp_project):
        phases_dir = tmp_project / ".harness" / "phases"
        ex._register_run(phases_dir, "feature", "2026-05-14_10-00-00", "mvp", "feat-feature")
        data = json.loads((phases_dir / "index.json").read_text(encoding="utf-8"))
        assert any(r["run_id"] == "2026-05-14_10-00-00" for r in data["runs"])

    def test_creates_index_if_missing(self, tmp_path):
        phases_dir = tmp_path / "phases"
        phases_dir.mkdir()
        ex._register_run(phases_dir, "task", "2026-05-14_10-00-00", "mvp", "feat-task")
        assert (phases_dir / "index.json").exists()
        data = json.loads((phases_dir / "index.json").read_text(encoding="utf-8"))
        assert len(data["runs"]) == 1


# ---------------------------------------------------------------------------
# _ensure_unique_run_id
# ---------------------------------------------------------------------------

class TestEnsureUniqueRunId:
    def test_no_conflict(self, tmp_path):
        task_dir = tmp_path / "task"
        task_dir.mkdir()
        result = ex._ensure_unique_run_id(task_dir, "2026-05-13_20-00-00")
        assert result == "2026-05-13_20-00-00"

    def test_conflict_adds_suffix(self, tmp_path):
        task_dir = tmp_path / "task"
        task_dir.mkdir()
        (task_dir / "2026-05-13_20-00-00").mkdir()
        result = ex._ensure_unique_run_id(task_dir, "2026-05-13_20-00-00")
        assert result == "2026-05-13_20-00-00_2"
