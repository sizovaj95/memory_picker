2026-03-13 - E01/F01/S01: Added `pyproject.toml` with uv-compatible project metadata, runtime dependencies, and pytest configuration.
2026-03-13 - E01/F01/S02: Created the `src/memory_picker` package and the `tests` layout for unit and end-to-end coverage.
2026-03-13 - E01/F01/S03: Added typed application settings for supported formats, managed folder names, thresholds, and future quota placeholders.
2026-03-13 - E01/F01/S04: Added shared logging configuration for the CLI and pipeline modules.
2026-03-13 - E01/F01/S05: Added a bootstrap smoke test that validates settings defaults load correctly.
2026-03-13 - E01/F02/S01: Implemented flat-root scanning with managed-folder and nested-directory skipping.
2026-03-13 - E01/F02/S02: Added deterministic extension-based classification for photos, non-photo artifacts, and unsupported files.
2026-03-13 - E01/F02/S03: Configured the initial supported format sets for JPG, JPEG, PNG, HEIC, MOV, and AAE handling.
2026-03-13 - E01/F02/S04: Added normalized inventory records with absolute paths, normalized extensions, sizes, and classifications.
2026-03-13 - E01/F02/S05: Added unit tests covering mixed folders, extension casing, and managed-folder skipping.
2026-03-13 - E01/F03/S01: Implemented EXIF capture-date extraction with standard datetime tag support.
2026-03-13 - E01/F03/S02: Added filesystem mtime fallback when EXIF data is missing or unreadable.
2026-03-13 - E01/F03/S03: Added deterministic day-map generation from ascending distinct calendar dates.
2026-03-13 - E01/F03/S04: Added structured day assignments with day name, day index, and timestamp provenance.
2026-03-13 - E01/F03/S05: Added unit tests for EXIF-first behavior, mtime fallback, same-day grouping, and stable numbering.
2026-03-13 - E01/F04/S01: Implemented safe image-open validation and corrupt-file rejection.
2026-03-13 - E01/F04/S02: Added deterministic blur scoring using a Laplacian variance metric.
2026-03-13 - E01/F04/S03: Added dark and overexposure checks with configurable thresholds.
2026-03-13 - E01/F04/S04: Added structured quality assessments with metrics, rejection reasons, and optional error details.
2026-03-13 - E01/F04/S05: Added unit tests for sharp, blurry, dark, and corrupt image cases.
2026-03-13 - E01/F05/S01: Implemented lazy creation of day, rejected, and not_photo directories during file moves.
2026-03-13 - E01/F05/S02: Added non-photo and unsupported-file moves into day-level `not_photo` folders.
2026-03-13 - E01/F05/S03: Added rejected-photo moves into day-level `rejected` folders.
2026-03-13 - E01/F05/S04: Added accepted-photo moves into the assigned `dayXX` root.
2026-03-13 - E01/F05/S05: Added collision-safe duplicate suffix handling to prevent silent overwrites.
2026-03-13 - E01/F05/S06: Added unit tests covering directory creation, placement, and collision-safe moves.
2026-03-13 - E01/F06/S01: Added the `memory-picker` CLI entrypoint with root-path and log-level arguments.
2026-03-13 - E01/F06/S02: Wired inventory, day assignment, quality checks, and file moves into a single pipeline function.
2026-03-13 - E01/F06/S03: Added pipeline summary logging with accepted, rejected, and artifact counts.
2026-03-13 - E01/F06/S04: Added a user-facing run summary report returned by the pipeline and printed by the CLI.
2026-03-13 - E01/F06/S05: Added an end-to-end test covering a full run and an idempotent rerun on the same folder.
2026-03-17 - E01/F06/S04: Added a VS Code-oriented debug entrypoint with a hardcoded root path and launch configuration for one-click local debugging.
2026-03-20 - E01/F04/S02: Replaced the global blur score with a tile-based blur score that emphasizes the sharpest regions of the image.
2026-03-20 - E01/F04/S05: Added a quality test covering intentional background blur with a sharp subject region.
