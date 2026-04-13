"""Local code-based settings for VS Code driven runs.

Edit these values directly when you want to tune Epic 3 behavior without
threading more environment variables through the app.
"""

from __future__ import annotations

SELECTION_ENABLED = True
OPENAI_MODEL = "gpt-4.1-mini"
SELECTION_PREFERENCE_PROMPT: str | None = None
MAX_PHOTOS_PER_DAY: int | None = 10
MAX_PHOTOS_TOTAL: int | None = 30
LARGE_CLUSTER_THRESHOLD = 5
ALLOW_SPARE_CAPACITY_REUSE = True
MAX_FINAL_PHOTOS_PER_CLUSTER = 1
MAX_FINAL_PHOTOS_PER_CLUSTER_WITH_EXCEPTION = 2
SECOND_PASS_ENABLED = False
SECOND_PASS_EXTRA_CANDIDATES_PER_DAY = 2
# Keep debug runs small until the live ranking path is proven stable in this environment.
MAX_RANKING_CANDIDATES_PER_DAY: int | None = None
RANKING_CANDIDATE_SAMPLE_SEED = 17
OPENAI_UPLOAD_MAX_DIMENSION = 1280
OPENAI_UPLOAD_JPEG_QUALITY = 82
