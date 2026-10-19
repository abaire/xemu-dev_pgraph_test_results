"""Helpers for determining which xemu renderer produced a set of results."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os

logger = logging.getLogger(__name__)

OPENGL = "OpenGL"
VULKAN = "Vulkan"

RENDERER_FILENAME = "renderer.json"


def detect_renderer(run_dir: str | os.PathLike[str]) -> str:
    """Returns OPENGL or VULKAN for the given results run directory.

    The run directory is the one containing machine_info.txt and the suite
    subdirectories. xemu-pgraph-run writes a renderer.json file there; if it is
    missing (e.g., older results), the 'vk_' prefix that the test runner applies
    to the GL info path component is used instead.
    """
    path = Path(run_dir)
    renderer_file = path / RENDERER_FILENAME
    try:
        with renderer_file.open(encoding="utf-8") as infile:
            data = json.load(infile)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read %s", renderer_file, exc_info=True)
    else:
        if isinstance(data, dict) and isinstance(data.get("vulkan"), bool):
            return VULKAN if data["vulkan"] else OPENGL
        logger.warning("Ignoring malformed %s: %r", renderer_file, data)

    return VULKAN if any(part.startswith("vk_") for part in path.parts) else OPENGL
