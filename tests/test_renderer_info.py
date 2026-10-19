from __future__ import annotations

from typing import TYPE_CHECKING

from renderer_info import OPENGL, VULKAN, detect_renderer

if TYPE_CHECKING:
    from pathlib import Path


def test_detect_renderer_reads_renderer_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "Linux_x86_64" / "gl_Mesa_llvmpipe" / "gslv_4.50"
    run_dir.mkdir(parents=True)

    (run_dir / "renderer.json").write_text('{"vulkan": true}', encoding="utf-8")
    assert detect_renderer(run_dir) == VULKAN

    (run_dir / "renderer.json").write_text('{"vulkan": false}', encoding="utf-8")
    assert detect_renderer(str(run_dir)) == OPENGL


def test_detect_renderer_json_overrides_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "Linux_x86_64" / "vk_Mesa_llvmpipe" / "gslv_4.50"
    run_dir.mkdir(parents=True)
    (run_dir / "renderer.json").write_text('{"vulkan": false}', encoding="utf-8")

    assert detect_renderer(run_dir) == OPENGL


def test_detect_renderer_falls_back_to_path(tmp_path: Path) -> None:
    vk_dir = tmp_path / "Linux_x86_64" / "vk_Mesa_llvmpipe" / "gslv_4.50"
    gl_dir = tmp_path / "Linux_x86_64" / "gl_Mesa_llvmpipe" / "gslv_4.50"
    vk_dir.mkdir(parents=True)
    gl_dir.mkdir(parents=True)

    assert detect_renderer(vk_dir) == VULKAN
    assert detect_renderer(gl_dir) == OPENGL
    # Directories need not exist for path-based detection.
    assert detect_renderer("results/ver/Linux/vk_Foo/gslv_1") == VULKAN


def test_detect_renderer_malformed_json_falls_back(tmp_path: Path) -> None:
    run_dir = tmp_path / "vk_Mesa_llvmpipe" / "gslv_4.50"
    run_dir.mkdir(parents=True)

    (run_dir / "renderer.json").write_text("not json", encoding="utf-8")
    assert detect_renderer(run_dir) == VULKAN

    (run_dir / "renderer.json").write_text('{"vulkan": "yes"}', encoding="utf-8")
    assert detect_renderer(run_dir) == VULKAN
