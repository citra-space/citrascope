"""Hardware adapter registry.

This module provides a centralized registry for all hardware adapters.
To add a new adapter, simply add an entry to the REGISTERED_ADAPTERS dict below.

Each adapter entry should include:
- module: The full module path to import
- class_name: The class name within that module
- description: A human-readable description of the adapter

Third-party adapters can be added by modifying this registry.
"""

import importlib
from typing import Any, Dict, List, Type

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter

# Central registry of all available hardware adapters
REGISTERED_ADAPTERS: Dict[str, Dict[str, str]] = {
    "indi": {
        "module": "citrascope.hardware.indi_adapter",
        "class_name": "IndiAdapter",
        "description": "INDI Protocol - Universal astronomy device control",
    },
    "nina": {
        "module": "citrascope.hardware.nina_adv_http_adapter",
        "class_name": "NinaAdvancedHttpAdapter",
        "description": "N.I.N.A. Advanced HTTP API - Windows-based astronomy imaging",
    },
    "kstars": {
        "module": "citrascope.hardware.kstars_dbus_adapter",
        "class_name": "KStarsDBusAdapter",
        "description": "KStars/Ekos via D-Bus - Linux astronomy suite",
    },
}


def get_adapter_class(adapter_name: str) -> Type[AbstractAstroHardwareAdapter]:
    """Get the adapter class for the given adapter name.

    Args:
        adapter_name: The name of the adapter (e.g., "indi", "nina", "kstars")

    Returns:
        The adapter class

    Raises:
        ValueError: If the adapter name is not registered
        ImportError: If the adapter module cannot be imported (e.g., missing dependencies)
    """
    if adapter_name not in REGISTERED_ADAPTERS:
        available = ", ".join(f"'{name}'" for name in REGISTERED_ADAPTERS.keys())
        raise ValueError(f"Unknown hardware adapter type: '{adapter_name}'. " f"Valid options are: {available}")

    adapter_info = REGISTERED_ADAPTERS[adapter_name]
    module = importlib.import_module(adapter_info["module"])
    adapter_class = getattr(module, adapter_info["class_name"])

    return adapter_class


def list_adapters() -> Dict[str, Dict[str, str]]:
    """Get a dictionary of all registered adapters with their descriptions.

    Returns:
        Dict mapping adapter names to their info (description, module, class_name)
    """
    return {
        name: {
            "description": info["description"],
            "module": info["module"],
            "class_name": info["class_name"],
        }
        for name, info in REGISTERED_ADAPTERS.items()
    }


def get_adapter_schema(adapter_name: str) -> list:
    """Get the configuration schema for a specific adapter.

    Args:
        adapter_name: The name of the adapter

    Returns:
        The adapter's settings schema

    Raises:
        ValueError: If the adapter name is not registered
        ImportError: If the adapter module cannot be imported
    """
    adapter_class = get_adapter_class(adapter_name)
    # Call classmethod directly without instantiation
    return adapter_class.get_settings_schema()
