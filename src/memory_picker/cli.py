"""Command-line entrypoint for Memory Picker."""

from __future__ import annotations

import argparse

from memory_picker.config import build_settings
from memory_picker.logging_utils import configure_logging
from memory_picker.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser."""

    parser = argparse.ArgumentParser(description="Organize and filter a flat trip photo folder.")
    parser.add_argument("--root", required=True, help="Path to the trip folder to process.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level for the run (for example INFO or DEBUG).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(args.log_level.upper())
    settings = build_settings(args.root)
    summary = run_pipeline(settings)
    print(summary.to_report())
    return 0
