"""Command-line entrypoint for Memory Picker."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from memory_picker.config import build_settings
from memory_picker.heif_conversion import convert_trip_root_heif_files
from memory_picker.logging_utils import configure_logging
from memory_picker.pipeline import run_pipeline

WINDOWS_PHOTO_ROOT = Path("/mnt/d/Documents/Photos")
ORANGE_ANSI = "\033[38;5;214m"
RESET_ANSI = "\033[0m"


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser."""

    parser = argparse.ArgumentParser(description="Organize and filter a flat trip photo folder.")
    parser.add_argument("--root", help="Path to the trip folder to process.")
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
    if args.root:
        settings = build_settings(args.root)
        summary = run_pipeline(settings)
        print(summary.to_report())
        return 0

    root_path = prompt_for_trip_root()
    convert_only = prompt_yes_no(
        "Only convert HEIC/HEIF photos to JPG and stop?",
        default=False,
    )

    settings = build_settings(root_path)
    if convert_only:
        summary = convert_trip_root_heif_files(settings)
        print("HEIF conversion summary")
        print(f"  converted_heif_files: {summary.converted_files}")
        print(f"  deleted_original_heif_files: {summary.deleted_original_files}")
        return 0

    categorization_enabled = prompt_yes_no(
        "Apply OpenAI categorization after cleanup?",
        default=True,
    )
    settings = replace(
        settings,
        categorization_settings=replace(
            settings.categorization_settings,
            enabled=categorization_enabled,
        ),
    )
    if categorization_enabled:
        print_warning("Turn VPN off before OpenAI categorization.")
        print_category_names(settings)

    summary = run_pipeline(settings)
    print(summary.to_report())
    return 0


def prompt_for_trip_root() -> Path:
    """Prompt for the trip folder name under the default Windows photo root."""

    questionary = _require_questionary()
    print("Photo root selection")
    print(f"  Base folder: D:/Documents/Photos/ -> {WINDOWS_PHOTO_ROOT}")
    while True:
        folder_name = questionary.text(
            "Type the photo folder name under D:/Documents/Photos/:"
        ).ask()
        if folder_name is None:
            raise KeyboardInterrupt("Photo root selection was cancelled.")
        folder_name = folder_name.strip()
        candidate = WINDOWS_PHOTO_ROOT / folder_name
        if candidate.exists() and candidate.is_dir():
            print(f"Selected: {candidate}")
            return candidate
        print(f"Folder not found: {candidate}")


def prompt_yes_no(prompt: str, default: bool) -> bool:
    """Prompt with arrow-key selection and Enter to confirm."""

    questionary = _require_questionary()
    default_label = "Yes" if default else "No"
    result = questionary.select(
        prompt,
        choices=["Yes", "No"],
        default=default_label,
    ).ask()
    if result is None:
        raise KeyboardInterrupt("Prompt was cancelled.")
    return result == "Yes"


def print_warning(message: str) -> None:
    """Print an orange terminal warning when ANSI colors are supported."""

    print(f"{ORANGE_ANSI}{message}{RESET_ANSI}")


def print_category_names(settings) -> None:
    """Print the configured category names without explanations."""

    print("Photos will be sorted into these categories:")
    for category in settings.categorization_settings.categories:
        print(f"  - {category.name}")


def _require_questionary():
    """Import questionary lazily for interactive CLI mode."""

    try:
        import questionary
    except ImportError as exc:  # pragma: no cover - exercised in real interactive runs.
        raise RuntimeError(
            "Interactive CLI requires `questionary` to be installed. "
            "Run `uv sync` to install project dependencies."
        ) from exc
    return questionary
