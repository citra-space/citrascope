"""Source extraction processor using SExtractor."""

import logging
import shutil
import subprocess
import time
from pathlib import Path

import pandas as pd
from astropy.io import fits

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult

from .processor_dependencies import check_sextractor


class SourceExtractorProcessor(AbstractImageProcessor):
    """
    Source extraction processor using SExtractor.

    Detects all sources (stars and satellites) in the image and extracts
    their positions, magnitudes, and FWHM. Requires plate-solved image with WCS.

    Typical processing time: 2-5 seconds.
    """

    name = "source_extractor"
    friendly_name = "Source Extractor"
    description = "Detect stars and satellites via SExtractor (requires plate-solved image)"

    def _parse_sex_catalog(self, catalog_path: Path) -> pd.DataFrame:
        """Parse SExtractor catalog into DataFrame.

        Based on generate_obs.py lines 29-37, the catalog columns are:
        - Column 4: MAG_AUTO (magnitude)
        - Column 5: MAGERR_AUTO (magnitude error)
        - Column 8: ALPHA_J2000 (RA)
        - Column 9: DELTA_J2000 (Dec)
        - Column 10: FWHM_IMAGE (FWHM in pixels)

        Args:
            catalog_path: Path to SExtractor catalog file

        Returns:
            DataFrame with columns: ra, dec, mag, magerr, fwhm
        """
        sources = []

        with open(catalog_path, "r") as f:
            for line in f:
                # Skip comment lines
                if line.startswith("#"):
                    continue

                cols = line.split()
                if len(cols) < 11:
                    continue

                try:
                    sources.append(
                        {
                            "ra": float(cols[8]),  # ALPHA_J2000
                            "dec": float(cols[9]),  # DELTA_J2000
                            "mag": float(cols[4]),  # MAG_AUTO
                            "magerr": float(cols[5]),  # MAGERR_AUTO
                            "fwhm": float(cols[10]),  # FWHM_IMAGE
                        }
                    )
                except (ValueError, IndexError):
                    # Skip malformed lines
                    continue

        return pd.DataFrame(sources)

    def _extract_sources(self, image_path: Path, config_dir: Path, working_dir: Path) -> pd.DataFrame:
        """Run SExtractor and parse catalog.

        Args:
            image_path: Path to FITS image (should be plate-solved with WCS)
            config_dir: Path to directory containing SExtractor config files
            working_dir: Directory for temporary files (catalog will be written here)

        Returns:
            DataFrame with columns: ra, dec, mag, magerr, fwhm

        Raises:
            RuntimeError: If SExtractor fails
        """
        # Ensure paths are absolute
        image_path = image_path.resolve()
        config_dir = config_dir.resolve()
        working_dir = working_dir.resolve()

        # Create a symlink in working_dir with a simple name (no spaces in path)
        image_symlink = working_dir / "input.fits"
        catalog_name = "output.cat"
        catalog_path = working_dir / catalog_name

        try:
            # Create symlink to avoid passing image path with spaces to SExtractor
            if image_symlink.exists():
                image_symlink.unlink()
            image_symlink.symlink_to(image_path)

            # Copy config files to working_dir so relative paths work
            for config_file in ["default.sex", "default.param", "default.conv", "default.nnw"]:
                src = config_dir / config_file
                dst = working_dir / config_file
                if not dst.exists():
                    shutil.copy(src, dst)

            # Build SExtractor command - all files in working_dir now
            cmd = [
                "sex",
                "input.fits",  # Symlink in working_dir
                "-c",
                "default.sex",  # Local copy in working_dir
                "-CATALOG_NAME",
                "output.cat",  # Output in working_dir
            ]

            # Debug logging to diagnose path issues
            logger = logging.getLogger("citrascope")
            logger.info(f"Running SExtractor from cwd: {working_dir}")
            logger.info(f"Config files copied to working_dir (default.sex, default.param, default.conv, default.nnw)")
            logger.info(f"SExtractor command: {' '.join(cmd)}")
            logger.info(f"Image symlink: {image_symlink} -> {image_path}")
            logger.info(f"Catalog path: {catalog_path}")

            # Try 'sex' command first (most common)
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(working_dir))

                # If sex not found, try 'source-extractor' alias
                if result.returncode == 127 or "not found" in (result.stderr or "").lower():
                    cmd[0] = "source-extractor"
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(working_dir))
            except FileNotFoundError:
                # Command doesn't exist, try alternate name
                cmd[0] = "source-extractor"
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(working_dir))
                except FileNotFoundError:
                    raise RuntimeError("SExtractor not found. Install with: brew install sextractor")

            if result.returncode != 0:
                raise RuntimeError(f"SExtractor failed: {result.stderr}")

        finally:
            # Clean up symlink
            if image_symlink.exists():
                image_symlink.unlink()

        # Parse catalog
        sources = self._parse_sex_catalog(catalog_path)
        return sources

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with source extraction.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with source extraction outcome
        """
        start_time = time.time()

        # Check if image has WCS (requires plate solver to have run)
        try:
            with fits.open(context.working_image_path) as hdul:
                if "CRVAL1" not in hdul[0].header:
                    return ProcessorResult(
                        should_upload=True,
                        extracted_data={},
                        confidence=0.0,
                        reason="Image not plate-solved (WCS missing)",
                        processing_time_seconds=time.time() - start_time,
                        processor_name=self.name,
                    )
        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Could not read image: {e}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        # Check dependencies
        if not check_sextractor():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="SExtractor not installed",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            config_dir = Path(__file__).parent / "sextractor_configs"
            sources_df = self._extract_sources(context.working_image_path, config_dir, context.working_dir)

            elapsed = time.time() - start_time

            return ProcessorResult(
                should_upload=True,
                extracted_data={
                    "num_sources": len(sources_df),
                    "sources_catalog": str(context.working_dir / f"{context.working_image_path.stem}.cat"),
                },
                confidence=1.0,
                reason=f"Extracted {len(sources_df)} sources in {elapsed:.1f}s",
                processing_time_seconds=elapsed,
                processor_name=self.name,
            )

        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Source extraction failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
