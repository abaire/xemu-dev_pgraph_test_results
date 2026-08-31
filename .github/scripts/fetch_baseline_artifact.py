#!/usr/bin/env python3
# ruff: noqa: S607 Starting a process with a partial executable path

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from xemu_pgraph_ci_tools.models import RunIdentifier

# Configure logging for CI visibility
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *list(args)]).decode().strip()


def parse_version(text: str) -> tuple[int, int, int]:
    """Extracts (major, minor, patch) as a tuple of ints."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if match:
        return tuple(map(int, match.groups()))  # type: ignore[return-value]
    return (0, 0, 0)


def get_local_context() -> tuple[tuple[int, int, int], str, str, str] | None:
    """Returns (target_version_tuple, env_signature, renderer_type, local_version_str) or None."""
    results_path = Path("results")
    if not results_path.is_dir():
        logger.info("No 'results' directory found.")
        return None

    machine_infos = list(results_path.glob("**/machine_info.txt"))
    if not machine_infos:
        logger.info("Could not find dev results machine_info.txt in '%s'.", results_path)
        return None

    path = machine_infos[0].resolve()
    parts = path.parts
    idx = parts.index("results")

    if len(parts) <= idx + 1:
        logger.warning("Path %s does not contain xemu version component.", path)
        return None

    local_version_str = parts[idx + 1]
    target_version = parse_version(local_version_str)
    env_sig = os.path.join(*parts[idx + 2 : -1]) if len(parts) > idx + 2 else ""

    renderer = "OpenGL"
    with path.open(encoding="utf-8", errors="replace") as f:
        if "- VK_" in f.read():
            renderer = "Vulkan"

    return target_version, env_sig, renderer, local_version_str


def score_candidate(
    candidate_path: Path,
    target_version: tuple[int, int, int],
    target_env_sig: str,
    target_renderer: str,
) -> int:
    """Priority: Version (<= Target) > Exact Env > OS > Renderer."""
    run_id = RunIdentifier.parse(str(candidate_path))
    cand_version = parse_version(run_id.xemu_version)

    if cand_version > target_version:
        return -1

    score = 0
    # Weighted scoring for numeric version and hardware affinity
    score += (cand_version[0] * 1000000) + (cand_version[1] * 1000) + cand_version[2]

    path_str = str(candidate_path)
    if target_env_sig in path_str:
        score += 5000000

    target_os = target_env_sig.split(os.sep)[0]
    if run_id.platform_info == target_os:
        score += 1000000

    m_info = Path("manifest-repo") / candidate_path / "machine_info.txt"
    if m_info.exists():
        with m_info.open(encoding="utf-8", errors="replace") as f:
            content = f.read()
            if (target_renderer == "Vulkan") == ("- VK_" in content):
                score += 500000

    return score


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "abaire")
    repo = "xemu-nxdk_pgraph_tests_results"
    repo_url = (
        f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        if token
        else f"https://github.com/{owner}/{repo}.git"
    )

    try:
        context = get_local_context()
        if context is None:
            logger.info("No local test results found. Skipping baseline fetch.")
            return 0

        target_ver, env_sig, renderer, local_ver_str = context
        logger.info("Local Context: %s | %s | %s", local_ver_str, env_sig, renderer)

        # 1. Fetch manifest from main
        logger.info("Fetching manifest from %s/%s@main...", owner, repo)
        subprocess.check_call(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "main",
                repo_url,
                "manifest-repo",
            ]
        )

        # 2. Score candidates
        manifest_root = Path("manifest-repo/results")
        candidates = [p.parent for p in manifest_root.glob("**/machine_info.txt")]

        scored = []
        for cp in candidates:
            rel_path = cp.relative_to("manifest-repo")
            score = score_candidate(rel_path, target_ver, env_sig, renderer)
            if score >= 0:
                scored.append((score, rel_path))

        if not scored:
            logger.error("No suitable baseline found in manifest.")
            return 1

        scored.sort(key=lambda x: x[0], reverse=True)
        best_match_path = scored[0][1]

        # 3. Resolve archive branch and clone
        run_id = RunIdentifier.parse(str(best_match_path))
        version_id = run_id.xemu_version
        archive_branch = f"archive/{version_id}"
        logger.info("Best Match: %s", best_match_path)
        logger.info("Targeting Branch: %s", archive_branch)

        subprocess.check_call(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                archive_branch,
                repo_url,
                "baseline-repo",
            ]
        )

        # The archive branches contain the 'results' folder at the root
        final_baseline_dir = (Path("baseline-repo") / best_match_path).resolve()

        if not final_baseline_dir.is_dir():
            logger.error("Resolved baseline directory %s does not exist.", final_baseline_dir)
            return 1

        logger.info("FINAL_SELECTION=%s", final_baseline_dir)

        if "GITHUB_ENV" in os.environ:
            with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as f:
                f.write(f"XEMU_BASELINE_DIR={final_baseline_dir}\n")

    except Exception:
        logger.exception("An unexpected error occurred during baseline retrieval.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
