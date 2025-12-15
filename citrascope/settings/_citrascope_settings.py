"""CitraScope settings class using JSON-based configuration."""

from typing import Any, Dict, Optional

from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings.config_manager import ConfigManager


class CitraScopeSettings:
    """Settings for CitraScope loaded from JSON configuration file."""

    def __init__(
        self,
        dev: bool = False,
        log_level: str = "INFO",
        keep_images: bool = False,
    ):
        """Initialize settings from JSON config file.

        Args:
            dev: If True, use development API endpoint
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            keep_images: If True, preserve captured images
        """
        self.config_manager = ConfigManager()

        # Load configuration from file
        config = self.config_manager.load_config()

        # API Settings
        self.host: str = config.get("host", "dev.api.citra.space" if dev else "api.citra.space")
        self.port: int = config.get("port", 443)
        self.use_ssl: bool = config.get("use_ssl", True)
        self.personal_access_token: str = config.get("personal_access_token", "")
        self.telescope_id: str = config.get("telescope_id", "")

        # Hardware adapter selection
        self.hardware_adapter: str = config.get("hardware_adapter", "indi")

        # Hardware adapter-specific settings stored as dict
        self.adapter_settings: Dict[str, Any] = config.get("adapter_settings", {})

        # Runtime settings (can be overridden by CLI flags)
        self.log_level: str = log_level if log_level != "INFO" else config.get("log_level", "INFO")
        self.keep_images: bool = keep_images if keep_images else config.get("keep_images", False)

        # Task retry configuration
        self.max_task_retries: int = config.get("max_task_retries", 3)
        self.initial_retry_delay_seconds: int = config.get("initial_retry_delay_seconds", 30)
        self.max_retry_delay_seconds: int = config.get("max_retry_delay_seconds", 300)

        if dev:
            self.host = "dev.api.citra.space"
            CITRASCOPE_LOGGER.info("Using development API endpoint.")

    def is_configured(self) -> bool:
        """Check if minimum required configuration is present.

        Returns:
            True if personal_access_token, telescope_id, and hardware_adapter are set.
        """
        return bool(self.personal_access_token and self.telescope_id and self.hardware_adapter)

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for serialization.

        Returns:
            Dictionary of all settings.
        """
        return {
            "host": self.host,
            "port": self.port,
            "use_ssl": self.use_ssl,
            "personal_access_token": self.personal_access_token,
            "telescope_id": self.telescope_id,
            "hardware_adapter": self.hardware_adapter,
            "adapter_settings": self.adapter_settings,
            "log_level": self.log_level,
            "keep_images": self.keep_images,
            "max_task_retries": self.max_task_retries,
            "initial_retry_delay_seconds": self.initial_retry_delay_seconds,
            "max_retry_delay_seconds": self.max_retry_delay_seconds,
        }

    def save(self) -> None:
        """Save current settings to JSON config file."""
        self.config_manager.save_config(self.to_dict())
        CITRASCOPE_LOGGER.info(f"Configuration saved to {self.config_manager.get_config_path()}")

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "CitraScopeSettings":
        """Create settings instance from dictionary.

        Args:
            config: Dictionary of configuration values.

        Returns:
            New CitraScopeSettings instance.
        """
        settings = cls()
        settings.host = config.get("host", settings.host)
        settings.port = config.get("port", settings.port)
        settings.use_ssl = config.get("use_ssl", settings.use_ssl)
        settings.personal_access_token = config.get("personal_access_token", "")
        settings.telescope_id = config.get("telescope_id", "")
        settings.hardware_adapter = config.get("hardware_adapter", "indi")
        settings.adapter_settings = config.get("adapter_settings", {})
        settings.log_level = config.get("log_level", "INFO")
        settings.keep_images = config.get("keep_images", False)
        settings.max_task_retries = config.get("max_task_retries", 3)
        settings.initial_retry_delay_seconds = config.get("initial_retry_delay_seconds", 30)
        settings.max_retry_delay_seconds = config.get("max_retry_delay_seconds", 300)
        return settings
