"""Structured logging setup."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with a structured, timestamped format."""
    root = logging.getLogger()
    if root.handlers:
        # Avoid duplicate handlers on reload
        root.setLevel(level.upper())
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet noisy libraries a bit
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
