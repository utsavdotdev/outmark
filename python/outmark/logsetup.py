"""Logging configuration for the Linux-side process."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure a single stream handler. Safe to call once at startup."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
