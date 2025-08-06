from pydantic_settings import BaseSettings, SettingsConfigDict
from citrascope.logging import CITRASCOPE_LOGGER


from citrascope.settings.defaults import UNDEFINED_INT, UNDEFINED_STRING


class CitraAPISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CITRA_API_",
        env_nested_delimiter="__",
    )

    host: str = UNDEFINED_STRING
    port: int = UNDEFINED_INT
    personal_access_token: str = UNDEFINED_STRING
    use_ssl: bool = False

    def model_post_init(self, __context) -> None:
        # log the host value
        if self.host == UNDEFINED_STRING:
            CITRASCOPE_LOGGER.warning(f"{self.__class__.__name__} host has not been set")
        else:
            CITRASCOPE_LOGGER.info(f"{self.__class__.__name__} host is {self.host}")
