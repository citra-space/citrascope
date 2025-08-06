import logging

from pythonjsonlogger.json import JsonFormatter

CITRASCOPE_LOGGER = logging.getLogger()
CITRASCOPE_LOGGER.setLevel(logging.INFO)


class CitraScopeFormatter(JsonFormatter):
    def process_log_record(self, log_record: dict) -> dict:
        log_record.pop("color_message", None)
        return super().process_log_record(log_record)


handler = logging.StreamHandler()
log_format = "%(asctime)s %(levelname)s %(message)s"
rename_fields = {
    "asctime": "epoch",
    "levelname": "level",
}
date_format = "%Y-%m-%dT%H:%M:%S.%fZ"
formatter = CitraScopeFormatter(
    fmt=log_format,
    datefmt=date_format,
    rename_fields=rename_fields,
)
handler.setFormatter(formatter)
CITRASCOPE_LOGGER.handlers.clear()
CITRASCOPE_LOGGER.addHandler(handler)

# TODO: There are no extra modules to clear handlers for at the moment, but this is a placeholder
modules: list[str] = []
for module in modules:
    logger = logging.getLogger(module)
    logger.handlers.clear()
    logger.propagate = True
