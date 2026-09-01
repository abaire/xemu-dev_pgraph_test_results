from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Load generate_results_site dynamically from .github/scripts
script_path = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "generate_results_site.py"
spec = importlib.util.spec_from_file_location("generate_results_site", script_path)
assert spec
assert spec.loader
generate_results_site = importlib.util.module_from_spec(spec)
sys.modules["generate_results_site"] = generate_results_site
spec.loader.exec_module(generate_results_site)

DiffLink = generate_results_site.DiffLink


def test_diff_link_properties() -> None:
    link = DiffLink(
        filename="test_case_1.png",
        suite="Alpha_tests",
        result_url="https://example.com/source.png",
        machine="Darwin_arm64",
        gl="Apple M3 Max",
        glsl="4.10",
    )
    assert link.test_name == "test_case_1"
    assert link.sort_key == "Alpha_tests/test_case_1.png"
    assert not link.has_diff

    link.hw_diff_image = "diff.png"
    assert link.has_diff


def test_known_issues_filtering() -> None:
    link = DiffLink(
        filename="test_case_1.png",
        suite="Alpha_tests",
        result_url="https://example.com/source.png",
        machine="Darwin_arm64",
        gl="Apple M3 Max",
        glsl="4.10",
    )

    registry = {
        "Alpha_tests": {
            "issues": [
                {
                    "text": "Known issue on Apple Silicon",
                    "filter": {
                        "platform": ["Darwin*"],
                    },
                },
                {
                    "text": "Known issue on Linux",
                    "filter": {
                        "platform": ["Linux*"],
                    },
                },
            ],
            "test_case_1": {
                "issues": [
                    {
                        "text": "Specific test issue",
                        "filter": {
                            "glsl": ["4.*"],
                        },
                    }
                ]
            },
        }
    }

    link.add_known_issues(registry)
    assert "Known issue on Apple Silicon" in link.known_issues
    assert "Known issue on Linux" not in link.known_issues
    assert "Specific test issue" in link.known_issues


def test_generate_site_empty(tmp_path: Path) -> None:
    output_dir = tmp_path / "site"
    hw_dir = output_dir / "my_branch" / "compare_hw"
    xemu_dir = output_dir / "my_branch" / "compare_xemu"
    hw_dir.mkdir(parents=True)
    xemu_dir.mkdir(parents=True)

    templates_dir = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "site-templates"

    jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))
    jinja_env.globals["sidenav_width"] = 48
    jinja_env.globals["sidenav_icon_width"] = 32

    generator = generate_results_site.Generator(
        results_dir=str(tmp_path / "results"),
        hw_golden_comparison=str(hw_dir),
        xemu_golden_comparison=str(xemu_dir),
        branch="my_branch",
        results_base_url="https://example.com/results",
        site_resources_base_url="https://example.com/site",
        hw_golden_base_url="https://example.com/hw",
        xemu_golden_base_url="https://example.com/xemu",
        output_dir=str(output_dir),
        jinja_env=jinja_env,
        top_index_only=False,
    )

    result = generator.generate_site()
    assert result == 0
    assert (output_dir / "index.html").exists()
    assert (output_dir / "my_branch" / "index.html").exists()
    assert (output_dir / "site.css").exists()
    assert (output_dir / "script.js").exists()
