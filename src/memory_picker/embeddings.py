"""Local image embedding backends for Epic 2 clustering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
import logging

from memory_picker.config import EmbeddingSettings
from memory_picker.image_support import register_heif_support
from memory_picker.logging_utils import log_progress
from memory_picker.models import AcceptedPhotoRecord, ImageEmbedding

LOGGER = logging.getLogger("memory_picker.embeddings")


class ImageEmbedder(ABC):
    """Abstract image embedder interface used by clustering."""

    @abstractmethod
    def embed_images(self, photo_records: Sequence[AcceptedPhotoRecord]) -> list[ImageEmbedding]:
        """Return one normalized embedding per photo."""


@dataclass
class DinoV2ImageEmbedder(ImageEmbedder):
    """DINOv2 image embedder loaded lazily from Transformers."""

    settings: EmbeddingSettings
    _model: object = field(init=False, repr=False)
    _processor: object = field(init=False, repr=False)
    _torch: object = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModel
        except ImportError as exc:  # pragma: no cover - exercised in real runs
            raise RuntimeError(
                "DINOv2 embedding requires `torch` and `transformers` to be installed."
            ) from exc

        self._torch = torch
        device = self.resolve_device(self.settings.device)
        from_pretrained_kwargs = {}
        if self.settings.hf_token:
            from_pretrained_kwargs["token"] = self.settings.hf_token
        self._processor = AutoImageProcessor.from_pretrained(
            self.settings.model_name,
            **from_pretrained_kwargs,
        )
        self._model = AutoModel.from_pretrained(
            self.settings.model_name,
            **from_pretrained_kwargs,
        )
        self._model.to(device)
        self._model.eval()
        self._device = device

    def resolve_device(self, requested_device: str) -> str:
        """Resolve the configured device into an actual torch device string."""

        if requested_device != "auto":
            return requested_device
        return "cuda" if self._torch.cuda.is_available() else "cpu"

    def _load_batch_images(self, paths: Sequence[Path]) -> list[Image.Image]:
        register_heif_support()
        images: list[Image.Image] = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        return images

    def embed_images(self, photo_records: Sequence[AcceptedPhotoRecord]) -> list[ImageEmbedding]:
        """Embed a sequence of photos and normalize the resulting vectors."""

        if not photo_records:
            return []

        LOGGER.info("Embedding %s accepted photos with %s", len(photo_records), self.settings.model_name)
        embeddings: list[ImageEmbedding] = []
        batch_size = max(1, self.settings.batch_size)
        for index in range(0, len(photo_records), batch_size):
            batch_records = photo_records[index : index + batch_size]
            images = self._load_batch_images([record.source_path for record in batch_records])
            inputs = self._processor(images=images, return_tensors="pt")
            inputs = {
                key: value.to(self._device) if hasattr(value, "to") else value
                for key, value in inputs.items()
            }
            with self._torch.no_grad():
                outputs = self._model(**inputs)
            pooled = getattr(outputs, "pooler_output", None)
            if pooled is None:
                pooled = outputs.last_hidden_state[:, 0]
            normalized = self._torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors = normalized.detach().cpu().numpy().astype(np.float32)

            for record, vector in zip(batch_records, vectors, strict=True):
                embeddings.append(ImageEmbedding(source_path=record.source_path, vector=vector))
            log_progress(
                LOGGER,
                "Embedding",
                len(embeddings),
                len(photo_records),
                noun="photo",
            )

        return embeddings
