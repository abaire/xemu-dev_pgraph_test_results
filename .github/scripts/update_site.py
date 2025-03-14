#!/usr/bin/env python3

# ruff: noqa: S701 By default, jinja2 sets `autoescape` to `False`. Consider using `autoescape=True` or the `select_autoescape` function to mitigate XSS vulnerabilities.

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, FileSystemLoader


@dataclass
class DiffLink:
    # Info about the test artifact.
    filename: str
    suite: str
    result_url: str

    # Info about the machine used to generate the test results.
    machine: str
    gl: str
    glsl: str

    # The related Xbox test artifact.
    hw_diff_image: str = ""
    hw_diff_url: str = ""
    hw_golden_url: str = ""

    # The related xemu release test artifact.
    xemu_build_info: str = ""
    xemu_diff_image: str = ""
    xemu_diff_url: str = ""
    xemu_golden_url: str = ""

    known_issues: list[str] = dataclasses.field(default_factory=list)

    @property
    def sort_key(self) -> str:
        return f"{self.suite}/{self.filename}"

    @property
    def has_diff(self) -> bool:
        return bool(self.hw_diff_image or self.xemu_diff_image)

    @property
    def test_name(self) -> str:
        return self.filename[:-4]

    def add_known_issues(self, registry: dict[str, Any]):
        known_issues = registry.get(self.suite)
        if not known_issues:
            return

        for issue in known_issues.get("issues", []):
            self._process_known_issue(issue)

        test_issues = known_issues.get(self.test_name)
        if test_issues:
            for issue in test_issues.get("issues", []):
                self._process_known_issue(issue)

    def _process_known_issue(self, issue: dict[str, Any]):
        # Check for a suite-level issue
        suite_issue_text = issue.get("text")
        if suite_issue_text and self._should_apply(issue.get("filter", {})):
            self.known_issues.append(suite_issue_text)

    @staticmethod
    def _match(comparator: str, value: str) -> bool:
        elements = comparator.split("*")
        comparison = r".*".join([re.escape(component) for component in elements])

        match = re.match(comparison, value)
        return bool(match)

    def _matches_platform(self, comparator: str) -> bool:
        return self._match(comparator, self.machine)

    def _matches_gl(self, comparator: str) -> bool:
        return self._match(comparator, self.gl)

    def _matches_glsl(self, comparator: str) -> bool:
        return self._match(comparator, self.glsl)

    def _should_apply(self, filter: dict[str, Any]) -> bool:
        for comparator_key, match_func in {"platform": self._matches_platform, "gl": self._matches_gl, "glsl": self._matches_glsl}.items():
            comparators = filter.get(comparator_key)
            if not comparators:
                continue

            match = False
            for comparator in comparators:
                if match_func(comparator):
                    match = True
                    break
            if not match:
                return False

        for subfilter in filter.get("subfilters", []):
            if not self._should_apply(subfilter):
                return False

        return True

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
        top_index_only: bool,
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
        self.top_index_only = top_index_only

        self.results: dict[str, DiffLink] = {}
        if not self.top_index_only:
            self._find_results()
            self._find_hw_diffs()
            self._find_xemu_diffs()

    def _find_results(self):
        for result in glob.glob("**/*.png", root_dir=self.results_dir, recursive=True):
            components = result.split(os.path.sep)
            suite, filename = components[-2:]
            machine, gl, glsl = components[-5:-2]
            diff_key = os.path.join(suite, filename)
            self.results[diff_key] = DiffLink(
                filename=filename,
                suite=suite,
                machine=machine,
                gl=gl,
                glsl=glsl,
                result_url=f"{self.results_base_url}/results/{result}",
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

            # If the results are identical to HW, there will be no golden. Since the Pages page has the room, populate
            # the Golden image anyway.
            if not diff_link.hw_golden_url:
                diff_link.hw_golden_url = f"{self.hw_golden_base_url}/results/{suite}/{golden_filename}"

    def _generate_comparison_page(self):
        output_dir = os.path.join(self.output_dir, self.branch.replace("/", "_"))

        # There are generally many diffs against hardware and for PR purposes it's more important to diff against the
        # status quo.
        # diffs_vs_hw = {diff.sort_key: diff for diff in self.results.values() if diff.hw_diff_url}

        known_issues_file = os.path.join(self.xemu_golden_comparison, "known_issues.json")
        if os.path.isfile(known_issues_file):
            known_issues_registry = _load_known_issues(known_issues_file)
        else:
            known_issues_registry = {}

        diffs_by_xemu_version: dict[str, dict[str, list[DiffLink]]] = defaultdict(lambda: defaultdict(list))
        for diff in self.results.values():
            if not diff.xemu_diff_url:
                continue
            diff.add_known_issues(known_issues_registry)
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
        if not self.top_index_only:
            self._generate_comparison_page()
        self._generate_index_page()
        return 0


def _load_known_issues(known_issues_file: str) -> dict[str, Any]:
    with open(known_issues_file) as infile:
        content = json.load(infile)
        known_issues = content.get("known_issues", {})

    def sanitize_name(name: str) -> str:
        return name.replace(" ", "_")

    def sanitize_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {sanitize_name(key): sanitize_value(val) for key, val in value.items()}
        return value

    return {sanitize_name(key): sanitize_value(value) for key, value in known_issues.items()}


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
        default="https://raw.githubusercontent.com/abaire/xemu-dev_pgraph_test_results/pages-branch",
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
    parser.add_argument(
        "--top-index-only",
        action="store_true",
        help="Only regenerate the top level index.html file, do not scan for images.",
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
        top_index_only=args.top_index_only,
    )
    return generator.generate_site()


if __name__ == "__main__":
    sys.exit(main())
