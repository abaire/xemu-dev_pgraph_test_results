from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_plan_hw_diffs_empty(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    output_dir = tmp_path / "compare-results"
    output_dir.mkdir()
    plan_file = tmp_path / "diff_tasks.json"
    github_output = tmp_path / "github_output.txt"

    env = {"GITHUB_OUTPUT": str(github_output)}
    script = Path(".github/scripts/plan_hw_diffs.py").resolve()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_dir),
            "--output-dir",
            str(output_dir),
            "--output-plan-file",
            str(plan_file),
            "--max-shards",
            "4",
            "--force",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "diff_count=0" in result.stdout
    assert "shard_count=0" in result.stdout

    with open(plan_file, encoding="utf-8") as f:
        tasks = json.load(f)
    assert tasks == []

    output_content = github_output.read_text(encoding="utf-8")
    assert "diff_count=0" in output_content
    assert "shard_count=0" in output_content
    assert 'matrix={"shard": []}' in output_content


def test_plan_xemu_diffs_missing_baseline(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    output_dir = tmp_path / "compare-results"
    output_dir.mkdir()
    plan_file = tmp_path / "diff_tasks_xemu.json"
    github_output = tmp_path / "github_output.txt"

    env = {"GITHUB_OUTPUT": str(github_output)}
    script = Path(".github/scripts/plan_xemu_diffs.py").resolve()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_dir),
            "--output-dir",
            str(output_dir),
            "--output-plan-file",
            str(plan_file),
            "--max-shards",
            "4",
            "--force",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "diff_count=0" in result.stdout
    assert "shard_count=0" in result.stdout

    with open(plan_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["tasks"] == []

    output_content = github_output.read_text(encoding="utf-8")
    assert "diff_count=0" in output_content
    assert "shard_count=0" in output_content
    assert 'matrix={"shard": []}' in output_content


def test_plan_xemu_diffs_empty(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    baseline_dir = tmp_path / "baseline"
    baseline_run = (
        baseline_dir / "xemu-0.8.134" / "Darwin_arm64" / "gl_Apple" / "gslv_4.10"
    )
    (baseline_run / "suite_1").mkdir(parents=True)
    (baseline_run / "results.json").write_text("{}", encoding="utf-8")

    output_dir = tmp_path / "compare-results"
    output_dir.mkdir()
    plan_file = tmp_path / "diff_tasks_xemu.json"
    github_output = tmp_path / "github_output.txt"

    env = {"GITHUB_OUTPUT": str(github_output)}
    script = Path(".github/scripts/plan_xemu_diffs.py").resolve()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--results-dir",
            str(results_dir),
            "--baseline-dir",
            str(baseline_dir),
            "--output-dir",
            str(output_dir),
            "--output-plan-file",
            str(plan_file),
            "--max-shards",
            "4",
            "--force",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "diff_count=0" in result.stdout
    assert "shard_count=0" in result.stdout

    with open(plan_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["tasks"] == []

    output_content = github_output.read_text(encoding="utf-8")
    assert "diff_count=0" in output_content
    assert "shard_count=0" in output_content
    assert 'matrix={"shard": []}' in output_content


def test_plan_hw_diffs_filters_deprecated_tasks(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from xemu_pgraph_ci_tools.golden_config import GoldenConfig

    scripts_dir = str(Path(__file__).parent.parent / ".github" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import plan_hw_diffs

    task1 = MagicMock()
    task1.suite = "Blend_tests"
    task1.test_case = "0_ADD_1"
    task1.to_dict.return_value = {"suite": "Blend_tests", "test": "0_ADD_1"}

    task2 = MagicMock()
    task2.suite = "Valid_suite"
    task2.test_case = "Valid_test"
    task2.to_dict.return_value = {"suite": "Valid_suite", "test": "Valid_test"}

    golden_config = GoldenConfig(deprecated_tests={"Blend_tests": ["0_ADD_1"]})
    output_plan = tmp_path / "diff_tasks.json"

    with (
        patch("plan_hw_diffs.identify_missing_hw_diffs", return_value=[task1, task2]),
        patch("plan_hw_diffs.load_golden_config", return_value=golden_config),
        patch(
            "sys.argv",
            [
                "plan_hw_diffs.py",
                "--output-plan-file",
                str(output_plan),
            ],
        ),
    ):
        ret = plan_hw_diffs.main()
        assert ret == 0

    assert output_plan.exists()
    plan_data = json.loads(output_plan.read_text(encoding="utf-8"))
    assert len(plan_data) == 1
    assert plan_data[0]["suite"] == "Valid_suite"
    assert plan_data[0]["test"] == "Valid_test"


def test_plan_xemu_diffs_filters_deprecated_tasks(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from xemu_pgraph_ci_tools.golden_config import GoldenConfig

    scripts_dir = str(Path(__file__).parent.parent / ".github" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import plan_xemu_diffs

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()

    task1 = MagicMock()
    task1.suite = "Blend_tests"
    task1.test_case = "0_ADD_1"
    task1.to_dict.return_value = {"suite": "Blend_tests", "test": "0_ADD_1"}

    task2 = MagicMock()
    task2.suite = "Valid_suite"
    task2.test_case = "Valid_test"
    task2.to_dict.return_value = {"suite": "Valid_suite", "test": "Valid_test"}

    golden_config = GoldenConfig(deprecated_tests={"Blend_tests": ["0_ADD_1"]})
    output_plan = tmp_path / "diff_tasks_xemu.json"

    with (
        patch(
            "plan_xemu_diffs.identify_missing_xemu_diffs",
            return_value=({"reg": "val"}, [task1, task2]),
        ),
        patch("plan_xemu_diffs.load_golden_config", return_value=golden_config),
        patch(
            "sys.argv",
            [
                "plan_xemu_diffs.py",
                "--results-dir",
                str(results_dir),
                "--baseline-dir",
                str(baseline_dir),
                "--output-plan-file",
                str(output_plan),
            ],
        ),
    ):
        ret = plan_xemu_diffs.main()
        assert ret == 0

    assert output_plan.exists()
    plan_data = json.loads(output_plan.read_text(encoding="utf-8"))
    assert len(plan_data["tasks"]) == 1
    assert plan_data["tasks"][0]["suite"] == "Valid_suite"
    assert plan_data["tasks"][0]["test"] == "Valid_test"
