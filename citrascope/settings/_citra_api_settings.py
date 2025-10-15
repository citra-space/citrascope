from pydantic_settings import BaseSettings, SettingsConfigDict
from citrascope.logging import CITRASCOPE_LOGGER


from citrascope.settings.defaults import UNDEFINED_INT, UNDEFINED_STRING




class CitraAPISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CITRA_API_",
        env_nested_delimiter="__",
    )

    # Default to production API
    host: str = "app.citra.space"
    port: int = UNDEFINED_INT
    personal_access_token: str = UNDEFINED_STRING
    use_ssl: bool = True

    def __init__(self, dev: bool = False, **kwargs):
        super().__init__(**kwargs)
        if dev:
            self.host = "dev.app.citra.space"
            CITRASCOPE_LOGGER.info("Using development API endpoint.")

    def model_post_init(self, __context) -> None:
        # log the host value
        if self.host == UNDEFINED_STRING:
            CITRASCOPE_LOGGER.warning(f"{self.__class__.__name__} host has not been set")
        else:
            CITRASCOPE_LOGGER.info(f"{self.__class__.__name__} host is {self.host}")
