#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed


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

    return ret


def _find_hw_comparison_paths(output_dir: str) -> set[str]:
    ret: set[str] = set()

    for root, dirnames, filenames in os.walk(output_dir):
        if not dirnames:
            continue

        if "summary.json" not in filenames:
            continue

        if os.path.basename(root) != "Xbox__Xbox__DirectX__nv2a":
            continue
        ret.add(root)

        # No need to recurse into test suite directories.
        dirnames.clear()

    return ret


def _comparison_path_to_source_path(comparison_path: str) -> str:
    components = comparison_path.split("/")

    xemu = components[-4]
    platform = components[-3]
    graphics_pair = components[-2]

    return os.path.join(xemu, platform, *graphics_pair.split(":"))


def find_result_dirs_without_hw_diffs(results_dir: str, output_dir: str) -> set[str]:
    result_paths = _find_results_paths(results_dir)

    hw_comparison_paths = _find_hw_comparison_paths(output_dir)
    source_paths = {os.path.join(results_dir, _comparison_path_to_source_path(path)) for path in hw_comparison_paths}

    return result_paths - source_paths


def perform_comparison(result: str, output_dir: str, compare_script: str) -> tuple[str, bool, str, str]:
    process = subprocess.run(
        [compare_script, result, "--output-dir", output_dir, "--verbose"], capture_output=True, text=True, check=False
    )
    if process.returncode == 0:
        return result, True, process.stdout, process.stderr
    return result, False, process.stdout, process.stderr


def generate_missing_hw_diffs(
    results_dir: str, output_dir: str, compare_script: str, max_workers: int | None = None
) -> None:
    results_missing_comparisons = find_result_dirs_without_hw_diffs(results_dir, output_dir)

    if not results_missing_comparisons:
        return

    successful_comparisons = 0
    failed_comparisons = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(perform_comparison, result, output_dir, compare_script): result
            for result in results_missing_comparisons
        }

        for future in as_completed(futures):
            result_path, success, stdout, stderr = future.result()
            if success:
                successful_comparisons += 1
            else:
                failed_comparisons += 1

    for result in results_missing_comparisons:
        subprocess.run([compare_script, result, "--output-dir", output_dir, "--verbose"], check=False)


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

    args = parser.parse_args()

    compare_script = os.path.abspath(os.path.expanduser(args.compare_script))
    generate_missing_hw_diffs(args.results_dir, args.output_dir, compare_script)

    return 0


if __name__ == "__main__":
    sys.exit(main())
