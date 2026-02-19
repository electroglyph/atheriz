"""
Shared logger for the atheriz game server.

Usage:
    from atheriz.logger import logger

    logger.info("Something happened")
    logger.warning("Watch out!")
    logger.error("Something went wrong")
"""

import logging

from atheriz import settings

logger = logging.getLogger("atheriz")
FORMATTER = logging.Formatter("%(levelname)s: %(name)s: %(message)s")

def apply_settings():
    """Apply current settings to the logger."""
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    level = level_map.get(settings.LOG_LEVEL.lower(), logging.INFO)
    logger.setLevel(level)

def _setup_logger():
    """Ensure the logger has a default handler with the preferred formatter."""
    for h in logger.handlers:
        if isinstance(h.formatter, logging.Formatter) and h.formatter._fmt == FORMATTER._fmt:
            return
    
    handler = logging.StreamHandler()
    handler.setFormatter(FORMATTER)
    logger.addHandler(handler)
    logger.propagate = False

apply_settings()
_setup_logger()
