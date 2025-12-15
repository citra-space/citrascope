import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


class ExcludeHttpRequestFilter(logging.Filter):
    def filter(self, record):
        return "HTTP Request:" not in record.getMessage()


class ExcludeWebLogsFilter(logging.Filter):
    """Filter out web-related logs (uvicorn, HTTP requests) from file logging."""

    def filter(self, record):
        # Exclude uvicorn loggers
        if record.name.startswith("uvicorn"):
            return False
        # Exclude HTTP request messages
        if "HTTP Request:" in record.getMessage():
            return False
        # Exclude WebSocket messages
        if "WebSocket" in record.getMessage():
            return False
        return True


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[95m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        # Save original levelname
        original_levelname = record.levelname

        # Temporarily add color codes
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"

        # Format the record
        result = super().format(record)

        # Restore original levelname so other handlers don't get colored version
        record.levelname = original_levelname

        return result


CITRASCOPE_LOGGER = logging.getLogger()
CITRASCOPE_LOGGER.setLevel(logging.INFO)

# Console handler with colors
handler = logging.StreamHandler()
handler.addFilter(ExcludeHttpRequestFilter())
log_format = "%(asctime)s %(levelname)s %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"
formatter = ColoredFormatter(fmt=log_format, datefmt=date_format)
handler.setFormatter(formatter)
CITRASCOPE_LOGGER.handlers.clear()
CITRASCOPE_LOGGER.addHandler(handler)

# File handler will be added by setup_file_logging()
_file_handler: Optional[TimedRotatingFileHandler] = None


def setup_file_logging(log_file_path: Path, backup_count: int = 30) -> None:
    """Setup file-based logging with daily rotation.

    Args:
        log_file_path: Path to the log file (should include date in filename).
        backup_count: Number of daily log files to keep (default 30 days).
    """
    global _file_handler

    # Remove existing file handler if present
    if _file_handler is not None:
        CITRASCOPE_LOGGER.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None

    # Create new file handler with daily rotation
    _file_handler = TimedRotatingFileHandler(
        filename=str(log_file_path),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
    )

    # Add filter to exclude web logs
    _file_handler.addFilter(ExcludeWebLogsFilter())

    # Use plain formatter (no ANSI colors for files)
    plain_formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    _file_handler.setFormatter(plain_formatter)
    _file_handler.setLevel(logging.INFO)

    # Add to logger
    CITRASCOPE_LOGGER.addHandler(_file_handler)


def get_file_handler() -> Optional[TimedRotatingFileHandler]:
    """Get the current file handler.

    Returns:
        The file handler if file logging is set up, None otherwise.
    """
    return _file_handler
