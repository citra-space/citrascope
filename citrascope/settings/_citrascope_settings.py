from pydantic_settings import BaseSettings, SettingsConfigDict

from citrascope.logging import CITRASCOPE_LOGGER

UNDEFINED_STRING = "undefined"


class CitraScopeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CITRASCOPE_",
        env_nested_delimiter="__",
    )

    # Default to production API
    host: str = "api.citra.space"
    port: int = 443

    personal_access_token: str = UNDEFINED_STRING
    use_ssl: bool = True
    telescope_id: str = UNDEFINED_STRING

    # Hardware adapter selection
    hardware_adapter: str = "indi"  # Options: "indi", "nina"

    # INDI adapter settings
    indi_server_url: str = "localhost"
    indi_server_port: int = 7624
    indi_telescope_name: str = UNDEFINED_STRING
    indi_camera_name: str = UNDEFINED_STRING

    # NINA Advanced API adapter settings
    nina_url_prefix: str = "http://nina:1888/v2/api"
    nina_scp_command_template: str = (
        "pwd"  # system command to copy files to NINA computer, default just prints working directory
    )

    log_level: str = "INFO"
    keep_images: bool = False
    bypass_autofocus: bool = False

    def __init__(
        self,
        dev: bool = False,
        log_level: str = "INFO",
        keep_images: bool = False,
        bypass_autofocus: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.log_level = log_level
        self.keep_images = keep_images
        self.bypass_autofocus = bypass_autofocus
        if dev:
            self.host = "dev.api.citra.space"
            CITRASCOPE_LOGGER.info("Using development API endpoint.")

    def model_post_init(self, __context) -> None:
        if self.personal_access_token == UNDEFINED_STRING:
            CITRASCOPE_LOGGER.warning(f"{self.__class__.__name__} personal_access_token has not been set")
            exit(1)
        if self.telescope_id == UNDEFINED_STRING:
            CITRASCOPE_LOGGER.warning(f"{self.__class__.__name__} telescope_id has not been set")
            exit(1)
