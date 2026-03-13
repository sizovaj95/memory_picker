"""Image format helpers shared by image-processing modules."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def register_heif_support() -> None:
    """Register HEIF/HEIC support when the optional plugin is available."""

    try:
        import pillow_heif
    except ImportError:
        return

    pillow_heif.register_heif_opener()
