#!/usr/bin/env python3

# ruff: noqa: TRY002 Create your own exception
# ruff: noqa: S202 Uses of `tarfile.extractall()`

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from typing import Any
from urllib.request import urlcleanup, urlretrieve

import requests

logger = logging.getLogger(__name__)


def _filter_release_info_by_tag(release_infos: list[dict[str, Any]], tag: str) -> dict[str, Any] | None:
    for info in release_infos:
        if info.get("tag_name") == tag:
            return info
    return None


def _fetch_github_release_info(api_url: str, tag: str = "latest") -> dict[str, Any] | None:
    full_url = f"{api_url}/releases/latest" if not tag or tag == "latest" else f"{api_url}/releases"

    def fetch_and_filter(url: str):
        try:
            response = requests.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=15,
            )
            response.raise_for_status()
            release_info = response.json()

        except requests.exceptions.RequestException:
            logger.exception("Failed to retrieve information from %s", url)
            return None

        if isinstance(release_info, list):
            release_info = _filter_release_info_by_tag(release_info, tag)
        if release_info:
            return release_info

        if not response.links:
            return None

        next_link = response.links.get("next", {}).get("url")
        if not next_link:
            return None
        next_link = next_link + "&per_page=60"
        return fetch_and_filter(next_link)

    return fetch_and_filter(full_url)


def _download_artifact(target_path: str, download_url: str, artifact_path_override: str | None = None) -> bool:
    """Downloads an artifact from the given URL, if it does not already exist. Returns True if download was needed."""
    if os.path.exists(target_path):
        return False

    if artifact_path_override and os.path.exists(artifact_path_override):
        return True

    if not download_url.startswith("https://"):
        logger.error("Download URL '%s' has unexpected scheme", download_url)
        msg = f"Bad download_url '{download_url} - non HTTPS scheme"
        raise ValueError(msg)

    logger.debug("Downloading %s from %s", target_path, download_url)
    if artifact_path_override:
        target_path = artifact_path_override
        logger.debug(
            "> downloading artifact %s containing %s",
            artifact_path_override,
            target_path,
        )
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    urlretrieve(download_url, target_path)  # noqa: S310 - checked just above
    urlcleanup()

    return True


def fetch_latest_xemu_results(api_url: str, cache_dir: str, output_dir: str) -> None:
    logger.info("Fetching xemu golden results artifact")

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    release_info = _fetch_github_release_info(api_url)
    if not release_info:
        msg = "Failed to fetch info about xemu golden results artifact"
        raise Exception(msg)

    download_url = ""
    for asset in release_info.get("assets", []):
        asset_name = asset.get("name", "")
        if not asset_name:
            continue
        if not asset_name.startswith("xemu") and asset_name.endswith("tgz"):
            continue

        download_url = asset.get("browser_download_url", "")
        break

    if not download_url:
        msg = "Failed to fetch download URL for latest xemu golden results"
        raise Exception(msg)

    target_file = os.path.join(cache_dir, download_url.split("/")[-1])

    if not os.path.isfile(target_file):
        _download_artifact(target_file, download_url)

    with tarfile.open(target_file, "r:gz") as tar:
        already_extracted = True
        for member in tar.getmembers():
            if not os.path.exists(os.path.join(output_dir, member.name)):
                already_extracted = False
                break
        if not already_extracted:
            logger.info("Extracting %s to %s", target_file, output_dir)
            tar.extractall(path=output_dir)


def _find_results_paths(results_dir: str) -> set[str]:
    ret: set[str] = set()

    for root, dirnames, filenames in os.walk(results_dir):
        if not dirnames:
            continue

        if "results.json" not in filenames:
            continue

        ret.add(root)

        # No need to recurse into test suite directories.
        dirnames.clear()

    cwd = os.getcwd()
    return {os.path.relpath(absolute_path, cwd) for absolute_path in ret}


@dataclass
class ResultsConfiguration:
    cpu: str = "any"
    os_version = "any"
    gl_vendor = "any"
    gl_renderer = "any"
    gl_version = "any"
    glsl_version = "any"
    renderer = "OpenGL"
    sanitized_glsl = "any"
    sanitized_gl = "any"
    sanitized_os_arch = "any"

    def __init__(self, results_path: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with open(os.path.join(results_path, "machine_info.txt")) as machine_info:
            for full_line in machine_info:
                line = full_line.strip()
                if line.startswith("CPU:"):
                    self.cpu = line.split(":", 1)[1].strip()
                elif line.startswith("OS_Version:"):
                    self.os_version = line.split(":", 1)[1].strip()
                elif line.startswith("GL_VENDOR:"):
                    self.gl_vendor = line.split(":", 1)[1].strip()
                elif line.startswith("GL_RENDERER:"):
                    self.gl_renderer = line.split(":", 1)[1].strip()
                elif line.startswith("GL_VERSION:"):
                    self.gl_version = line.split(":", 1)[1].strip()
                elif line.startswith("GL_SHADING_LANGUAGE_VERSION:"):
                    self.glsl_version = line.split(":", 1)[1].strip()
                elif line.startswith("- VK_"):
                    self.renderer = "Vulkan"

        path_components = results_path.split(os.path.sep)
        self.sanitized_glsl = path_components[-1]
        self.sanitized_gl = path_components[-2]
        self.sanitized_os_arch = path_components[-3]

    def score(self, other: ResultsConfiguration) -> int:
        def prefix_match(a: str, b: str, value: int, perfect_bonus: int) -> int:
            ret = 0
            for idx in range(min(len(a), len(b))):
                if a[idx] != b[idx]:
                    return ret
                ret += value
            return ret + perfect_bonus

        ret = 0

        # Prefer matching renderer path, even across different OS/GPUs
        if self.renderer == other.renderer:
            ret += 500000

        # Prefer the same OS + architecture, falling back to the same OS
        ret += prefix_match(self.sanitized_os_arch, other.sanitized_os_arch, 100, 100000)

        # Slightly prefer matching GLSL
        ret += prefix_match(self.glsl_version, other.glsl_version, 50, 500)

        # Slightly prefer matching GL
        ret += prefix_match(self.gl_version, other.gl_version, 50, 500)

        return ret


def _find_best_comparator(
    results: ResultsConfiguration, golden_paths: dict[str, ResultsConfiguration]
) -> tuple[str, ResultsConfiguration]:
    """Finds the golden results dir that is the best comparison for the given dir."""

    best_config = None
    best_score = 0

    for item in golden_paths.items():
        if not best_config:
            best_config = item
            best_score = results.score(item[1])
            continue

        score = results.score(item[1])
        if score > best_score:
            best_config = item
            best_score = score

    return best_config


def _build_golden_configurations(golden_dir: str) -> dict[str, ResultsConfiguration]:
    golden_paths = _find_results_paths(golden_dir)
    ret: dict[str, ResultsConfiguration] = {}

    for path in golden_paths:
        ret[path] = ResultsConfiguration(path)

    return ret


def find_result_dirs_without_golden_diffs(
    results_dir: str, golden_dir: str, output_dir: str, *, force: bool = False
) -> list[tuple[str, str]]:
    result_paths = _find_results_paths(results_dir)
    golden_configurations = _build_golden_configurations(golden_dir)

    ret: list[tuple[str, str]] = []

    for path in result_paths:
        path_components = path.split(os.path.sep)
        target_dir = os.path.join(output_dir, *path_components[1:])
        if os.path.isdir(target_dir) and not force:
            continue

        results_config = ResultsConfiguration(path)
        golden_path, golden_configuration = _find_best_comparator(results_config, golden_configurations)

        ret.append((path, golden_path))

    return ret


def generate_diffs(results_dir: str, golden_dir: str, compare_script: str, cache_dir: str, output_dir: str):
    required_comparisons = find_result_dirs_without_golden_diffs(results_dir, golden_dir, output_dir)

    registry = {}
    for result, golden in required_comparisons:
        registry[result] = golden
        subprocess.run(
            [
                compare_script,
                result,
                "--against",
                golden,
                "--output-dir",
                output_dir,
                "--cache-path",
                cache_dir,
                "--verbose",
            ],
            check=False,
        )

    with open(os.path.join(output_dir, "comparisons.json"), "w") as outfile:
        json.dump(registry, outfile, indent=2)

    known_issues_file = os.path.join(golden_dir, "results", "known_issues.json")
    if os.path.isfile(known_issues_file):
        shutil.copy(known_issues_file, os.path.join(output_dir, "known_issues.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory including test outputs that will be processed",
    )
    parser.add_argument(
        "--output-dir",
        default="compare-results",
        help="Directory into which diff results will be generated",
    )
    parser.add_argument(
        "--compare-script",
        default="compare.py",
        help="The compare.py script used to generate results",
    )
    parser.add_argument(
        "--xemu-golden-results-dir",
        default="xemu-golden-results",
        help="Directory into which xemu golden results should be extracted",
    )
    parser.add_argument(
        "--xemu-golden-results-repo-api-url",
        default="https://api.github.com/repos/abaire/xemu-nxdk_pgraph_tests_results",
        help="GitHub API URL for the repo containing xemu golden results",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory into which files that may be useful across runs should be placed",
    )

    args = parser.parse_args()

    compare_script = os.path.abspath(os.path.expanduser(args.compare_script))
    results_dir = os.path.abspath(os.path.expanduser(args.results_dir))
    golden_dir = os.path.abspath(os.path.expanduser(args.xemu_golden_results_dir))
    output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
    cache_dir = os.path.abspath(os.path.expanduser(args.cache_dir))
    fetch_latest_xemu_results(args.xemu_golden_results_repo_api_url, cache_dir, golden_dir)

    generate_diffs(results_dir, golden_dir, compare_script, cache_dir, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
