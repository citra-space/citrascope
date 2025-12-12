"""Configuration file manager for CitraScope.

Handles reading and writing JSON configuration files using platformdirs
for cross-platform config directory management.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import platformdirs


class ConfigManager:
    """Manages configuration file storage and retrieval."""

    def __init__(self):
        """Initialize the config manager with the standard config directory."""
        self.config_dir = Path(platformdirs.user_config_dir("citrascope", appauthor="citra-space"))
        self.config_file = self.config_dir / "config.json"

    def ensure_config_directory(self) -> None:
        """Create config directory with proper permissions if it doesn't exist."""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, mode=0o700)
        else:
            # Ensure proper permissions on existing directory
            os.chmod(self.config_dir, 0o700)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file.

        Returns:
            Dict containing configuration, or empty dict if file doesn't exist.
        """
        if not self.config_file.exists():
            return {}

        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            # Log error but return empty config to allow recovery
            print(f"Error loading config file: {e}")
            return {}

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to JSON file with proper permissions.

        Args:
            config: Dictionary of configuration values to save.
        """
        self.ensure_config_directory()

        # Write to temp file first, then atomic rename
        temp_file = self.config_file.with_suffix(".json.tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(config, f, indent=2)
            # Set restrictive permissions before moving into place
            os.chmod(temp_file, 0o600)
            temp_file.rename(self.config_file)
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            raise IOError(f"Failed to save config: {e}")

    def get_config_path(self) -> Path:
        """Get the path to the config file.

        Returns:
            Path object pointing to the config file location.
        """
        return self.config_file

    def config_exists(self) -> bool:
        """Check if a config file exists.

        Returns:
            True if config file exists, False otherwise.
        """
        return self.config_file.exists()

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate configuration structure.

        Args:
            config: Configuration dictionary to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # Basic validation - check that it's a dict
        if not isinstance(config, dict):
            return False, "Configuration must be a dictionary"

        # Could add more validation here for required fields, types, etc.
        return True, None
