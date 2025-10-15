import logging

CITRASCOPE_LOGGER = logging.getLogger()
CITRASCOPE_LOGGER.setLevel(logging.INFO)

handler = logging.StreamHandler()
log_format = "%(asctime)s %(levelname)s %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
handler.setFormatter(formatter)
CITRASCOPE_LOGGER.handlers.clear()
CITRASCOPE_LOGGER.addHandler(handler)
