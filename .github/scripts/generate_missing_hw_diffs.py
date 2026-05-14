#!/usr/bin/env python3

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)


def _find_results_paths(results_dir: str) -> set[str]:
    ret: set[str] = set()

    logger.info("Searching for result directories in '%s'", results_dir)
    if not os.path.isdir(results_dir):
        logger.warning("Results directory '%s' does not exist", results_dir)
        return ret

    for root, dirnames, filenames in os.walk(results_dir):
        if not dirnames:
            continue

        if "results.json" not in filenames:
            continue

        logger.info("  Found result directory: %s", root)
        ret.add(root)

        # No need to recurse into test suite directories.
        dirnames.clear()

    logger.info("Found %d result directory(ies)", len(ret))
    return ret


def _find_hw_comparison_paths(output_dir: str) -> set[str]:
    ret: set[str] = set()

    logger.info("Searching for existing HW comparisons in '%s'", output_dir)
    if not os.path.isdir(output_dir):
        logger.info("  Output directory '%s' does not exist (no prior comparisons)", output_dir)
        return ret

    for root, dirnames, filenames in os.walk(output_dir):
        if not dirnames:
            continue

        if "summary.json" not in filenames:
            continue

        if os.path.basename(root) != "Xbox__Xbox__DirectX__nv2a":
            continue
        logger.info("  Found existing comparison: %s", root)
        ret.add(root)

        # No need to recurse into test suite directories.
        dirnames.clear()

    logger.info("Found %d existing comparison(s)", len(ret))
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

    if source_paths:
        logger.info("Mapped %d existing comparison(s) back to source paths:", len(source_paths))
        for sp in sorted(source_paths):
            logger.info("  %s", sp)

    missing = result_paths - source_paths
    logger.info("%d result directory(ies) still need HW comparisons", len(missing))
    for m in sorted(missing):
        logger.info("  %s", m)

    return missing


def _discover_test_suites(result_dir: str) -> list[str]:
    """Return sorted list of test suite subdirectory names within a result directory."""
    try:
        suites = [entry.name for entry in os.scandir(result_dir) if entry.is_dir() and not entry.name.startswith(".")]
    except OSError:
        logger.warning("Could not scan result directory: %s", result_dir)
        suites = []
    return sorted(suites)


def generate_missing_hw_diffs(
    results_dir: str,
    output_dir: str,
    compare_script: str,
    shard_index: int | None = None,
    shard_count: int | None = None,
) -> None:
    results_missing_comparisons = find_result_dirs_without_hw_diffs(results_dir, output_dir)

    if not results_missing_comparisons:
        logger.warning("No result directories need HW comparisons. Nothing to do.")
        return

    # Build a flattened list of (result_dir, suite_name) pairs so sharding
    # distributes individual test suites across runners, not just the few
    # top-level result directories.
    flat_items: list[tuple[str, str]] = []
    for result_dir in sorted(results_missing_comparisons):
        suites = _discover_test_suites(result_dir)
        logger.info("Found %d test suite(s) in %s", len(suites), result_dir)
        flat_items.extend((result_dir, suite) for suite in suites)

    logger.info("Total (result_dir, suite) pairs to process (before sharding): %d", len(flat_items))

    if not flat_items:
        logger.warning("No test suites found. Nothing to do.")
        return

    if shard_index is not None and shard_count is not None:
        logger.info("Sharding: index=%d, count=%d", shard_index, shard_count)
        flat_items = [item for i, item in enumerate(flat_items) if i % shard_count == shard_index]
        logger.info("This shard will process %d pair(s)", len(flat_items))
        if not flat_items:
            logger.warning("Shard %d has no work to process.", shard_index)
            return

    # Group the assigned suites back by result directory so we make one
    # compare.py invocation per result directory (with a suite filter).
    suites_by_result_dir: dict[str, list[str]] = {}
    for result_dir, suite in flat_items:
        suites_by_result_dir.setdefault(result_dir, []).append(suite)

    for result_dir, suites in sorted(suites_by_result_dir.items()):
        sorted_suites = sorted(suites)
        logger.info("Running comparison for %s with %d suite(s): %s", result_dir, len(suites), ", ".join(sorted_suites))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n".join(sorted_suites))
            suites_file = f.name

        try:
            subprocess.run(
                [
                    compare_script,
                    result_dir,
                    "--output-dir",
                    output_dir,
                    "--verbose",
                    "--include-suites-file",
                    suites_file,
                ],
                check=False,
            )
        finally:
            os.unlink(suites_file)


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
        "--shard-index",
        type=int,
        default=None,
        help="Index of this shard (0-based). Must be used with --shard-count.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=None,
        help="Total number of shards. Must be used with --shard-index.",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if (args.shard_index is None) != (args.shard_count is None):
        parser.error("--shard-index and --shard-count must be used together")

    compare_script = os.path.abspath(os.path.expanduser(args.compare_script))
    logger.info("results-dir: %s", args.results_dir)
    logger.info("output-dir: %s", args.output_dir)
    logger.info("compare-script: %s", compare_script)
    generate_missing_hw_diffs(
        args.results_dir, args.output_dir, compare_script, shard_index=args.shard_index, shard_count=args.shard_count
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
