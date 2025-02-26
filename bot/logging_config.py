import sys
import logging
from pythonjsonlogger import jsonlogger
import colorlog


def setup_logging(log_mode: str = "json", level: str = "INFO") -> None:
    """
    Sets up the logging configuration.

    Args:
        log_mode: Determines the logging format. Options are:
            - "json": Logs are output in JSON format.
            - "color": Logs are output to stdout with color highlighting.
        level: Logging level (e.g., "INFO", "DEBUG").
    """
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove any pre-existing handlers.
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    if log_mode == "json":
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    elif log_mode == "color":
        handler = logging.StreamHandler(sys.stdout)
        formatter = colorlog.ColoredFormatter(
            fmt="%(log_color)s%(asctime)s [%(levelname)s] %(message)s",
            log_colors={
                "DEBUG": "blue",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        # Fallback: use basic configuration.
        logging.basicConfig(level=level)
