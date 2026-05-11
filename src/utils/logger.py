import sys
import os
from loguru import logger

def setup_logger(debug_mode: bool = False):
    """
    Configures the global loguru logger.
    - Console output: Clean and colorized. If debug_mode is True, shows more context.
    - File output: Detailed logs saved to logs/keen.log.
    """
    # Remove default handler
    logger.remove()
    
    # Create logs directory in the project root
    os.makedirs("logs", exist_ok=True)
    
    if debug_mode:
        console_format = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        console_level = "DEBUG"
    else:
        console_format = "<level>{level: <8}</level> <cyan>|</cyan> <level>{message}</level>"
        console_level = "INFO"

    # Add console handler
    logger.add(sys.stdout, format=console_format, level=console_level, colorize=True)
    
    # Add file handler with verbose formatting
    file_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
    logger.add("logs/keen.log", format=file_format, level="DEBUG", rotation="10 MB", compression="zip")

def set_debug_mode(enable: bool):
    """
    Reconfigures the logger dynamically for debug mode.
    """
    setup_logger(debug_mode=enable)
