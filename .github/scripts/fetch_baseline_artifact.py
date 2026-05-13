# ruff: noqa: S607 Starting a process with a partial executable path

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

# Configure logging for CI visibility
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def git(*args):
    return subprocess.check_output(["git", *list(args)]).decode().strip()


def parse_version(text):
    """Extracts (major, minor, patch) as a tuple of ints."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0)


def get_local_context():
    """Returns (target_version_tuple, env_signature, renderer_type, local_version_str)."""
    results_path = Path("results")
    machine_infos = list(results_path.glob("**/machine_info.txt"))
    if not machine_infos:
        msg = "Could not find dev results machine_info.txt"
        raise FileNotFoundError(msg)

    path = machine_infos[0].resolve()
    parts = path.parts
    idx = parts.index("results")

    local_version_str = parts[idx + 1]
    target_version = parse_version(local_version_str)
    env_sig = os.path.join(*parts[idx + 2 : -1])

    renderer = "OpenGL"
    with path.open() as f:
        if "- VK_" in f.read():
            renderer = "Vulkan"

    return target_version, env_sig, renderer, local_version_str


def score_candidate(candidate_path, target_version, target_env_sig, target_renderer):
    """Priority: Version (<= Target) > Exact Env > OS > Renderer."""
    path_parts = candidate_path.parts
    # Path: results/<xemu-id>/<os>/<gpu>/<glsl>
    version_str = path_parts[1]
    cand_version = parse_version(version_str)

    if cand_version > target_version:
        return -1

    score = 0
    # Weighted scoring for numeric version and hardware affinity
    score += (cand_version[0] * 1000000) + (cand_version[1] * 1000) + cand_version[2]

    path_str = str(candidate_path)
    if target_env_sig in path_str:
        score += 5000000

    target_os = target_env_sig.split(os.sep)[0]
    if path_parts[2] == target_os:
        score += 1000000

    m_info = Path("manifest-repo") / candidate_path / "machine_info.txt"
    if m_info.exists():
        with m_info.open() as f:
            content = f.read()
            if (target_renderer == "Vulkan") == ("- VK_" in content):
                score += 500000

    return score


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "abaire")
    repo = "xemu-nxdk_pgraph_tests_results"
    repo_url = (
        f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        if token
        else f"https://github.com/{owner}/{repo}.git"
    )

    try:
        target_ver, env_sig, renderer, local_ver_str = get_local_context()
        logger.info("Local Context: %s | %s | %s", local_ver_str, env_sig, renderer)

        # 1. Fetch manifest from main
        logger.info("Fetching manifest from %s/%s@main...", owner, repo)
        subprocess.check_call(["git", "clone", "--depth", "1", "--branch", "main", repo_url, "manifest-repo"])

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
            sys.exit(1)

        scored.sort(key=lambda x: x[0], reverse=True)
        best_match_path = scored[0][1]

        # 3. Resolve archive branch and clone
        version_id = best_match_path.parts[1]
        archive_branch = f"archive/{version_id}"
        logger.info("Best Match: %s", best_match_path)
        logger.info("Targeting Branch: %s", archive_branch)

        subprocess.check_call(["git", "clone", "--depth", "1", "--branch", archive_branch, repo_url, "baseline-repo"])

        # The archive branches contain the 'results' folder at the root
        final_baseline_dir = (Path("baseline-repo") / best_match_path).resolve()

        if not final_baseline_dir.is_dir():
            logger.error("Resolved baseline directory %s does not exist.", final_baseline_dir)
            sys.exit(1)

        logger.info("FINAL_SELECTION=%s", final_baseline_dir)

        if "GITHUB_ENV" in os.environ:
            with open(os.environ["GITHUB_ENV"], "a") as f:
                f.write(f"XEMU_BASELINE_DIR={final_baseline_dir}\n")

    except Exception:
        logger.exception("An unexpected error occurred during baseline retrieval.")
        sys.exit(1)
