"""Unit tests for MSI science processors."""

import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pandas as pd
import pytest

from citrascope.processors.builtin.photometry_processor import PhotometryProcessor
from citrascope.processors.builtin.plate_solver_processor import PlateSolverProcessor
from citrascope.processors.builtin.satellite_matcher_processor import SatelliteMatcherProcessor
from citrascope.processors.builtin.source_extractor_processor import SourceExtractorProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.plate_solve_timeout = 40
    settings.astrometry_index_path = None
    return settings


@pytest.fixture
def mock_context(tmp_path, mock_settings):
    """Create a mock processing context."""
    image_path = tmp_path / "test_image.fits"
    working_dir = tmp_path / "working"
    working_dir.mkdir(exist_ok=True)

    return ProcessingContext(
        image_path=image_path,
        working_image_path=image_path,
        working_dir=working_dir,
        image_data=None,
        task=Mock(satelliteName="TEST SAT", satelliteId="12345", assigned_filter_name="Clear"),
        telescope_record=None,
        ground_station_record=None,
        settings=mock_settings,
        logger=Mock(),
    )


class TestPlateSolverProcessor:
    """Tests for PlateSolverProcessor."""

    def test_processor_metadata(self):
        """Test processor has correct metadata."""
        processor = PlateSolverProcessor()
        assert processor.name == "plate_solver"
        assert processor.friendly_name == "Plate Solver"
        assert "Astrometry" in processor.description

    @patch("citrascope.processors.builtin.processor_dependencies.check_astrometry")
    def test_astrometry_not_installed(self, mock_check, mock_context):
        """Test processor fails gracefully when Astrometry.net not installed."""
        mock_check.return_value = False

        processor = PlateSolverProcessor()
        result = processor.process(mock_context)

        assert isinstance(result, ProcessorResult)
        assert result.should_upload is True  # Fail-open
        assert result.confidence == 0.0
        assert "not installed" in result.reason

    @patch("citrascope.processors.builtin.processor_dependencies.check_astrometry")
    @patch("citrascope.processors.builtin.plate_solver_processor.PlateSolverProcessor._solve_field")
    @patch("astropy.io.fits.open")
    def test_successful_plate_solve(self, mock_fits_open, mock_solve, mock_check, mock_context, tmp_path):
        """Test successful plate solving."""
        mock_check.return_value = True

        # Mock solve_field to return a .new file
        new_file = tmp_path / "test_image.new"
        mock_solve.return_value = new_file

        # Mock FITS header reading
        mock_hdul = MagicMock()
        mock_header = {
            "CRVAL1": 120.5,
            "CRVAL2": 45.3,
            "CDELT1": 0.001,
        }
        mock_hdul[0].header = mock_header
        mock_fits_open.return_value.__enter__.return_value = mock_hdul

        processor = PlateSolverProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 1.0
        assert result.extracted_data["plate_solved"] is True
        assert result.extracted_data["ra_center"] == 120.5
        assert result.extracted_data["dec_center"] == 45.3
        # Verify working_image_path was updated
        assert mock_context.working_image_path == new_file

    @patch("citrascope.processors.builtin.processor_dependencies.check_astrometry")
    @patch("citrascope.processors.builtin.plate_solver_processor.PlateSolverProcessor._solve_field")
    def test_plate_solve_timeout(self, mock_solve, mock_check, mock_context):
        """Test plate solving timeout handling."""
        mock_check.return_value = True
        mock_solve.side_effect = TimeoutError("Timeout")

        processor = PlateSolverProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True  # Fail-open
        assert result.confidence == 0.0
        assert "timed out" in result.reason


class TestSourceExtractorProcessor:
    """Tests for SourceExtractorProcessor."""

    def test_processor_metadata(self):
        """Test processor has correct metadata."""
        processor = SourceExtractorProcessor()
        assert processor.name == "source_extractor"
        assert processor.friendly_name == "Source Extractor"
        assert "SExtractor" in processor.description

    @patch("astropy.io.fits.open")
    def test_missing_wcs(self, mock_fits_open, mock_context):
        """Test processor fails gracefully when WCS missing."""
        # Mock FITS header without WCS
        mock_hdul = MagicMock()
        mock_hdul[0].header = {}  # No CRVAL1
        mock_fits_open.return_value.__enter__.return_value = mock_hdul

        processor = SourceExtractorProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 0.0
        assert "WCS missing" in result.reason

    @patch("astropy.io.fits.open")
    @patch("citrascope.processors.builtin.processor_dependencies.check_sextractor")
    def test_sextractor_not_installed(self, mock_check, mock_fits_open, mock_context):
        """Test processor fails gracefully when SExtractor not installed."""
        # Mock FITS with WCS
        mock_hdul = MagicMock()
        mock_hdul[0].header = {"CRVAL1": 120.0}
        mock_fits_open.return_value.__enter__.return_value = mock_hdul

        mock_check.return_value = False

        processor = SourceExtractorProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 0.0
        assert "not installed" in result.reason

    @patch("astropy.io.fits.open")
    @patch("citrascope.processors.builtin.processor_dependencies.check_sextractor")
    @patch("citrascope.processors.builtin.source_extractor_processor.SourceExtractorProcessor._extract_sources")
    def test_successful_extraction(self, mock_extract, mock_check, mock_fits_open, mock_context, tmp_path):
        """Test successful source extraction."""
        # Mock FITS with WCS
        mock_hdul = MagicMock()
        mock_hdul[0].header = {"CRVAL1": 120.0}
        mock_fits_open.return_value.__enter__.return_value = mock_hdul

        mock_check.return_value = True

        # Mock source extraction
        sources = pd.DataFrame({"ra": [120.1, 120.2], "dec": [45.1, 45.2], "mag": [10.5, 11.2], "fwhm": [2.0, 2.1]})
        mock_extract.return_value = sources

        processor = SourceExtractorProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 1.0
        assert result.extracted_data["num_sources"] == 2


class TestPhotometryProcessor:
    """Tests for PhotometryProcessor."""

    def test_processor_metadata(self):
        """Test processor has correct metadata."""
        processor = PhotometryProcessor()
        assert processor.name == "photometry"
        assert processor.friendly_name == "Photometry Calibrator"
        assert "APASS" in processor.description

    def test_missing_catalog(self, mock_context):
        """Test processor fails gracefully when catalog missing."""
        processor = PhotometryProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 0.0
        assert "catalog not found" in result.reason

    @patch("citrascope.processors.builtin.photometry_processor.PhotometryProcessor._calibrate_photometry")
    @patch("pandas.read_csv")
    def test_successful_calibration(self, mock_read, mock_calibrate, mock_context, tmp_path):
        """Test successful photometric calibration."""
        # Create mock catalog file (processor expects output.cat in working_dir)
        (mock_context.working_dir / "output.cat").touch()
        mock_context.working_image_path = tmp_path / "test_image.fits"

        # Mock catalog reading
        sources = pd.DataFrame({"ra": [120.1, 120.2], "dec": [45.1, 45.2], "mag": [10.5, 11.2]})
        mock_read.return_value = sources

        # Mock calibration
        mock_calibrate.return_value = (25.3, 15)

        processor = PhotometryProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 1.0
        assert result.extracted_data["zero_point"] == 25.3
        assert result.extracted_data["num_calibration_stars"] == 15


class TestSatelliteMatcherProcessor:
    """Tests for SatelliteMatcherProcessor."""

    def test_processor_metadata(self):
        """Test processor has correct metadata."""
        processor = SatelliteMatcherProcessor()
        assert processor.name == "satellite_matcher"
        assert processor.friendly_name == "Satellite Matcher"
        assert "TLE" in processor.description

    def test_missing_catalog(self, mock_context):
        """Test processor fails gracefully when catalog missing."""
        processor = SatelliteMatcherProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 0.0
        assert "catalog not found" in result.reason

    @patch("citrascope.processors.builtin.processor_dependencies.check_ephemeris")
    def test_missing_ephemeris(self, mock_check, mock_context, tmp_path):
        """Test processor fails gracefully when ephemeris missing."""
        # Create mock catalog file (processor expects output.cat in working_dir)
        (mock_context.working_dir / "output.cat").touch()
        mock_context.working_image_path = tmp_path / "test_image.fits"

        mock_check.return_value = False

        processor = SatelliteMatcherProcessor()
        result = processor.process(mock_context)

        assert result.should_upload is True
        assert result.confidence == 0.0
        assert "Ephemeris" in result.reason


class TestDependencyChecks:
    """Tests for dependency checking utilities."""

    @patch("citrascope.processors.builtin.processor_dependencies.shutil.which")
    def test_check_astrometry(self, mock_which):
        """Test Astrometry.net detection."""
        from citrascope.processors.builtin.processor_dependencies import check_astrometry

        mock_which.return_value = "/usr/bin/solve-field"
        assert check_astrometry() is True

        mock_which.return_value = None
        assert check_astrometry() is False

    @patch("citrascope.processors.builtin.processor_dependencies.shutil.which")
    def test_check_sextractor(self, mock_which):
        """Test SExtractor detection."""
        from citrascope.processors.builtin.processor_dependencies import check_sextractor

        # Test source-extractor command
        mock_which.side_effect = lambda cmd: "/usr/bin/source-extractor" if cmd == "source-extractor" else None
        assert check_sextractor() is True

        # Reset mock and test sex alias
        mock_which.reset_mock()
        mock_which.side_effect = lambda cmd: "/usr/bin/sex" if cmd == "sex" else None
        assert check_sextractor() is True

        # Reset mock and test neither found
        mock_which.reset_mock()
        mock_which.side_effect = lambda cmd: None
        assert check_sextractor() is False
