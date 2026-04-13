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
2026-03-30 - E03/F01/S01: Added typed Epic 3 selection settings for OpenAI model choice, prompt preferences, caps, and large-cluster dedup behavior.
2026-03-30 - E03/F01/S02: Added an optional configurable GPT preference prompt while preserving a default diversity-first ranking prompt.
2026-03-30 - E03/F01/S03: Added a strict structured day-ranking schema with stable photo IDs, scores, tags, rationales, and good-enough signals.
2026-03-30 - E03/F01/S04: Added deterministic local score normalization so saved day rankings can be reused for trip-wide selection without resending images.
2026-03-30 - E03/F01/S05: Added mocked tests covering prompt construction, schema-driven ranking flow, and score reuse.
2026-03-30 - E03/F02/S01: Added Epic 3 candidate preparation that reads Epic 2 cluster manifests and identifies large clusters for deduplication.
2026-03-30 - E03/F02/S02: Collapsed burst groups to one survivor each only for clusters larger than five photos before GPT ranking.
2026-03-30 - E03/F02/S03: Left singleton and small clusters unchanged so GPT still sees all non-duplicate candidates.
2026-03-30 - E03/F02/S04: Built complete per-day GPT candidate sets from untouched photos plus large-cluster burst survivors.
2026-03-30 - E03/F02/S05: Added unit coverage proving only large clusters are reduced before ranking.
2026-03-30 - E03/F03/S01: Added per-day multimodal GPT request construction with stable photo IDs and no cluster or representative metadata.
2026-03-30 - E03/F03/S02: Threaded optional prompt preferences into day-ranking requests without making them mandatory.
2026-03-30 - E03/F03/S03: Parsed full day rankings into stable records with scores, tags, rationales, and explicit good-enough flags.
2026-03-30 - E03/F03/S04: Persisted `day_selection_manifest.json` files for each ranked day with prompt and response metadata.
2026-03-30 - E03/F03/S05: Added deterministic validation for malformed GPT outputs including missing IDs, duplicates, and non-contiguous ranks.
2026-03-30 - E03/F03/S06: Added mocked tests for day-ranking request construction and manifest-compatible ranking results.
2026-03-30 - E03/F04/S01: Added local trip-wide selection that merges saved day results without resending photos.
2026-03-30 - E03/F04/S02: Applied per-day and trip-wide photo limits as ceilings rather than fill targets.
2026-03-30 - E03/F04/S03: Stopped final selection early when no additional photos remained good enough.
2026-03-30 - E03/F04/S04: Allowed optional spillover reuse of spare capacity only when stronger saved candidates remained.
2026-03-30 - E03/F04/S05: Added tests covering early stop behavior and non-forced quota filling.
2026-03-30 - E03/F05/S01: Added deterministic `to_print/dayXX` materialization for final album outputs.
2026-03-30 - E03/F05/S02: Copied selected photos into `to_print` without mutating original day folders.
2026-03-30 - E03/F05/S03: Added a trip-level `to_print/selection_manifest.json` capturing final picks, source cluster data, and prompt metadata.
2026-03-30 - E03/F05/S04: Extended the end-to-end pipeline test to cover Epic 3 manifests, `to_print` outputs, and rerun safety.
