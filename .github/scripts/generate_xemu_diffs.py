#!/usr/bin/env python3


from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    os_version: str = "any"
    gl_vendor: str = "any"
    gl_renderer: str = "any"
    gl_version: str = "any"
    glsl_version: str = "any"
    renderer: str = "OpenGL"
    sanitized_glsl: str = "any"
    sanitized_gl: str = "any"
    sanitized_os_arch: str = "any"

    def __init__(self, results_path: str):
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

        # Directory structure: results/<version_id>/<os_arch>/<gpu>/<glsl>
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

        # Prefer matching renderer path
        if self.renderer == other.renderer:
            ret += 500000

        # Prefer the same OS + architecture, falling back to the same OS
        ret += prefix_match(self.sanitized_os_arch, other.sanitized_os_arch, 100, 100000)

        # Match GLSL and GL versions
        ret += prefix_match(self.glsl_version, other.glsl_version, 50, 500)
        ret += prefix_match(self.gl_version, other.gl_version, 50, 500)

        return ret


def _find_best_comparator(
    results: ResultsConfiguration, golden_paths: dict[str, ResultsConfiguration]
) -> tuple[str, ResultsConfiguration]:
    best_config = None
    best_score = -1

    for path, config in golden_paths.items():
        score = results.score(config)
        if score > best_score:
            best_config = (path, config)
            best_score = score

    return best_config


def _build_configurations(base_dir: str) -> dict[str, ResultsConfiguration]:
    paths = _find_results_paths(base_dir)
    return {path: ResultsConfiguration(path) for path in paths}


def generate_diffs(results_dir: str, golden_dir: str, compare_script: str, cache_dir: str, output_dir: str):
    result_paths = _find_results_paths(results_dir)
    golden_configurations = _build_configurations(golden_dir)

    if not golden_configurations:
        msg = f"No baseline results found in {golden_dir}"
        raise ValueError(msg)

    registry = {}
    for path in result_paths:
        results_config = ResultsConfiguration(path)
        golden_path, _ = _find_best_comparator(results_config, golden_configurations)

        registry[path] = golden_path

        subprocess.run(
            [
                compare_script,
                path,
                "--against",
                golden_path,
                "--output-dir",
                output_dir,
                "--cache-path",
                cache_dir,
                "--verbose",
            ],
            check=False,
        )

    # Save comparison map
    with open(os.path.join(output_dir, "comparisons.json"), "w") as outfile:
        json.dump(registry, outfile, indent=2)

    # Copy global known issues from baseline
    known_issues_file = os.path.join(golden_dir, "results", "known_issues.json")
    if os.path.isfile(known_issues_file):
        shutil.copy(known_issues_file, os.path.join(output_dir, "known_issues.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output-dir", default="compare-results")
    parser.add_argument("--compare-script", default="compare.py")
    parser.add_argument("--baseline-dir", required=True, help="Path to the cloned archive branch")
    parser.add_argument("--cache-dir", default="cache")

    args = parser.parse_args()

    # Absolute paths for reliability
    compare_script = os.path.abspath(os.path.expanduser(args.compare_script))
    results_dir = os.path.abspath(os.path.expanduser(args.results_dir))
    golden_dir = os.path.abspath(os.path.expanduser(args.baseline_dir))
    output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
    cache_dir = os.path.abspath(os.path.expanduser(args.cache_dir))

    if not os.path.isdir(golden_dir):
        logger.error("Baseline directory %s not found.", golden_dir)
        return 1

    generate_diffs(results_dir, golden_dir, compare_script, cache_dir, output_dir)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
