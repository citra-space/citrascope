from pydantic_settings import BaseSettings, SettingsConfigDict
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings.defaults import UNDEFINED_INT, UNDEFINED_STRING


class CitraAPISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CITRA_API_",
        env_nested_delimiter="__",
    )

    # Default to production API
    host: str = "api.citra.space"
    port: int = 443
    personal_access_token: str = UNDEFINED_STRING
    use_ssl: bool = True
    telescope_id: str = UNDEFINED_STRING

    def __init__(self, dev: bool = False, **kwargs):
        super().__init__(**kwargs)
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
