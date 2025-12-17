"""CitraScope settings class using JSON-based configuration."""

from pathlib import Path
from typing import Any, Dict, Optional

import platformdirs

# Application constants for platformdirs
# Defined before imports to avoid circular dependency
APP_NAME = "citrascope"
APP_AUTHOR = "citra-space"

from citrascope.constants import DEFAULT_API_PORT, DEFAULT_WEB_PORT, PROD_API_HOST
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings.settings_file_manager import SettingsFileManager


class CitraScopeSettings:
    """Settings for CitraScope loaded from JSON configuration file."""

    def __init__(self, web_port: int = DEFAULT_WEB_PORT):
        """Initialize settings from JSON config file.

        Args:
            web_port: Port for web interface (default: 24872) - bootstrap option only
        """
        self.config_manager = SettingsFileManager()

        # Load configuration from file
        config = self.config_manager.load_config()

        # Application data directories
        self._images_dir = Path(platformdirs.user_data_dir(APP_NAME, appauthor=APP_AUTHOR)) / "images"

        # API Settings (all loaded from config file)
        self.host: str = config.get("host", PROD_API_HOST)
        self.port: int = config.get("port", DEFAULT_API_PORT)
        self.use_ssl: bool = config.get("use_ssl", True)
        self.personal_access_token: str = config.get("personal_access_token", "")
        self.telescope_id: str = config.get("telescope_id", "")

        # Hardware adapter selection
        self.hardware_adapter: str = config.get("hardware_adapter", "")

        # Hardware adapter-specific settings stored as dict
        self.adapter_settings: Dict[str, Any] = config.get("adapter_settings", {})

        # Runtime settings (all loaded from config file, configurable via web UI)
        self.log_level: str = config.get("log_level", "INFO")
        self.keep_images: bool = config.get("keep_images", False)

        # Web port: CLI override if non-default, otherwise use config file
        self.web_port: int = web_port if web_port != DEFAULT_WEB_PORT else config.get("web_port", DEFAULT_WEB_PORT)

        # Task retry configuration
        self.max_task_retries: int = config.get("max_task_retries", 3)
        self.initial_retry_delay_seconds: int = config.get("initial_retry_delay_seconds", 30)
        self.max_retry_delay_seconds: int = config.get("max_retry_delay_seconds", 300)

        # Log file configuration
        self.file_logging_enabled: bool = config.get("file_logging_enabled", True)
        self.log_retention_days: int = config.get("log_retention_days", 30)

    def get_images_dir(self) -> Path:
        """Get the path to the images directory.

        Returns:
            Path object pointing to the images directory.
        """
        return self._images_dir

    def ensure_images_directory(self) -> None:
        """Create images directory if it doesn't exist."""
        if not self._images_dir.exists():
            self._images_dir.mkdir(parents=True)

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
            "web_port": self.web_port,
            "max_task_retries": self.max_task_retries,
            "initial_retry_delay_seconds": self.initial_retry_delay_seconds,
            "max_retry_delay_seconds": self.max_retry_delay_seconds,
            "file_logging_enabled": self.file_logging_enabled,
            "log_retention_days": self.log_retention_days,
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
        settings.hardware_adapter = config.get("hardware_adapter", "")
        settings.adapter_settings = config.get("adapter_settings", {})
        settings.log_level = config.get("log_level", "INFO")
        settings.keep_images = config.get("keep_images", False)
        settings.web_port = config.get("web_port", DEFAULT_WEB_PORT)
        settings.max_task_retries = config.get("max_task_retries", 3)
        settings.initial_retry_delay_seconds = config.get("initial_retry_delay_seconds", 30)
        settings.max_retry_delay_seconds = config.get("max_retry_delay_seconds", 300)
        settings.file_logging_enabled = config.get("file_logging_enabled", True)
        settings.log_retention_days = config.get("log_retention_days", 30)
        return settings
