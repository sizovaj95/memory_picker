"""VS Code-friendly debug entrypoint with a hardcoded folder path.

Edit ``DEBUG_ROOT`` to point at the folder you want to process, then run this
module from VS Code's debug button.
"""

from __future__ import annotations

from pathlib import Path

from memory_picker.config import build_settings
from memory_picker.logging_utils import configure_logging
from memory_picker.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUG_ROOT = REPO_ROOT / "japan_trip"
LOG_LEVEL = "DEBUG"


def main() -> int:
    """Run the pipeline using the hardcoded debug folder."""

    if not DEBUG_ROOT.exists():
        raise FileNotFoundError(
            f"Debug root does not exist: {DEBUG_ROOT}. "
            "Edit DEBUG_ROOT in src/memory_picker/debug_run.py."
        )

    configure_logging(LOG_LEVEL)
    settings = build_settings(DEBUG_ROOT)
    summary = run_pipeline(settings)
    print(summary.to_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
