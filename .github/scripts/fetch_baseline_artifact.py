# ruff: noqa: S607 Starting a process with a partial executable path

import os
import subprocess
import sys
from pathlib import Path


def git(*args):
    return subprocess.check_output(["git", *list(args)]).decode().strip()


def get_latest_archive_branch(repo_url):
    # Get all heads, filter for archive/, sort by version-like names descending
    cmd = ["git", "ls-remote", "--heads", repo_url, "refs/heads/archive/*"]
    output = subprocess.check_output(cmd).decode()
    branches = []
    for line in output.splitlines():
        ref = line.split()[1]
        branches.append(ref.replace("refs/heads/", ""))

    # Simple sort for now; latest usually has highest version number
    return sorted(branches)[-1]


def find_local_env_path():
    # results/xemu-DEV-ID/OS_ARCH/GPU_INFO/GLSL_INFO/machine_info.txt
    results_path = Path("results")
    machine_infos = list(results_path.glob("**/machine_info.txt"))
    if not machine_infos:
        msg = "Could not find dev results machine_info.txt"
        raise FileNotFoundError(msg)

    # We want the relative path from the xemu-<version> level
    # e.g., Darwin_arm64/gl_Apple_Apple_M5_Max/gslv_4.10
    full_path = machine_infos[0].parent
    parts = full_path.parts
    # Find where 'results' is, skip 'results' and the 'xemu-version' dir
    idx = parts.index("results")
    return os.path.join(*parts[idx + 2 :])


if __name__ == "__main__":
    REPO_URL = "https://github.com/xemu-project/xemu-nxdk_pgraph_tests_results.git"

    env_sig = find_local_env_path()
    print(f"Detected environment signature: {env_sig}")

    latest_branch = get_latest_archive_branch(REPO_URL)
    print(f"Targeting baseline branch: {latest_branch}")

    # Shallow clone the specific archive branch
    subprocess.check_call(["git", "clone", "--depth", "1", "--branch", latest_branch, REPO_URL, "baseline-repo"])

    # Locate the matching directory in the baseline
    # baseline-repo/results/xemu-RELEASE-ID/OS_ARCH/GPU_INFO/...
    baseline_results_root = Path("baseline-repo/results")
    matches = list(baseline_results_root.glob(f"**/{env_sig}"))

    if not matches:
        print(f"No exact match for {env_sig} in baseline. Checking for closest OS match...")
        os_arch = env_sig.split(os.sep)[0]
        matches = list(baseline_results_root.glob(f"**/{os_arch}*"))
        if not matches:
            sys.exit("Could not find any suitable baseline for this OS.")

    baseline_path = matches[0]
    print(f"SELECTED_BASELINE={baseline_path}")

    # Set environment variables for the next step in the GHA
    with open(os.environ["GITHUB_ENV"], "a") as f:
        f.write(f"XEMU_BASELINE_DIR={baseline_path}\n")
