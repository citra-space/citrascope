import logging


class ExcludeHttpRequestFilter(logging.Filter):
    def filter(self, record):
        return "HTTP Request:" not in record.getMessage()


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
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


CITRASCOPE_LOGGER = logging.getLogger()
CITRASCOPE_LOGGER.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.addFilter(ExcludeHttpRequestFilter())
log_format = "%(asctime)s %(levelname)s %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"
formatter = ColoredFormatter(fmt=log_format, datefmt=date_format)
handler.setFormatter(formatter)
CITRASCOPE_LOGGER.handlers.clear()
CITRASCOPE_LOGGER.addHandler(handler)
