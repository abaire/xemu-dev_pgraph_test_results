# ruff: noqa: S701, PLR2004, BLE001

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

from jinja2 import Environment, FileSystemLoader, PackageLoader


@dataclass
class DiffLink:
    filename: str
    suite: str
    result_url: str

    machine: str
    gl: str
    glsl: str

    hw_diff_image: str = ""
    hw_diff_url: str = ""
    hw_golden_url: str = ""

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
        suite_issue_text = issue.get("text")
        if suite_issue_text and self._should_apply(issue.get("filter", {})):
            self.known_issues.append(suite_issue_text)

    @staticmethod
    def _match(comparator: str, value: str) -> bool:
        elements = comparator.split("*")
        comparison = r".*".join([re.escape(component) for component in elements])
        return bool(re.match(comparison, value))

    def _matches_platform(self, comparator: str) -> bool:
        return self._match(comparator, self.machine)

    def _matches_gl(self, comparator: str) -> bool:
        return self._match(comparator, self.gl)

    def _matches_glsl(self, comparator: str) -> bool:
        return self._match(comparator, self.glsl)

    def _should_apply(self, filters: dict[str, Any]) -> bool:
        for comparator_key, match_func in {
            "platform": self._matches_platform,
            "gl": self._matches_gl,
            "glsl": self._matches_glsl,
        }.items():
            comparators = filters.get(comparator_key)
            if not comparators:
                continue

            match = False
            for comparator in comparators:
                if match_func(comparator):
                    match = True
                    break
            if not match:
                return False

        return all(
            self._should_apply(subfilter) for subfilter in filters.get("subfilters", [])
        )


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
        top_index_only: bool = False,
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
        self.comparison_registry: dict[str, str] = {}
        self.run_infos: dict[str, dict[str, Any]] = defaultdict(dict)

        self.results: dict[str, DiffLink] = {}
        if not self.top_index_only:
            self._find_results()
            self._find_hw_diffs()
            self._load_comparison_registry()
            self._find_xemu_diffs()

    def _find_results(self):
        for result in glob.glob("**/*.png", root_dir=self.results_dir, recursive=True):
            components = result.split(os.path.sep)
            if len(components) < 2:
                continue
            suite, filename = components[-2:]
            if len(components) >= 5:
                machine, gl, glsl = components[-5:-2]
            else:
                machine, gl, glsl = "Unknown", "OpenGL", "Default"
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
        return (
            f"{self.site_resources_base_url}/{os.path.basename(self.output_dir)}/{path}"
        )

    def _find_hw_diffs(self):
        hw_diff_relative_path = self.hw_golden_comparison.replace(self.output_dir, "")
        for hw_diff in glob.glob(
            "**/*.png", root_dir=self.hw_golden_comparison, recursive=True
        ):
            components = hw_diff.split(os.path.sep)
            if len(components) < 2:
                continue
            suite, filename = components[-2:]
            golden_filename = filename.replace("-diff.png", ".png")
            diff_key = os.path.join(suite, golden_filename)
            if diff_key in self.results:
                diff_link = self.results[diff_key]
                diff_link.hw_diff_image = hw_diff
                diff_link.hw_diff_url = self._make_site_url(
                    f"{hw_diff_relative_path}/{hw_diff}"
                )
                diff_link.hw_golden_url = (
                    f"{self.hw_golden_base_url}/results/{suite}/{golden_filename}"
                )

    def _load_comparison_registry(self):
        comparisons_path = os.path.join(self.xemu_golden_comparison, "comparisons.json")
        if os.path.isfile(comparisons_path):
            with open(comparisons_path) as infile:
                self.comparison_registry = json.load(infile)

        for comparison in self.comparison_registry:
            run_info_file = os.path.join(comparison, "run_info.json")
            if run_info_file in self.run_infos:
                continue
            if os.path.isfile(run_info_file):
                with open(run_info_file) as infile:
                    self.run_infos[run_info_file] = json.load(infile)

    def _find_xemu_diffs(self):
        xemu_diff_relative_path = self.xemu_golden_comparison.replace(
            self.output_dir, ""
        )
        for xemu_diff in glob.glob(
            "**/*.png", root_dir=self.xemu_golden_comparison, recursive=True
        ):
            components = xemu_diff.split(os.path.sep)
            results_key = os.path.join("results", *components[:4])
            xemu_golden_info = self.comparison_registry.get(results_key, "")

            suite, filename = components[-2:]
            golden_filename = filename.replace("-diff.png", ".png")
            diff_key = os.path.join(suite, golden_filename)
            if diff_key in self.results:
                diff_link = self.results[diff_key]
                xemu_subpath = (
                    "/".join(xemu_golden_info.split(os.path.sep)[2:])
                    if xemu_golden_info
                    else ""
                )
                diff_link.xemu_build_info = xemu_subpath
                diff_link.xemu_diff_image = xemu_diff
                diff_link.xemu_diff_url = self._make_site_url(
                    f"{xemu_diff_relative_path}/{xemu_diff}"
                )
                if xemu_subpath:
                    diff_link.xemu_golden_url = f"{self.xemu_golden_base_url}/results/{xemu_subpath}/{suite}/{golden_filename}"
                if not diff_link.hw_golden_url:
                    diff_link.hw_golden_url = (
                        f"{self.hw_golden_base_url}/results/{suite}/{golden_filename}"
                    )

    def _generate_comparison_page(self):
        output_dir = os.path.join(self.output_dir, self.branch.replace("/", "_"))
        known_issues_file = os.path.join(
            self.xemu_golden_comparison, "known_issues.json"
        )
        known_issues_registry = (
            _load_known_issues(known_issues_file)
            if os.path.isfile(known_issues_file)
            else {}
        )

        diffs_by_xemu_version: dict[str, dict[str, list[DiffLink]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for diff in self.results.values():
            if not diff.xemu_diff_url:
                continue
            diff.add_known_issues(known_issues_registry)
            diffs_by_xemu_version[diff.xemu_build_info][diff.suite].append(diff)

        os.makedirs(output_dir, exist_ok=True)
        template_name = (
            "comparison_result.html.j2"
            if diffs_by_xemu_version
            else "no_diffs_result.html.j2"
        )
        template = self.env.get_template(template_name)
        with open(
            os.path.join(output_dir, "index.html"), "w", encoding="utf-8"
        ) as outfile:
            outfile.write(
                template.render(
                    diffs_by_xemu_version=diffs_by_xemu_version,
                    run_information=self.run_infos,
                    branch=self.branch,
                    css_dir=os.path.relpath(self.css_output_dir, output_dir),
                    js_dir=os.path.relpath(self.js_output_dir, output_dir),
                    home_url=self._home_url(output_dir),
                )
            )

    def _generate_index_page(self):
        comparison_pages: dict[str, str] = {}

        for page in glob.glob(
            "**/index.html", root_dir=self.output_dir, recursive=True
        ):
            if page == "index.html":
                continue
            comparison_pages[os.path.dirname(page)] = page

        template = self.env.get_template("index.html.j2")
        output_dir = self.output_dir
        with open(
            os.path.join(output_dir, "index.html"), "w", encoding="utf-8"
        ) as outfile:
            outfile.write(
                template.render(
                    comparison_pages=comparison_pages,
                    css_dir=os.path.relpath(self.css_output_dir, output_dir),
                    js_dir=os.path.relpath(self.js_output_dir, output_dir),
                )
            )

    def _write_js(self):
        js_template = self.env.get_template("script.js.j2")
        os.makedirs(self.js_output_dir, exist_ok=True)
        with open(
            os.path.join(self.js_output_dir, "script.js"), "w", encoding="utf-8"
        ) as outfile:
            outfile.write(js_template.render())

    def _write_css(self):
        css_template = self.env.get_template("site.css.j2")
        os.makedirs(self.css_output_dir, exist_ok=True)
        with open(
            os.path.join(self.css_output_dir, "site.css"), "w", encoding="utf-8"
        ) as outfile:
            outfile.write(
                css_template.render(
                    comparison_golden_outline_size=6,
                    title_bar_height=40,
                )
            )

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
            return {
                sanitize_name(key): sanitize_value(val) for key, val in value.items()
            }
        return value

    return {
        sanitize_name(key): sanitize_value(value) for key, value in known_issues.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("hw_comparison_results")
    parser.add_argument("xemu_comparison_results")
    parser.add_argument("results_branch")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output-dir", default="site")
    parser.add_argument("--site-resources-base-url", default=".")
    parser.add_argument("--results-base-url", default=".")
    parser.add_argument(
        "--xemu-golden-base-url",
        default="https://raw.githubusercontent.com/abaire/xemu-nxdk_pgraph_tests_results/github_pages",
    )
    parser.add_argument(
        "--hw-golden-base-url",
        default="https://raw.githubusercontent.com/abaire/nxdk_pgraph_tests_golden_results/main",
    )
    parser.add_argument("--templates-dir", help="Directory containing templates")
    parser.add_argument("--top-index-only", action="store_true")

    args = parser.parse_args()

    output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
    hw_golden_comparison = os.path.abspath(
        os.path.expanduser(args.hw_comparison_results)
    )
    xemu_golden_comparison = os.path.abspath(
        os.path.expanduser(args.xemu_comparison_results)
    )

    if not hw_golden_comparison.startswith(output_dir):
        msg = f"Hardware golden comparison dir '{hw_golden_comparison}' must be a subdirectory within '{output_dir}'"
        raise ValueError(msg)

    if not xemu_golden_comparison.startswith(output_dir):
        msg = f"xemu golden comparison dir '{xemu_golden_comparison}' must be a subdirectory within '{output_dir}'"
        raise ValueError(msg)

    results_base_url = (
        f"{args.results_base_url}/{args.results_branch}"
        if args.results_base_url != "."
        and not args.results_base_url.endswith(args.results_branch)
        else args.results_base_url
    )

    if args.templates_dir:
        jinja_env = Environment(loader=FileSystemLoader(args.templates_dir))
    else:
        try:
            jinja_env = Environment(
                loader=PackageLoader("xemu_dev_pgraph", "templates")
            )
        except Exception:
            fallback = os.path.join(os.path.dirname(__file__), "templates")
            jinja_env = Environment(loader=FileSystemLoader(fallback))

    jinja_env.globals["sidenav_width"] = 48
    jinja_env.globals["sidenav_icon_width"] = 32

    generator = Generator(
        results_dir=args.results_dir,
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
