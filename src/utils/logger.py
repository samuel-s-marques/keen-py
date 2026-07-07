import os
import sys

from loguru import logger

# Ids of the handlers this module manages, so reconfiguring (e.g. toggling debug
# mode) removes only these — not third-party sinks such as the per-connection
# WebSocket queue sinks added by the API server.
_MANAGED_HANDLERS: list[int] = []
_default_cleared = False


def setup_logger(debug_mode: bool = False):
    """
    Configures the global loguru logger.
    - Console output: Clean and colorized. If debug_mode is True, shows more context.
    - File output: Detailed logs saved to logs/keen.log.
    """
    global _MANAGED_HANDLERS, _default_cleared

    if not _default_cleared:
        # Remove loguru's built-in default handler exactly once.
        logger.remove()
        _default_cleared = True
    else:
        # Remove only our previously-added handlers, leaving external sinks intact.
        for hid in _MANAGED_HANDLERS:
            try:
                logger.remove(hid)
            except ValueError:
                pass
    _MANAGED_HANDLERS = []

    # Create logs directory in the project root
    os.makedirs("logs", exist_ok=True)

    if debug_mode:
        console_format = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        console_level = "DEBUG"
    else:
        console_format = (
            "<level>{level: <8}</level> <cyan>|</cyan> <level>{message}</level>"
        )
        console_level = "INFO"

    # Add console handler
    console_id = logger.add(
        sys.stdout, format=console_format, level=console_level, colorize=True
    )

    # Add file handler with verbose formatting
    file_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
    file_id = logger.add(
        "logs/keen.log",
        format=file_format,
        level="DEBUG",
        rotation="10 MB",
        compression="zip",
    )

    _MANAGED_HANDLERS = [console_id, file_id]


def set_debug_mode(enable: bool):
    """
    Reconfigures the logger dynamically for debug mode.
    """
    setup_logger(debug_mode=enable)
