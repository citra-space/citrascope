"""Data classes for image processor input and output."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from citrascope.tasks.task import Task


@dataclass
class ProcessorResult:
    """Result returned by processors."""

    should_upload: bool  # False = skip upload
    extracted_data: dict  # Metrics to attach to upload
    confidence: float  # 0.0-1.0 quality score
    reason: str  # Human-readable explanation
    processing_time_seconds: float  # For metrics
    processor_name: str  # Which processor returned this


@dataclass
class AggregatedResult:
    """Combined results from all processors."""

    should_upload: bool  # AND of all processor results
    extracted_data: dict  # Merged extracted data
    all_results: List[ProcessorResult]  # Individual results
    total_time: float  # Total processing time
    skip_reason: Optional[str]  # Why upload was skipped (if any)


@dataclass
class ProcessingContext:
    """Rich context provided to image processors."""

    # Image data
    image_path: Path  # Original captured image
    working_image_path: Path  # Current working image (processors can update this)
    working_dir: Path  # Task-specific temp directory for intermediate files
    image_data: Optional[np.ndarray]  # Pre-loaded for performance

    # Task context (None for manual captures)
    task: Optional[Task]

    # Observatory context
    telescope_record: Optional[dict]
    ground_station_record: Optional[dict]

    # Settings
    settings: Optional[Any]  # CitraScopeSettings instance

    # Daemon (at runtime: for LocationService, etc.; tests can pass Mock)
    daemon: Optional[Any] = None

    # Logging
    logger: Optional[Any] = None  # Logger instance for debugging
