#!/usr/bin/env python3

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader


@dataclass
class DiffLink:
    filename: str
    suite: str
    result_url: str

    hw_diff_image: str = ""
    hw_diff_url: str = ""
    hw_golden_url: str = ""

    xemu_build_info: str = ""
    xemu_diff_image: str = ""
    xemu_diff_url: str = ""
    xemu_golden_url: str = ""

    @property
    def sort_key(self) -> str:
        return f"{self.suite}/{self.filename}"

    @property
    def has_diff(self) -> bool:
        return bool(self.hw_diff_image or self.xemu_diff_image)

    @property
    def test_name(self) -> str:
        return self.filename[:-4]


class Generator:
    def __init__(
        self,
        *,
        branch: str,
        results_dir: str,
        hw_golden_comparison: str,
        xemu_golden_comparison: str,
        results_base_url: str,
        site_resources_base_url: str,
        hw_golden_base_url: str,
        xemu_golden_base_url: str,
        output_dir: str,
        jinja_env: Environment,
    ):
        self.branch = branch
        self.results_dir = results_dir
        self.hw_golden_comparison = hw_golden_comparison
        self.xemu_golden_comparison = xemu_golden_comparison
        self.results_base_url = results_base_url
        self.site_resources_base_url = site_resources_base_url
        self.hw_golden_base_url = hw_golden_base_url
        self.xemu_golden_base_url = xemu_golden_base_url
        self.output_dir = output_dir.rstrip("/")
        self.css_output_dir = output_dir.rstrip("/")
        self.js_output_dir = output_dir.rstrip("/")
        self.env = jinja_env

        self.results: dict[str, DiffLink] = {}
        self._find_results()
        self._find_hw_diffs()
        self._find_xemu_diffs()

    def _find_results(self):
        for result in glob.glob("**/*.png", root_dir=self.results_dir, recursive=True):
            suite, filename = result.split(os.path.sep)[-2:]
            diff_key = os.path.join(suite, filename)
            self.results[diff_key] = DiffLink(
                filename=filename, suite=suite, result_url=f"{self.results_base_url}/results/{result}"
            )

    def _home_url(self, output_dir: str) -> str:
        return f"{os.path.relpath(self.output_dir, output_dir)}/index.html"

    def _make_site_url(self, path: str) -> str:
        return f"{self.site_resources_base_url}/{os.path.basename(self.output_dir)}/{path}"

    def _find_hw_diffs(self):

        hw_diff_relative_path = self.hw_golden_comparison.replace(self.output_dir, "")
        for hw_diff in glob.glob("**/*.png", root_dir=self.hw_golden_comparison, recursive=True):
            suite, filename = hw_diff.split(os.path.sep)[-2:]
            golden_filename = filename.replace("-diff.png", ".png")
            diff_link = self.results[os.path.join(suite, golden_filename)]

            diff_link.hw_diff_image = hw_diff
            diff_link.hw_diff_url = self._make_site_url(f"{hw_diff_relative_path}/{hw_diff}")
            diff_link.hw_golden_url = f"{self.hw_golden_base_url}/results/{suite}/{golden_filename}"

    def _find_xemu_diffs(self):

        xemu_diff_relative_path = self.xemu_golden_comparison.replace(self.output_dir, "")

        with open(os.path.join(self.xemu_golden_comparison, "comparisons.json")) as infile:
            comparison_registry = json.load(infile)

        for xemu_diff in glob.glob("**/*.png", root_dir=self.xemu_golden_comparison, recursive=True):
            components = xemu_diff.split(os.path.sep)
            # The first 4 components of the path will be xemu_version/os_arch/gl_info/glsl_info
            results_key = os.path.join("results", *components[:4])

            xemu_golden_info = comparison_registry.get(results_key)
            if not xemu_golden_info:
                msg = f"Failed to lookup comparison database for xemu diff '{xemu_diff}' from {comparison_registry}"
                raise ValueError(msg)
            suite, filename = components[-2:]
            golden_filename = filename.replace("-diff.png", ".png")
            diff_link = self.results[os.path.join(suite, golden_filename)]

            xemu_subpath = "/".join(xemu_golden_info.split(os.path.sep)[2:])
            diff_link.xemu_build_info = xemu_subpath
            diff_link.xemu_diff_image = xemu_diff
            diff_link.xemu_diff_url = self._make_site_url(f"{xemu_diff_relative_path}/{xemu_diff}")

            diff_link.xemu_golden_url = f"{self.xemu_golden_base_url}/results/{xemu_subpath}/{suite}/{golden_filename}"

    def _generate_comparison_page(self):
        output_dir = os.path.join(self.output_dir, self.branch.replace("/", "_"))

        # There are generally many diffs against hardware and for PR purposes it's more important to diff against the
        # status quo.
        # diffs_vs_hw = {diff.sort_key: diff for diff in self.results.values() if diff.hw_diff_url}

        diffs_by_xemu_version: dict[str, dict[str, list[DiffLink]]] = defaultdict(lambda: defaultdict(list))
        for diff in self.results.values():
            if not diff.xemu_diff_url:
                continue
            diffs_by_xemu_version[diff.xemu_build_info][diff.suite].append(diff)

        with open(os.path.join(output_dir, "index.html"), "w") as outfile:
            comparison_template = self.env.get_template("comparison_result.html.j2")
            outfile.write(
                comparison_template.render(
                    diffs_by_xemu_version=diffs_by_xemu_version,
                    branch=self.branch,
                    css_dir=os.path.relpath(self.css_output_dir, output_dir),
                    js_dir=os.path.relpath(self.js_output_dir, output_dir),
                    home_url=self._home_url(output_dir),
                )
            )

    def _generate_index_page(self):
        comparison_pages: dict[str, str] = {}

        for page in glob.glob("**/index.html", root_dir=self.output_dir, recursive=True):
            if page == "index.html":
                continue
            comparison_pages[os.path.dirname(page)] = page

        index_template = self.env.get_template("index.html.j2")
        output_dir = self.output_dir

        with open(os.path.join(output_dir, "index.html"), "w") as outfile:
            outfile.write(
                index_template.render(
                    comparison_pages=comparison_pages,
                    css_dir=os.path.relpath(self.css_output_dir, output_dir),
                    js_dir=os.path.relpath(self.js_output_dir, output_dir),
                )
            )

    def _write_css(self) -> None:
        css_template = self.env.get_template("site.css.j2")
        with open(os.path.join(self.css_output_dir, "site.css"), "w") as outfile:
            outfile.write(
                css_template.render(
                    comparison_golden_outline_size=6,
                    title_bar_height=40,
                )
            )

    def _write_js(self) -> None:
        css_template = self.env.get_template("script.js.j2")
        with open(os.path.join(self.js_output_dir, "script.js"), "w") as outfile:
            outfile.write(css_template.render())

    def generate_site(self) -> int:
        self._write_css()
        self._write_js()
        self._generate_comparison_page()
        self._generate_index_page()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "hw_comparison_results",
        help="Directory containing the comparison between the results and Xbox hardware goldens",
    )
    parser.add_argument(
        "xemu_comparison_results",
        help="Directory containing the comparison between the results and xemu goldens",
    )
    parser.add_argument("results_branch", help="Name of the branch containing the results")
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory including test outputs that will be processed",
    )
    parser.add_argument(
        "--output-dir",
        default="site",
        help="Directory into which website files will be generated",
    )
    parser.add_argument(
        "--site-resources-base-url",
        default="https://raw.githubusercontent.com/abaire/xemu-dev_pgraph_test_results/site",
        help="Base URL at which the site branch output may be publicly accessed",
    )
    parser.add_argument(
        "--results-base-url",
        default="https://raw.githubusercontent.com/abaire/xemu-dev_pgraph_test_results/refs/heads",
        help="Base URL at which the contents of the development build results repository may be publicly accessed",
    )
    parser.add_argument(
        "--xemu-golden-base-url",
        default="https://raw.githubusercontent.com/abaire/xemu-nxdk_pgraph_tests_results/main",
        help="Base URL at which the contents of the xemu golden results repository may be publicly accessed",
    )
    parser.add_argument(
        "--hw-golden-base-url",
        default="https://raw.githubusercontent.com/abaire/nxdk_pgraph_tests_golden_results/main",
        help="Base URL at which the contents of the golden images from Xbox hardware may be publicly accessed.",
    )
    parser.add_argument(
        "--templates-dir",
        help="Directory containing the templates used to render the site.",
    )

    args = parser.parse_args()

    results_dir = args.results_dir
    output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
    hw_golden_comparison = os.path.abspath(os.path.expanduser(args.hw_comparison_results))
    xemu_golden_comparison = os.path.abspath(os.path.expanduser(args.xemu_comparison_results))

    if not hw_golden_comparison.startswith(output_dir):
        msg = f"Hardware golden comparison dir '{hw_golden_comparison}' must be a subdirectory within '{output_dir}'"
        raise ValueError(msg)

    if not xemu_golden_comparison.startswith(output_dir):
        msg = f"xemu golden comparison dir '{xemu_golden_comparison}' must be a subdirectory within '{output_dir}'"
        raise ValueError(msg)

    results_base_url = f"{args.results_base_url}/{args.results_branch}"

    if not args.templates_dir:
        args.templates_dir = os.path.join(os.path.dirname(__file__), "site-templates")

    jinja_env = Environment(loader=FileSystemLoader(args.templates_dir))
    jinja_env.globals["sidenav_width"] = 48
    jinja_env.globals["sidenav_icon_width"] = 32

    generator = Generator(
        results_dir=results_dir,
        hw_golden_comparison=hw_golden_comparison,
        xemu_golden_comparison=xemu_golden_comparison,
        branch=args.results_branch,
        results_base_url=results_base_url,
        site_resources_base_url=args.site_resources_base_url,
        hw_golden_base_url=args.hw_golden_base_url,
        xemu_golden_base_url=args.xemu_golden_base_url,
        output_dir=output_dir,
        jinja_env=jinja_env,
    )
    return generator.generate_site()


if __name__ == "__main__":
    sys.exit(main())
