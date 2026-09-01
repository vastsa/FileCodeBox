import logging
import os
import sys


PRODUCTION_ENVIRONMENTS = {"production", "prod"}
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def is_production_environment() -> bool:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    return environment in PRODUCTION_ENVIRONMENTS


def get_log_level_name() -> str:
    configured_level = os.getenv("LOG_LEVEL", "").strip().lower()
    if configured_level in LOG_LEVELS:
        return configured_level
    return "warning" if is_production_environment() else "info"


def get_log_level() -> int:
    return LOG_LEVELS[get_log_level_name()]


def is_access_log_enabled() -> bool:
    configured_value = os.getenv("ACCESS_LOG")
    if configured_value is not None:
        return configured_value.strip().lower() in {"1", "true", "yes", "on"}
    return not is_production_environment()


def setup_logger():
    _logger = logging.getLogger("FileCodeBox")
    level = get_log_level()
    _logger.setLevel(level)
    _logger.propagate = False

    if not _logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        _logger.addHandler(console_handler)
    else:
        console_handler = _logger.handlers[0]
    console_handler.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    return _logger


# 创建全局logger实例
logger = setup_logger()
