from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

# Load fetch_baseline_artifact dynamically from .github/scripts
script_path = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "fetch_baseline_artifact.py"
spec = importlib.util.spec_from_file_location("fetch_baseline_artifact", script_path)
assert spec
assert spec.loader
fetch_baseline = importlib.util.module_from_spec(spec)
sys.modules["fetch_baseline_artifact"] = fetch_baseline
spec.loader.exec_module(fetch_baseline)

parse_version = fetch_baseline.parse_version
score_candidate = fetch_baseline.score_candidate
get_local_context = fetch_baseline.get_local_context


def test_parse_version() -> None:
    assert parse_version("xemu-0.8.135-master-12345") == (0, 8, 135)
    assert parse_version("0.8.35") == (0, 8, 35)
    assert parse_version("invalid") == (0, 0, 0)


def test_score_candidate() -> None:
    cand_path = Path("results/xemu-0.8.134-master/Darwin_arm64/gl_Apple/gslv_4.10")
    target_ver = (0, 8, 135)
    target_env = "Darwin_arm64/gl_Apple/gslv_4.10"
    target_renderer = "OpenGL"

    score = score_candidate(cand_path, target_ver, target_env, target_renderer)
    assert score > 0

    # Newer candidate than target should be rejected (-1)
    cand_newer = Path("results/xemu-0.8.136-master/Darwin_arm64/gl_Apple/gslv_4.10")
    assert score_candidate(cand_newer, target_ver, target_env, target_renderer) == -1


def test_get_local_context_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Set cwd to tmp_path where results/ is empty or missing
    monkeypatch.chdir(tmp_path)
    assert get_local_context() is None
    assert fetch_baseline.main() == 0
