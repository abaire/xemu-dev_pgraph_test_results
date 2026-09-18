#!/usr/bin/env python3
"""Fetches the Linux release build artifact for a given xemu PR from xemu-project/xemu."""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_OWNER = "xemu-project"
REPO_NAME = "xemu"
DEFAULT_ARTIFACT_NAME = "xemu-ubuntu-x86_64-release"


def parse_pr_number(pr_input: str) -> int:
    """Extracts PR number from an integer string, #1234, or full GitHub PR URL."""
    pr_input = pr_input.strip()
    match = re.search(r"(?:pull/|^#?)(\d+)", pr_input)
    if not match:
        msg = f"Could not parse valid pull request number from '{pr_input}'"
        raise ValueError(msg)
    return int(match.group(1))


def get_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "xemu-dev_pgraph-ci",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_pr_details(pr_number: int, token: str | None = None) -> dict[str, Any]:
    """Retrieves pull request metadata from GitHub API."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}"
    response = requests.get(url, headers=get_headers(token), timeout=30)
    if response.status_code == 404:
        msg = f"Pull request #{pr_number} was not found in {REPO_OWNER}/{REPO_NAME}."
        raise ValueError(msg)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data


def find_ci_run(head_sha: str, token: str | None = None) -> dict[str, Any]:
    """Finds the completed CI workflow run associated with head_sha."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs"
    params = {"head_sha": head_sha}
    response = requests.get(url, headers=get_headers(token), params=params, timeout=30)
    response.raise_for_status()
    runs = response.json().get("workflow_runs", [])

    if not runs:
        msg = f"No GitHub Actions workflow runs found for commit {head_sha} on {REPO_OWNER}/{REPO_NAME}."
        raise RuntimeError(msg)

    # Look for completed successful CI runs
    successful_runs = [
        run
        for run in runs
        if run.get("status") == "completed" and run.get("conclusion") == "success"
    ]

    if not successful_runs:
        in_progress = [
            run for run in runs if run.get("status") in ("in_progress", "queued")
        ]
        if in_progress:
            msg = f"CI run for commit {head_sha} is currently in progress (status: {in_progress[0].get('status')})."
        else:
            conclusions = ", ".join(
                r.get("conclusion") or r.get("status") for r in runs
            )
            msg = f"No successful CI run found for commit {head_sha}. Run statuses: {conclusions}."
        raise RuntimeError(msg)

    # Prefer run named "CI" if present
    for run in successful_runs:
        if run.get("name") == "CI":
            return run  # type: ignore[no-any-return]

    return successful_runs[0]  # type: ignore[no-any-return]


def find_artifact(
    run_id: int, artifact_name: str, token: str | None = None
) -> dict[str, Any]:
    """Locates target build artifact in the workflow run."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/artifacts"
    response = requests.get(url, headers=get_headers(token), timeout=30)
    response.raise_for_status()
    artifacts = response.json().get("artifacts", [])

    for artifact in artifacts:
        if artifact.get("name") == artifact_name:
            if artifact.get("expired"):
                msg = f"Artifact '{artifact_name}' in run {run_id} has expired."
                raise RuntimeError(msg)
            return artifact  # type: ignore[no-any-return]

    available = [a.get("name", "") for a in artifacts]
    msg = f"Artifact '{artifact_name}' not found in run {run_id}. Available artifacts: {available}"
    raise RuntimeError(msg)


def download_and_extract_artifact(
    artifact_id: int,
    output_dir: Path,
    token: str | None = None,
) -> Path:
    """Downloads artifact zip and extracts xemu AppImage to output_dir/xemu."""
    download_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/artifacts/{artifact_id}/zip"
    logger.info("Downloading artifact from %s ...", download_url)

    # Note: requests follows redirects and strips the Authorization header on cross-host redirects (e.g. to AWS S3),
    # which is expected since AWS presigned URLs fail if an invalid Authorization header is present.
    response = requests.get(
        download_url, headers=get_headers(token), timeout=120, stream=True
    )
    response.raise_for_status()

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_extract_dir = output_dir / "_temp_extract"
    temp_extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        zf.extractall(temp_extract_dir)

    # Locate xemu binary or AppImage
    appimage_candidates = list(temp_extract_dir.glob("**/*xemu*.AppImage"))
    if not appimage_candidates:
        # Fallback search for any executable file named xemu
        appimage_candidates = [
            p for p in temp_extract_dir.glob("**/xemu") if p.is_file()
        ]

    if not appimage_candidates:
        msg = "Could not find xemu AppImage or executable in downloaded artifact zip."
        raise RuntimeError(msg)

    source_binary = appimage_candidates[0]
    target_binary = output_dir / "xemu"
    if target_binary.exists():
        target_binary.unlink()
    source_binary.rename(target_binary)
    target_binary.chmod(0o755)

    # Clean up temp extract folder
    for root, dirs, files in os.walk(temp_extract_dir, topdown=False):
        for file in files:
            (Path(root) / file).unlink(missing_ok=True)
        for d in dirs:
            (Path(root) / d).rmdir()
    temp_extract_dir.rmdir()

    logger.info("Successfully installed xemu binary at %s", target_binary)
    return target_binary


def sanitize_branch_name(name: str) -> str:
    """Replaces slashes and invalid branch characters with dashes."""
    return re.sub(r"[/\\:\s]+", "-", name).strip("-")


def export_github_output(outputs: dict[str, str]) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as f:
        for k, v in outputs.items():
            f.write(f"{k}={v}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download xemu PR build artifact")
    parser.add_argument(
        "--pr",
        required=True,
        help="xemu PR number or URL (e.g. 3056 or https://github.com/xemu-project/xemu/pull/3056)",
    )
    parser.add_argument(
        "--output-dir",
        default="assets",
        help="Directory to save the downloaded xemu executable into (default: assets)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub Personal Access Token / API token (defaults to GH_TOKEN or GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--artifact-name",
        default=DEFAULT_ARTIFACT_NAME,
        help=f"Target artifact name (default: {DEFAULT_ARTIFACT_NAME})",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    output_dir = Path(args.output_dir).resolve()

    try:
        pr_number = parse_pr_number(args.pr)
        logger.info("Fetching details for PR #%d ...", pr_number)
        pr_data = fetch_pr_details(pr_number, token)

        head_sha = pr_data["head"]["sha"]
        head_ref = pr_data["head"]["ref"]
        title = pr_data.get("title", "")
        pr_url = pr_data.get(
            "html_url", f"https://github.com/{REPO_OWNER}/{REPO_NAME}/pull/{pr_number}"
        )

        logger.info(
            "PR #%d: '%s' (Branch: %s, Commit: %s)",
            pr_number,
            title,
            head_ref,
            head_sha,
        )

        logger.info("Finding CI run for commit %s ...", head_sha)
        ci_run = find_ci_run(head_sha, token)
        run_id = ci_run["id"]
        logger.info("Found CI run %d: %s", run_id, ci_run.get("html_url"))

        logger.info("Locating artifact '%s' ...", args.artifact_name)
        artifact = find_artifact(run_id, args.artifact_name, token)
        artifact_id = artifact["id"]
        logger.info(
            "Found artifact %d (%s bytes)", artifact_id, artifact.get("size_in_bytes")
        )

        xemu_binary = download_and_extract_artifact(artifact_id, output_dir, token)

        safe_ref = sanitize_branch_name(head_ref)
        default_branch = f"results/pr-{pr_number}-{safe_ref}"

        meta = {
            "xemu_pr": pr_number,
            "pr_title": title,
            "pr_url": pr_url,
            "head_branch": head_ref,
            "head_sha": head_sha,
            "default_branch_name": default_branch,
            "binary_path": str(xemu_binary),
        }
        meta_path = output_dir / "run_meta.json"
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        export_github_output(
            {
                "pr_number": str(pr_number),
                "pr_title": title,
                "head_branch": head_ref,
                "head_sha": head_sha,
                "pr_url": pr_url,
                "default_branch": default_branch,
            }
        )

        logger.info("Successfully prepared test assets metadata at %s", meta_path)
        return 0

    except Exception as exc:
        logger.error("Failed to fetch xemu PR artifact: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
