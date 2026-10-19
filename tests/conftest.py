from __future__ import annotations

import sys
from pathlib import Path

# Scripts in .github/scripts import sibling modules (e.g., renderer_info), which
# works when they are run directly but requires the directory on sys.path here.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / ".github" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
