# ruff: noqa: S701, BLE001

from __future__ import annotations

import argparse
import logging
import os
import sys

from jinja2 import Environment, FileSystemLoader, PackageLoader

from xemu_dev_pgraph.hw_diffs import generate_missing_hw_diffs
from xemu_dev_pgraph.site_generator import Generator
from xemu_dev_pgraph.xemu_diffs import generate_diffs as generate_xemu_diffs

logger = logging.getLogger(__name__)


def run_pipeline(
    results_dir: str,
    golden_dir: str,
    xemu_baseline_dir: str | None,
    output_dir: str,
    *,
    branch: str = "main",
    perceptualdiff: str = "perceptualdiff",
    site_resources_base_url: str = ".",
    results_base_url: str = ".",
    hw_golden_base_url: str = "https://raw.githubusercontent.com/abaire/nxdk_pgraph_tests_golden_results/main",
    xemu_golden_base_url: str = "https://raw.githubusercontent.com/abaire/xemu-nxdk_pgraph_tests_results/github_pages",
) -> int:
    results_dir = os.path.abspath(os.path.expanduser(results_dir))
    output_dir = os.path.abspath(os.path.expanduser(output_dir))
    golden_dir = os.path.abspath(os.path.expanduser(golden_dir))
    if xemu_baseline_dir:
        xemu_baseline_dir = os.path.abspath(os.path.expanduser(xemu_baseline_dir))

    hw_comparison_dir = os.path.join(output_dir, "compare_hw")
    xemu_comparison_dir = os.path.join(output_dir, "compare_xemu")
    os.makedirs(hw_comparison_dir, exist_ok=True)
    os.makedirs(xemu_comparison_dir, exist_ok=True)

    # 1. Generate Hardware Diffs
    logger.info("Generating hardware golden diffs...")
    generate_missing_hw_diffs(
        results_dir=results_dir,
        output_dir=hw_comparison_dir,
        compare_script=sys.executable + " -m xemu_dev_pgraph.comparator",
        perceptualdiff=perceptualdiff,
    )

    # 2. Generate Xemu Baseline Diffs
    if xemu_baseline_dir and os.path.isdir(xemu_baseline_dir):
        logger.info("Generating xemu baseline diffs against %s...", xemu_baseline_dir)
        generate_xemu_diffs(
            results_dir=results_dir,
            golden_dir=xemu_baseline_dir,
            compare_script=sys.executable + " -m xemu_dev_pgraph.comparator",
            cache_dir=os.path.join(output_dir, "cache"),
            output_dir=xemu_comparison_dir,
            perceptualdiff=perceptualdiff,
        )
    else:
        logger.warning(
            "No valid xemu baseline directory provided; creating dummy comparisons.json"
        )
        with open(os.path.join(xemu_comparison_dir, "comparisons.json"), "w") as f:
            f.write("{}")

    # 3. Generate Static Preview Site
    logger.info("Rendering preview website into %s...", output_dir)
    try:
        jinja_env = Environment(loader=PackageLoader("xemu_dev_pgraph", "templates"))
    except Exception:
        fallback_dir = os.path.join(os.path.dirname(__file__), "templates")
        jinja_env = Environment(loader=FileSystemLoader(fallback_dir))

    jinja_env.globals["sidenav_width"] = 48
    jinja_env.globals["sidenav_icon_width"] = 32

    generator = Generator(
        results_dir=results_dir,
        hw_golden_comparison=hw_comparison_dir,
        xemu_golden_comparison=xemu_comparison_dir,
        branch=branch,
        results_base_url=results_base_url,
        site_resources_base_url=site_resources_base_url,
        hw_golden_base_url=hw_golden_base_url,
        xemu_golden_base_url=xemu_golden_base_url,
        output_dir=output_dir,
        jinja_env=jinja_env,
        top_index_only=False,
    )
    return generator.generate_site()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate PGraph regression visual diff report & HTML site."
    )
    parser.add_argument(
        "--results-dir",
        "-r",
        default="results",
        help="Directory containing actual test results.",
    )
    parser.add_argument(
        "--golden-dir",
        "-g",
        required=True,
        help="Directory containing Xbox hardware golden baseline.",
    )
    parser.add_argument(
        "--xemu-baseline-dir",
        "-x",
        help="Directory containing baseline xemu release results.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="site_preview",
        help="Output directory for generated preview site.",
    )
    parser.add_argument(
        "--branch", default="pr-preview", help="Branch or PR identifier."
    )
    parser.add_argument(
        "--perceptualdiff",
        default="perceptualdiff",
        help="Path to perceptualdiff binary.",
    )
    parser.add_argument(
        "--site-resources-base-url", default=".", help="Base URL for site resources."
    )
    parser.add_argument(
        "--results-base-url", default=".", help="Base URL for test results."
    )
    parser.add_argument(
        "--hw-golden-base-url",
        default="https://raw.githubusercontent.com/abaire/nxdk_pgraph_tests_golden_results/main",
        help="Base URL for HW golden images.",
    )
    parser.add_argument(
        "--xemu-golden-base-url",
        default="https://raw.githubusercontent.com/abaire/xemu-nxdk_pgraph_tests_results/github_pages",
        help="Base URL for xemu baseline images.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging."
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    return run_pipeline(
        results_dir=args.results_dir,
        golden_dir=args.golden_dir,
        xemu_baseline_dir=args.xemu_baseline_dir,
        output_dir=args.output_dir,
        branch=args.branch,
        perceptualdiff=args.perceptualdiff,
        site_resources_base_url=args.site_resources_base_url,
        results_base_url=args.results_base_url,
        hw_golden_base_url=args.hw_golden_base_url,
        xemu_golden_base_url=args.xemu_golden_base_url,
    )


if __name__ == "__main__":
    sys.exit(main())
