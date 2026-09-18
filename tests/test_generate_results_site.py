from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Load generate_results_site dynamically from .github/scripts
script_path = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "scripts"
    / "generate_results_site.py"
)
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

    templates_dir = (
        Path(__file__).resolve().parent.parent
        / ".github"
        / "scripts"
        / "site-templates"
    )

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


def test_compute_xemu_subpath() -> None:
    # 1. Colon-delimited identifier (e.g. from summary.json)
    colon_id = "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee:Linux_x86_64:gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits):gslv_4.50"
    expected = "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    assert generate_results_site.Generator._compute_xemu_subpath(colon_id) == expected

    # 2. Path-based identifier (e.g. from comparisons.json)
    path_id = "xemu-baseline/results/xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    assert generate_results_site.Generator._compute_xemu_subpath(path_id) == expected

    # 3. Empty or none
    assert generate_results_site.Generator._compute_xemu_subpath("") == ""


def test_generate_site_populates_xemu_golden_from_summary_json(tmp_path: Path) -> None:
    output_dir = tmp_path / "site"
    branch = "results_pr-3056"
    hw_dir = output_dir / branch / "compare_hw"
    xemu_dir = output_dir / branch / "compare_xemu"
    hw_dir.mkdir(parents=True)
    xemu_dir.mkdir(parents=True)

    results_dir = tmp_path / "results"
    run_rel = (
        "xemu-0.8.136-51-g3aee4c1682-3aee4c16820a8ca84548e979d4a062aba28abc21"
        "/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    )
    test_img_dir = results_dir / run_rel / "Blend_surface"
    test_img_dir.mkdir(parents=True)
    (test_img_dir / "R5G6B5_Add_SrcA_1-SrcA.png").write_bytes(b"PNG_DATA")

    golden_dir_name = (
        "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee__Linux_x86_64"
        "__gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)__gslv_4.50"
    )
    diff_comp_dir = xemu_dir / run_rel / golden_dir_name
    diff_img_dir = diff_comp_dir / "Blend_surface"
    diff_img_dir.mkdir(parents=True)
    (diff_img_dir / "R5G6B5_Add_SrcA_1-SrcA-diff.png").write_bytes(b"DIFF_DATA")

    # Write summary.json into diff_comp_dir
    summary_path = diff_comp_dir / "summary.json"
    summary_data = {
        "golden_identifier": "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee:Linux_x86_64:gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits):gslv_4.50",
        "result_identifier": "xemu-0.8.136-51-g3aee4c1682-3aee4c16820a8ca84548e979d4a062aba28abc21:Linux_x86_64:gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits):gslv_4.50",
    }
    summary_path.write_text(json.dumps(summary_data))

    templates_dir = (
        Path(__file__).resolve().parent.parent
        / ".github"
        / "scripts"
        / "site-templates"
    )

    jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))
    jinja_env.globals["sidenav_width"] = 48
    jinja_env.globals["sidenav_icon_width"] = 32

    generator = generate_results_site.Generator(
        results_dir=str(results_dir),
        hw_golden_comparison=str(hw_dir),
        xemu_golden_comparison=str(xemu_dir),
        branch=branch,
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

    page_content = (output_dir / branch / "index.html").read_text()
    expected_golden_subpath = "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    expected_golden_url = f"https://example.com/xemu/results/{expected_golden_subpath}/Blend_surface/R5G6B5_Add_SrcA_1-SrcA.png"

    assert f"vs {expected_golden_subpath}" in page_content
    assert f'src="{expected_golden_url}"' in page_content
    assert 'src=""' not in page_content


def test_generate_site_populates_xemu_golden_from_comparisons_json(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "site"
    branch = "results_pr-3056"
    hw_dir = output_dir / branch / "compare_hw"
    xemu_dir = output_dir / branch / "compare_xemu"
    hw_dir.mkdir(parents=True)
    xemu_dir.mkdir(parents=True)

    results_dir = tmp_path / "results"
    run_rel = (
        "xemu-0.8.136-51-g3aee4c1682-3aee4c16820a8ca84548e979d4a062aba28abc21"
        "/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    )
    test_img_dir = results_dir / run_rel / "Blend_surface"
    test_img_dir.mkdir(parents=True)
    (test_img_dir / "R5G6B5_Add_SrcA_1-SrcA.png").write_bytes(b"PNG_DATA")

    golden_dir_name = (
        "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee__Linux_x86_64"
        "__gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)__gslv_4.50"
    )
    diff_comp_dir = xemu_dir / run_rel / golden_dir_name
    diff_img_dir = diff_comp_dir / "Blend_surface"
    diff_img_dir.mkdir(parents=True)
    (diff_img_dir / "R5G6B5_Add_SrcA_1-SrcA-diff.png").write_bytes(b"DIFF_DATA")

    # Write comparisons.json at root of xemu_dir
    comparisons_data = {
        f"results/{run_rel}": "xemu-baseline/results/xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    }
    (xemu_dir / "comparisons.json").write_text(json.dumps(comparisons_data))

    templates_dir = (
        Path(__file__).resolve().parent.parent
        / ".github"
        / "scripts"
        / "site-templates"
    )

    jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))
    jinja_env.globals["sidenav_width"] = 48
    jinja_env.globals["sidenav_icon_width"] = 32

    generator = generate_results_site.Generator(
        results_dir=str(results_dir),
        hw_golden_comparison=str(hw_dir),
        xemu_golden_comparison=str(xemu_dir),
        branch=branch,
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

    page_content = (output_dir / branch / "index.html").read_text()
    expected_golden_subpath = "xemu-0.8.136-fc24584ce88f0915ad7f04775bb7712c2e3f49ee/Linux_x86_64/gl_Mesa_llvmpipe_(LLVM_20.1.2,_256_bits)/gslv_4.50"
    expected_golden_url = f"https://example.com/xemu/results/{expected_golden_subpath}/Blend_surface/R5G6B5_Add_SrcA_1-SrcA.png"

    assert f"vs {expected_golden_subpath}" in page_content
    assert f'src="{expected_golden_url}"' in page_content
    assert 'src=""' not in page_content
