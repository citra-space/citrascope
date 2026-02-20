"""Image processor framework for CitraScope.

This module provides a framework for processing captured images before upload.
Processors can extract readings, check quality, and decide whether to upload images.
"""

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import (
    AggregatedResult,
    ProcessingContext,
    ProcessorResult,
)
from citrascope.processors.processor_registry import ProcessorRegistry

__all__ = [
    "AbstractImageProcessor",
    "ProcessorResult",
    "ProcessingContext",
    "AggregatedResult",
    "ProcessorRegistry",
]
