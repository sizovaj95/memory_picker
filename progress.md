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
2026-03-23 - E02/F01/S01: Added accepted-photo clustering records with day metadata, dimensions, orientation, quality metrics, and deterministic similarity descriptors.
2026-03-23 - E02/F01/S02: Implemented accepted-photo discovery from day roots while excluding rejected, not_photo, and manifest files.
2026-03-23 - E02/F01/S03: Added perceptual-hash and normalized RGB histogram extraction for burst-group preprocessing.
2026-03-23 - E02/F01/S04: Added preprocessing tests for accepted-photo discovery, descriptor extraction, and day-folder filtering.
2026-03-23 - E02/F02/S01: Introduced an image-embedder abstraction for Epic 2 clustering.
2026-03-23 - E02/F02/S02: Implemented a default DINOv2 ViT-B/14 embedder with configurable model, device, and batch size settings.
2026-03-23 - E02/F02/S03: Normalized embedding vectors for cosine-distance comparisons in Stage 2 clustering.
2026-03-23 - E02/F02/S04: Added filename-based mock embeddings so automated tests do not invoke a real model.
2026-03-23 - E02/F02/S05: Added an opt-in manual DINOv2 benchmark test path guarded by an environment variable.
2026-03-23 - E02/F03/S01: Implemented deterministic burst grouping using time gap, perceptual hash, and histogram similarity thresholds.
2026-03-23 - E02/F03/S02: Embedded accepted photos and used burst representatives as semantic-clustering seeds.
2026-03-23 - E02/F03/S03: Added deterministic agglomerative clustering with cosine-distance thresholding for per-day semantic groups.
2026-03-23 - E02/F03/S04: Propagated final cluster IDs from burst representatives back to all accepted photos in the day.
2026-03-23 - E02/F03/S05: Added deterministic medoid selection for final cluster representatives.
2026-03-23 - E02/F03/S06: Added unit tests covering duplicate-heavy bursts, mixed-scene clustering, and representative stability.
2026-03-23 - E02/F04/S01: Defined a per-day cluster manifest schema containing summaries, burst groups, clusters, members, and similarity metrics.
2026-03-23 - E02/F04/S02: Persisted cluster manifests as `cluster_manifest.json` files inside each clustered day folder.
2026-03-23 - E02/F04/S03: Added per-day summary blocks with accepted-photo, burst-group, final-cluster, and singleton counts.
2026-03-23 - E02/F04/S04: Added manifest and pipeline rerun tests and verified Epic 2 with `15 passed, 1 skipped`.
2026-04-13 - E03/F01/S01-S03: Added deterministic post-cluster duplicate detection scoped to members that share both a final cluster and a burst group, using configurable pixel similarity and duplicate-set grouping.
2026-04-13 - E03/F02/S01-S03: Added deterministic duplicate winner selection, safe loser moves into `dayXX/rejected`, and coverage for clusters that collapse to a single surviving photo.
2026-04-13 - E03/F03/S01-S03: Added stable survivor renaming to `cNNN_bNNN_NNN.ext` with two-phase collision-safe renames and rerun-safe behavior.
2026-04-13 - E03/F04/S01-S03: Rewrote cluster manifests after cleanup, integrated Epic 3 into the main pipeline after clustering, refreshed planning docs for deterministic cleanup, and removed the deferred Epic 4 planning docs.
2026-04-13 - E04/F01/S01-S02: Added optional categorization settings with configurable OpenAI taxonomy defaults for people, animals, food, nature, city, buildings, architecture, and other.
2026-04-13 - E04/F02/S01-S03: Added a mockable OpenAI cluster categorizer with structured prompt/schema generation and explicit exclusion of `rejected` and `not_photo` files from AI classification.
2026-04-13 - E04/F03/S01-S02: Added per-day category materialization that moves accepted photos into category folders while preserving Epic 3 filenames and leaving rejected/non-photo files untouched.
2026-04-13 - E04/F04/S01-S03: Rewrote cluster manifests with category metadata, made accepted-photo loading recursive for rerun safety after categorization, integrated Epic 4 into the pipeline, and added automated tests for the optional categorization path.
2026-04-16 - E01/F05 + E03/F02: Reshaped day-level rejection storage into `_rejected/low_quality`, `_rejected/not_photo`, and `_rejected/duplicates`, renamed the reserved root folder to `_rejected`, and refreshed tests/docs for the new layout.
2026-04-20 - E01/F06 + E04/F02: Added configurable threaded quality checks, async OpenAI categorization with bounded concurrency and retries, richer stage/progress logging, and tests covering stable ordering plus failed/retired categorization behavior.
2026-04-20 - E01/F01: Added a mandatory front-of-pipeline HEIF/HEIC to JPEG conversion stage with metadata-preserving in-place replacement, collision-safe `__convertedNN` naming, run-summary reporting, and unit/e2e coverage for conversion, failure handling, and rerun safety.
