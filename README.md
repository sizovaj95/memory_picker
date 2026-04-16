# Memory Picker

Memory Picker is a local Python project for cleaning up trip photos and organizing them into a structure that is easier to review.

It started as an attempt to automate travel-album curation, but the current focus is more practical and grounded:
- filter out low-quality photos
- move non-photo artifacts aside
- organize accepted photos into `dayXX` folders
- cluster similar photos within each day
- detect near-duplicates inside the same cluster and burst group
- keep the best deterministic survivor
- rename survivors into stable, sortable filenames
- optionally categorize clusters with an OpenAI vision model

## What The Pipeline Does

Given a flat folder of trip media, the pipeline currently works like this:

1. Scan the trip root and classify files as photo, non-photo, or unsupported.
2. Read capture dates from EXIF when possible, otherwise fall back to filesystem modification time.
3. Create `day01`, `day02`, and so on.
4. Run local quality checks to reject blurry, too-dark, too-bright, or corrupt photos.
5. Move low-quality photos into `dayXX/_rejected/low_quality`.
6. Move videos, non-photo artifacts, and corrupt files into `dayXX/_rejected/not_photo`.
7. Keep accepted photos in the day root.
8. Build deterministic burst groups and semantic clusters for each day.
9. Write a `cluster_manifest.json` for each day.
10. Detect near-duplicates only within the same cluster and same burst group.
11. Keep the best deterministic winner and move duplicate losers into `dayXX/_rejected/duplicates`.
12. Rename survivors to names like `c001_b001_001.jpg`.
13. Optionally send one representative image per cluster to OpenAI for categorization.
14. If categorization is enabled, move accepted photos into per-day category folders such as `day01/people` or `day02/architecture`.

The project is designed to avoid destructive deletion. Files are moved into explicit folders instead of being removed.

## Current Folder Shape

After a run, a trip folder can look like this:

```text
MyTrip/
├── day01/
│   ├── _rejected/
│   │   ├── low_quality/
│   │   ├── not_photo/
│   │   └── duplicates/
│   ├── architecture/
│   │   └── c001_b001_001.jpg
│   └── cluster_manifest.json
└── day02/
    ├── _rejected/
    │   ├── low_quality/
    │   ├── not_photo/
    │   └── duplicates/
    ├── people/
    │   ├── c001_b001_001.jpg
    │   └── c001_b002_001.jpg
    └── cluster_manifest.json
```

If AI categorization is disabled, accepted photos stay directly in the `dayXX` root after cleanup and renaming.

## Tech Stack

- Python 3.12+
- `uv` for project and dependency management
- `pytest` for unit and end-to-end tests
- `Pillow` and `pillow-heif` for image IO
- `numpy` for image metrics and similarity calculations
- `torch` and `transformers` for local DINOv2 embeddings
- `openai` for optional Epic 4 cluster categorization
- `python-dotenv` for reading `.env`

## Running The Project

Install dependencies with `uv`, then run either the CLI or the debug entrypoint.

### CLI

```bash
uv run memory-picker --root /path/to/trip/folder
```

Optional logging level:

```bash
uv run memory-picker --root /path/to/trip/folder --log-level DEBUG
```

### VS Code Debug Flow

The repo also includes a debug entrypoint in `src/memory_picker/debug_run.py`. Edit `DEBUG_ROOT` there and run it from VS Code.

## Configuration

Most settings live in `src/memory_picker/config.py`, including:
- supported file extensions
- quality thresholds
- clustering thresholds
- duplicate-cleanup thresholds
- optional AI categorization settings

OpenAI credentials are loaded from `.env` using `python-dotenv`:

```env
OPENAI_API_KEY=your_key_here
```

AI categorization is optional and is currently controlled in code via `CategorizationSettings.enabled`.

## Tests

Run the full suite with:

```bash
uv run pytest
```

The test suite mocks AI categorization. It does not make real OpenAI calls.

## Project Structure

```text
src/memory_picker/   application code
tests/               unit and end-to-end tests
planning_docs/       epic/feature/story backlog in JSON
progress.md          append-only implementation log
instructions.md      original standing project brief for the AI agent
example_photos/      sample photos for development and experiments
```

## This Repo Was Also An AI Workflow Experiment

This project was not only built with AI assistance. It was also an attempt to work with an AI agent in a persistent, Scrum-like way.

The idea was to give the agent a stable operating context and let it keep moving the project forward across many sessions:

- [instructions.md](instructions.md) acted as the long-lived brief
  It described the problem, constraints, preferred architecture, testing rules, and working style.
- [planning_docs](planning_docs) acted as a backlog
  Work was broken down into epics, features, and stories in a structured JSON format.
- [progress.md](progress.md) acted as the running delivery log
  After each story or important revision, the agent appended what had changed.

So the repo is both:
- a photo-processing tool
- a record of an experiment in managing AI-driven software development with persistent instructions, backlog artifacts, and explicit progress tracking

## Status

The implemented epics today are:
- Epic 1: intake, quality filtering, day assignment, and file moves
- Epic 2: preprocessing, burst grouping, embeddings, clustering, and manifests
- Epic 3: deterministic duplicate rejection, survivor renaming, and manifest refresh
- Epic 4: optional OpenAI-based cluster categorization

The project is still evolving, but it already works as a useful local photo-cleanup pipeline.
