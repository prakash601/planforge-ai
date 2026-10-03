"""Evidence-gated wall openings, not semantic or metric ground truth."""

from .detection import OpeningConfig, detect_openings
from .model import attach_openings

__all__ = ["OpeningConfig", "attach_openings", "detect_openings"]
