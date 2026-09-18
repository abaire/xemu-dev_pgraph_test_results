from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass

# Load fetch_xemu_pr_artifact dynamically from .github/scripts
script_path = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "scripts"
    / "fetch_xemu_pr_artifact.py"
)
spec = importlib.util.spec_from_file_location("fetch_xemu_pr_artifact", script_path)
assert spec
assert spec.loader
fetch_pr_module = importlib.util.module_from_spec(spec)
sys.modules["fetch_xemu_pr_artifact"] = fetch_pr_module
spec.loader.exec_module(fetch_pr_module)

parse_pr_number = fetch_pr_module.parse_pr_number
sanitize_branch_name = fetch_pr_module.sanitize_branch_name
fetch_pr_details = fetch_pr_module.fetch_pr_details
find_ci_run = fetch_pr_module.find_ci_run
find_artifact = fetch_pr_module.find_artifact
download_and_extract_artifact = fetch_pr_module.download_and_extract_artifact


def test_parse_pr_number() -> None:
    assert parse_pr_number("3056") == 3056
    assert parse_pr_number(" #3056 ") == 3056
    assert parse_pr_number("https://github.com/xemu-project/xemu/pull/3056") == 3056
    assert (
        parse_pr_number("https://github.com/xemu-project/xemu/pull/3056/commits")
        == 3056
    )

    with pytest.raises(ValueError, match="Could not parse valid pull request number"):
        parse_pr_number("not-a-number")


def test_sanitize_branch_name() -> None:
    assert sanitize_branch_name("feat/alpha/test:1") == "feat-alpha-test-1"
    assert sanitize_branch_name("normal_branch") == "normal_branch"
    assert sanitize_branch_name("branch with spaces") == "branch-with-spaces"


def test_fetch_pr_details_success() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "head": {"sha": "abcdef12345", "ref": "feature-branch"},
        "title": "My Feature",
        "html_url": "https://github.com/xemu-project/xemu/pull/123",
    }

    with patch("requests.get", return_value=fake_response):
        data = fetch_pr_details(123, token="dummy_token")
        assert data["head"]["sha"] == "abcdef12345"
        assert data["head"]["ref"] == "feature-branch"


def test_fetch_pr_details_not_found() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 404

    with patch("requests.get", return_value=fake_response):
        with pytest.raises(ValueError, match="Pull request #999 was not found"):
            fetch_pr_details(999)


def test_find_ci_run_prefers_ci() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "workflow_runs": [
            {"id": 1, "name": "Lint", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "CI", "status": "completed", "conclusion": "success"},
        ]
    }

    with patch("requests.get", return_value=fake_response):
        run = find_ci_run("abcdef")
        assert run["id"] == 2
        assert run["name"] == "CI"


def test_find_ci_run_in_progress() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "workflow_runs": [
            {"id": 1, "name": "CI", "status": "in_progress", "conclusion": None},
        ]
    }

    with patch("requests.get", return_value=fake_response):
        with pytest.raises(RuntimeError, match="is currently in progress"):
            find_ci_run("abcdef")


def test_find_artifact_success() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "artifacts": [
            {"id": 101, "name": "other-artifact", "expired": False},
            {"id": 102, "name": "xemu-ubuntu-x86_64-release", "expired": False},
        ]
    }

    with patch("requests.get", return_value=fake_response):
        art = find_artifact(1, "xemu-ubuntu-x86_64-release")
        assert art["id"] == 102


def test_find_artifact_expired() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "artifacts": [
            {"id": 102, "name": "xemu-ubuntu-x86_64-release", "expired": True},
        ]
    }

    with patch("requests.get", return_value=fake_response):
        with pytest.raises(RuntimeError, match="has expired"):
            find_artifact(1, "xemu-ubuntu-x86_64-release")


def test_find_artifact_not_found() -> None:
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"artifacts": []}

    with patch("requests.get", return_value=fake_response):
        with pytest.raises(RuntimeError, match="not found in run 1"):
            find_artifact(1, "xemu-ubuntu-x86_64-release")


def test_download_and_extract_artifact(tmp_path: Path) -> None:
    # Create an in-memory zip containing a mock AppImage
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("dist/xemu-x86_64.AppImage", b"dummy-executable-content")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = zip_buffer.getvalue()

    output_dir = tmp_path / "assets"

    with patch("requests.get", return_value=fake_response):
        binary_path = download_and_extract_artifact(102, output_dir)
        assert binary_path == output_dir / "xemu"
        assert binary_path.exists()
        assert binary_path.read_bytes() == b"dummy-executable-content"
        # Verify temp folder was cleaned up
        assert not (output_dir / "_temp_extract").exists()


def test_main_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "assets"
    github_output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output_file))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("xemu.AppImage", b"binary")

    pr_resp = MagicMock(
        status_code=200,
        json=lambda: {
            "head": {"sha": "1234567890abcdef", "ref": "feat/my-branch"},
            "title": "Add Awesome Feature",
            "html_url": "https://github.com/xemu-project/xemu/pull/3000",
        },
    )
    runs_resp = MagicMock(
        status_code=200,
        json=lambda: {
            "workflow_runs": [
                {
                    "id": 42,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "run_url",
                }
            ]
        },
    )
    artifacts_resp = MagicMock(
        status_code=200,
        json=lambda: {
            "artifacts": [
                {
                    "id": 99,
                    "name": "xemu-ubuntu-x86_64-release",
                    "expired": False,
                    "size_in_bytes": 100,
                }
            ]
        },
    )
    download_resp = MagicMock(status_code=200, content=zip_buffer.getvalue())

    def mock_get(url: str, *args: object, **kwargs: object) -> MagicMock:
        if "/pulls/" in url:
            return pr_resp
        if "/actions/runs/" in url and "/artifacts" in url:
            return artifacts_resp
        if "/actions/runs" in url:
            return runs_resp
        if "/actions/artifacts/" in url:
            return download_resp
        raise AssertionError(f"Unexpected url {url}")

    with patch("requests.get", side_effect=mock_get):
        with patch.object(
            sys,
            "argv",
            [
                "fetch_xemu_pr_artifact.py",
                "--pr",
                "3000",
                "--output-dir",
                str(output_dir),
                "--token",
                "tok",
            ],
        ):
            code = fetch_pr_module.main()
            assert code == 0

    assert (output_dir / "xemu").exists()
    meta_file = output_dir / "run_meta.json"
    assert meta_file.exists()
    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta_data["xemu_pr"] == 3000
    assert meta_data["head_branch"] == "feat/my-branch"
    assert meta_data["default_branch_name"] == "results/pr-3000-feat-my-branch"

    output_lines = github_output_file.read_text(encoding="utf-8").splitlines()
    assert "pr_number=3000" in output_lines
    assert "default_branch=results/pr-3000-feat-my-branch" in output_lines
