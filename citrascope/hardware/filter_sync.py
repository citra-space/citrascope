"""Filter synchronization utilities for syncing hardware filters to backend API."""


def extract_enabled_filter_names(filter_config: dict) -> list[str]:
    """Extract names of enabled filters from hardware configuration.

    Args:
        filter_config: Dict mapping filter IDs to config dicts with 'name' and 'enabled' keys

    Returns:
        List of filter names where enabled=True
    """
    enabled_names = []
    for filter_id, config in filter_config.items():
        if config.get("enabled", False):
            enabled_names.append(config["name"])
    return enabled_names


def build_spectral_config_from_expanded(expanded_filters: list[dict]) -> tuple[dict, list[str]]:
    """Build discrete spectral_config from API expanded filter response.

    Args:
        expanded_filters: List of filter dicts from /filters/expand API response,
                         each with 'name', 'central_wavelength_nm', 'bandwidth_nm', 'is_known'

    Returns:
        Tuple of (spectral_config dict, list of unknown filter names)
    """
    filter_specs = []
    unknown_filters = []

    for f in expanded_filters:
        filter_specs.append(
            {"name": f["name"], "central_wavelength_nm": f["central_wavelength_nm"], "bandwidth_nm": f["bandwidth_nm"]}
        )
        if not f.get("is_known", True):
            unknown_filters.append(f["name"])

    spectral_config = {"type": "discrete", "filters": filter_specs}

    return spectral_config, unknown_filters


def sync_filters_to_backend(api_client, telescope_id: str, filter_config: dict, logger) -> bool:
    """Sync enabled filters from hardware to backend API.

    Extracts enabled filter names, expands them via filter library API,
    builds spectral_config, and updates telescope record.

    Args:
        api_client: CitraApiClient instance
        telescope_id: UUID string of telescope to update
        filter_config: Hardware filter configuration dict
        logger: Logger instance for output

    Returns:
        True if sync succeeded, False otherwise
    """
    if not filter_config:
        logger.debug("No filter configuration to sync")
        return False

    # Extract enabled filter names
    enabled_filter_names = extract_enabled_filter_names(filter_config)

    if not enabled_filter_names:
        logger.debug("No enabled filters to sync")
        return False

    logger.info(f"Syncing {len(enabled_filter_names)} enabled filters to backend: {enabled_filter_names}")

    # Expand filter names to full spectral specs via API
    expand_response = api_client.expand_filters(enabled_filter_names)
    if not expand_response or "filters" not in expand_response:
        logger.warning("Failed to expand filter names - API returned no data")
        return False

    # Build spectral_config from expanded filters
    expanded_filters = expand_response["filters"]
    spectral_config, unknown_filters = build_spectral_config_from_expanded(expanded_filters)

    if unknown_filters:
        logger.warning(f"Unknown filters (using defaults): {unknown_filters}")

    # Update telescope spectral_config via PATCH
    update_response = api_client.update_telescope_spectral_config(telescope_id, spectral_config)

    if update_response:
        logger.info(f"Successfully synced {len(spectral_config['filters'])} filters to backend")
        return True
    else:
        logger.warning("Failed to update telescope spectral_config on backend")
        return False
