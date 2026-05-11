from loguru import logger

def success(message: str) -> None:
    logger.opt(depth=1).success(message)

def info(message: str) -> None:
    logger.opt(depth=1).info(message)

def error(message: str) -> None:
    logger.opt(depth=1).error(message)

def warn(message: str) -> None:
    logger.opt(depth=1).warning(message)
