#!/usr/bin/env python3

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass


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


class Generator:
    def __init__(
        self,
        *,
        page_title: str | None,
        branch: str,
        results_dir: str,
        hw_golden_comparison: str,
        xemu_golden_comparison: str,
        results_base_url: str,
        wiki_base_url: str,
        hw_golden_base_url: str,
        xemu_golden_base_url: str,
        output_dir: str,
    ):
        self.page_title = page_title or branch
        self.results_dir = results_dir
        self.hw_golden_comparison = hw_golden_comparison
        self.xemu_golden_comparison = xemu_golden_comparison
        self.results_base_url = results_base_url
        self.wiki_base_url = wiki_base_url
        self.hw_golden_base_url = hw_golden_base_url
        self.xemu_golden_base_url = xemu_golden_base_url
        self.output_dir = output_dir

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

    def _find_hw_diffs(self):
        hw_diff_relative_path = self.hw_golden_comparison.replace(self.output_dir, "")
        for hw_diff in glob.glob("**/*.png", root_dir=self.hw_golden_comparison, recursive=True):
            suite, filename = hw_diff.split(os.path.sep)[-2:]
            golden_filename = filename.replace("-diff.png", ".png")
            diff_link = self.results[os.path.join(suite, golden_filename)]

            diff_link.hw_diff_image = hw_diff
            diff_link.hw_diff_url = f"{hw_diff_relative_path}/{hw_diff}"
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
            diff_link.xemu_diff_url = f"{xemu_diff_relative_path}/{xemu_diff}"

            diff_link.xemu_golden_url = f"{self.xemu_golden_base_url}/results/{xemu_subpath}/{suite}/{golden_filename}"

    def generate_markdown(self) -> int:
        page_filename = os.path.join(self.output_dir, f"{self.page_title}.md".replace("/", "_"))

        # There are generally many diffs against hardware and for PR purposes it's more important to diff against the
        # status quo.
        # diffs_vs_hw = {diff.sort_key: diff for diff in self.results.values() if diff.hw_diff_url}

        diffs_by_xemu_version: dict[str, list[DiffLink]] = defaultdict(list)
        for diff in self.results.values():
            if not diff.xemu_diff_url:
                continue
            diffs_by_xemu_version[diff.xemu_build_info].append(diff)

        with open(page_filename, "w") as outfile:
            outfile.writelines(
                [
                    f"{self.page_title}\n",
                    "===\n",
                ]
            )

            for xemu_version in sorted(diffs_by_xemu_version):
                outfile.write(f"# {xemu_version}\n")

                results_by_suite = defaultdict(list)
                for result in diffs_by_xemu_version[xemu_version]:
                    results_by_suite[result.suite].append(result)

                for suite in sorted(results_by_suite):
                    outfile.write(f"## {suite}\n")

                    for diff in sorted(results_by_suite[suite], key=lambda x: x.filename):
                        diff: DiffLink
                        test_name = diff.filename[:-4]
                        outfile.writelines(
                            [
                                f"### {test_name}\n",
                                "#### PR\n",
                                f"![{diff.result_url}]({diff.result_url})\n",
                                f"#### {xemu_version}\n",
                                f"![{diff.xemu_golden_url}]({diff.xemu_golden_url})\n",
                                f"### PR vs {xemu_version}\n",
                                f"[[{diff.xemu_diff_url}|{diff.xemu_diff_url}]]\n",
                            ]
                        )

                        if diff.hw_golden_url:
                            outfile.writelines(
                                [
                                    "#### HW\n",
                                    f"![{diff.hw_golden_url}]({diff.hw_golden_url})\n",
                                    "#### PR vs HW\n",
                                    f"[[{diff.hw_diff_url}|{diff.hw_diff_url}]]\n",
                                ]
                            )
                        else:
                            outfile.write("#### HW\nPR matches hardware\n")

                        outfile.write("\n")

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
        default="wiki",
        help="Directory into which markdown will be generated",
    )
    parser.add_argument("--page-title", help="Sets the title of the generated markdown page")
    parser.add_argument(
        "--wiki-base-url",
        default="https://github.com/abaire/xemu-dev_pgraph_test_results.wiki/raw/main",
        help="Base URL at which the contents of the wiki may be publicly accessed",
    )
    parser.add_argument(
        "--results-base-url",
        default="https://raw.githubusercontent.com/abaire/xemu-dev_pgraph_test_results/refs/heads",
        help="Base URL at which the contents of the xemu golden results repository may be publicly accessed",
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

    page_title = args.page_title

    results_base_url = f"{args.results_base_url}/{args.results_branch}"

    generator = Generator(
        page_title=page_title,
        results_dir=results_dir,
        hw_golden_comparison=hw_golden_comparison,
        xemu_golden_comparison=xemu_golden_comparison,
        branch=args.results_branch,
        results_base_url=results_base_url,
        wiki_base_url=args.wiki_base_url,
        hw_golden_base_url=args.hw_golden_base_url,
        xemu_golden_base_url=args.xemu_golden_base_url,
        output_dir=output_dir,
    )
    return generator.generate_markdown()


if __name__ == "__main__":
    sys.exit(main())
