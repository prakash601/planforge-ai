"""Candidate property stitching, without inventing alignment or adjacency."""

from .model import (
    StitchingConfig,
    load_inputs,
    stitch_measurements,
    validate_property,
)

__all__ = [
    "StitchingConfig",
    "load_inputs",
    "stitch_measurements",
    "validate_property",
]
