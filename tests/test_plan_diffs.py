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
    baseline_run = baseline_dir / "xemu-0.8.134" / "Darwin_arm64" / "gl_Apple" / "gslv_4.10"
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
