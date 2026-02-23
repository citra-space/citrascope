"""Dummy hardware adapter for testing without real hardware."""

import datetime
import logging
import time
from collections.abc import Callable
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import gaussian_filter

from citrascope.hardware.abstract_astro_hardware_adapter import (
    AbstractAstroHardwareAdapter,
    ObservationStrategy,
    SettingSchemaEntry,
)

# Synthetic camera constants — consistent across take_image() and the WCS header
# so the image geometry is self-describing.
_DUMMY_IMG_SIZE = 1024  # pixels per side
_DUMMY_PIXEL_SCALE = 6.0  # arcsec/pixel  →  ~1.7° FOV  (wide enough for Tetra3)
_DUMMY_SKY_BG = 500.0  # ADU sky background
_DUMMY_READ_NOISE = 8.0  # electrons RMS
_DUMMY_GAIN = 1.5  # electrons/ADU
_DUMMY_PSF_SIGMA_PX = 3.0 / 2.3548  # sigma from 3.0 px FWHM seeing
_DUMMY_MAG_LIMIT = 14.0  # faintest catalog star to render (Vmag)
_DUMMY_MAG_ZERO = 20.0  # instrument zero-point: V=10 → SNR~58, V=12 → SNR~9


class DummyAdapter(AbstractAstroHardwareAdapter):
    """
    Dummy hardware adapter that simulates hardware without requiring real devices.

    Perfect for testing, development, and demonstrations. All operations are logged
    and return realistic fake data. Images are synthetic starfields with a proper
    WCS header keyed to the current simulated telescope pointing.
    """

    def __init__(self, logger: logging.Logger, images_dir: Path, **kwargs):
        """Initialize dummy adapter.

        Args:
            logger: Logger instance
            images_dir: Path to images directory
            **kwargs: Additional settings including 'simulate_slow_operations'
        """
        super().__init__(images_dir, **kwargs)
        self.logger = logger
        self.simulate_slow = kwargs.get("simulate_slow_operations", False)
        self.slow_delay = kwargs.get("slow_delay_seconds", 2.0)

        # Fake hardware state
        self._connected = False
        self._telescope_connected = False
        self._camera_connected = False
        self._current_ra = 0.0  # hours (hardware convention)
        self._current_dec = 0.0  # degrees
        self._is_moving = False
        self._tracking_rate = (15.041, 0.0)  # arcsec/sec (sidereal rate)

        # Set by the daemon after connecting, mirrors the real telescope_record from the API.
        # When present, take_image() derives sensor dimensions and pixel scale from it.
        self.telescope_record: dict | None = None

        self.logger.info("DummyAdapter initialized")

    @classmethod
    def get_settings_schema(cls, **kwargs) -> list[SettingSchemaEntry]:
        """Return configuration schema for dummy adapter."""
        return [
            {
                "name": "simulate_slow_operations",
                "friendly_name": "Simulate Slow Operations",
                "type": "bool",
                "default": False,
                "description": "Add artificial delays to simulate slow hardware responses",
                "required": False,
                "group": "Testing",
            },
            {
                "name": "slow_delay_seconds",
                "friendly_name": "Delay Duration (seconds)",
                "type": "float",
                "default": 2.0,
                "min": 0.1,
                "max": 10.0,
                "description": "Duration of artificial delays when slow simulation is enabled",
                "required": False,
                "group": "Testing",
            },
        ]

    def get_observation_strategy(self) -> ObservationStrategy:
        """Dummy adapter uses manual strategy."""
        return ObservationStrategy.MANUAL

    def perform_observation_sequence(self, task, satellite_data) -> str:
        """Not used for manual strategy."""
        raise NotImplementedError("DummyAdapter uses MANUAL strategy")

    def connect(self) -> bool:
        """Simulate connection."""
        self.logger.info("DummyAdapter: Connecting...")
        self._simulate_delay()
        self._connected = True
        self._telescope_connected = True
        self._camera_connected = True
        self.logger.info("DummyAdapter: Connected successfully")
        return True

    def disconnect(self):
        """Simulate disconnection."""
        self.logger.info("DummyAdapter: Disconnecting...")
        self._connected = False
        self._telescope_connected = False
        self._camera_connected = False
        self.logger.info("DummyAdapter: Disconnected")

    def is_telescope_connected(self) -> bool:
        """Check fake telescope connection."""
        return self._telescope_connected

    def is_camera_connected(self) -> bool:
        """Check fake camera connection."""
        return self._camera_connected

    def list_devices(self) -> list[str]:
        """Return list of fake devices."""
        return ["Dummy Telescope", "Dummy Camera", "Dummy Filter Wheel", "Dummy Focuser"]

    def select_telescope(self, device_name: str) -> bool:
        """Simulate telescope selection."""
        self.logger.info(f"DummyAdapter: Selected telescope '{device_name}'")
        self._telescope_connected = True
        return True

    def _do_point_telescope(self, ra: float, dec: float):
        """Simulate telescope slew."""
        self.logger.info(f"DummyAdapter: Slewing to RA={ra:.4f}h, Dec={dec:.4f}°")
        self._is_moving = True
        self._simulate_delay()
        self._current_ra = ra
        self._current_dec = dec
        self._is_moving = False
        self.logger.info("DummyAdapter: Slew complete")

    def get_telescope_direction(self) -> tuple[float, float]:
        """Return current fake telescope position."""
        return (self._current_ra, self._current_dec)

    def telescope_is_moving(self) -> bool:
        """Check if fake telescope is moving."""
        return self._is_moving

    def select_camera(self, device_name: str) -> bool:
        """Simulate camera selection."""
        self.logger.info(f"DummyAdapter: Selected camera '{device_name}'")
        self._camera_connected = True
        return True

    def take_image(self, task_id: str, exposure_duration_seconds=1.0) -> str:
        """Simulate image capture, producing a synthetic starfield FITS."""
        self.logger.info(f"DummyAdapter: Starting {exposure_duration_seconds}s exposure for task {task_id}")
        self._simulate_delay(exposure_duration_seconds)

        timestamp = int(time.time())
        filename = f"dummy_{task_id}_{timestamp}.fits"
        filepath = self.images_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        image_data, wcs = self._generate_starfield(
            self._current_ra,
            self._current_dec,
            exposure_duration_seconds,
            seed=timestamp,
        )

        hdu = fits.PrimaryHDU(image_data, header=wcs.to_header())
        hdu.header["INSTRUME"] = ("DummyCamera", "Simulated camera")
        hdu.header["EXPTIME"] = (exposure_duration_seconds, "Exposure time (seconds)")
        hdu.header["DATE-OBS"] = (
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "UTC start of exposure",
        )
        hdu.header["TASKID"] = task_id
        hdu.writeto(filepath, overwrite=True)

        self.logger.info(f"DummyAdapter: Image saved to {filepath}")
        return str(filepath)

    def _generate_starfield(
        self,
        ra_center_hours: float,
        dec_center: float,
        exptime: float,
        seed: int,
    ) -> tuple[np.ndarray, WCS]:
        """Generate a synthetic starfield from the Tycho-2 catalog with a TAN WCS.

        Queries the Tycho-2 catalog via Vizier for real stars in the current FOV,
        projects them onto the pixel grid, and renders each as a Gaussian PSF.

        Args:
            ra_center_hours: RA of the field centre in hours (hardware convention).
            dec_center:      Dec of the field centre in degrees.
            exptime:         Exposure duration in seconds (scales star brightness).
            seed:            RNG seed for the noise model (use Unix timestamp).

        Returns:
            Tuple of (image array uint16, WCS object).
        """
        rng = np.random.default_rng(seed)
        ra_center = ra_center_hours * 15.0  # hours → degrees for WCS & catalog

        # Derive sensor geometry from telescope_record when available,
        # so the simulated image matches the real instrument's FOV and resolution.
        tr = self.telescope_record
        if (
            tr
            and tr.get("pixelSize")
            and tr.get("focalLength")
            and tr.get("horizontalPixelCount")
            and tr.get("verticalPixelCount")
        ):
            pixel_scale = float(tr["pixelSize"]) / float(tr["focalLength"]) * 206.265
            size_x = int(tr["horizontalPixelCount"])
            size_y = int(tr["verticalPixelCount"])
            self.logger.debug(
                f"DummyAdapter: using telescope sensor {size_x}×{size_y}px " f"@ {pixel_scale:.2f} arcsec/px"
            )
        else:
            pixel_scale = _DUMMY_PIXEL_SCALE
            size_x = size_y = _DUMMY_IMG_SIZE

        fov_deg = max(size_x, size_y) * pixel_scale / 3600.0

        # --- WCS: TAN projection centred on current pointing -----------------
        # Standard TAN (gnomonic) projection.  CDELT1 is in RA-coordinate
        # degrees per pixel; the TAN projection equations already fold in
        # cos(dec) when mapping (RA, Dec) → intermediate world coords, so
        # the on-sky pixel scale is isotropic at the field centre without any
        # additional correction here.
        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [(size_x + 1) / 2.0, (size_y + 1) / 2.0]
        wcs.wcs.cdelt = [-pixel_scale / 3600.0, pixel_scale / 3600.0]
        wcs.wcs.crval = [ra_center, dec_center]
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]

        # --- Star catalog query ----------------------------------------------
        star_ras, star_decs, star_mags = self._fetch_catalog_stars(ra_center, dec_center, fov_deg)

        # --- Sky background + noise ------------------------------------------
        dark_adu = 0.01 * exptime / _DUMMY_GAIN
        image = np.full((size_y, size_x), _DUMMY_SKY_BG + dark_adu, dtype=np.float64)
        sky_electrons = image * _DUMMY_GAIN
        image = rng.poisson(sky_electrons).astype(np.float64) / _DUMMY_GAIN
        image += rng.normal(0.0, _DUMMY_READ_NOISE / _DUMMY_GAIN, image.shape)

        # --- Render each catalog star as a Gaussian PSF ----------------------
        psf_sigma = _DUMMY_PSF_SIGMA_PX
        stamp_r = max(int(5 * psf_sigma), 15)

        pixel_coords = wcs.all_world2pix(np.column_stack([star_ras, star_decs]), 0)

        # Drop any stars whose projection produced NaN (behind tangent plane, etc.)
        valid = np.all(np.isfinite(pixel_coords), axis=1)
        pixel_coords = pixel_coords[valid]
        star_mags = star_mags[valid]

        n_rendered = 0
        for (xp, yp), mag in zip(pixel_coords, star_mags):
            flux_e = 10.0 ** ((_DUMMY_MAG_ZERO - mag) / 2.5) * exptime
            total_adu = flux_e / _DUMMY_GAIN

            xi, yi = int(round(xp)), int(round(yp))

            # Build a small stamp and blur it to the PSF shape
            stamp = np.zeros((2 * stamp_r + 1, 2 * stamp_r + 1))
            stamp[stamp_r, stamp_r] = total_adu
            stamp = gaussian_filter(stamp, sigma=psf_sigma)
            if stamp.sum() > 0:
                stamp *= total_adu / stamp.sum()

            # Blit stamp onto the full image, clipping to chip boundaries.
            # Compute the overlap between the stamp and the image array.
            x0, y0 = xi - stamp_r, yi - stamp_r
            ix0 = max(0, x0)
            iy0 = max(0, y0)
            ix1 = min(size_x, x0 + stamp.shape[1])
            iy1 = min(size_y, y0 + stamp.shape[0])
            sx0 = ix0 - x0
            sy0 = iy0 - y0
            sx1 = sx0 + (ix1 - ix0)
            sy1 = sy0 + (iy1 - iy0)

            if ix1 > ix0 and iy1 > iy0:
                image[iy0:iy1, ix0:ix1] += stamp[sy0:sy1, sx0:sx1]
                n_rendered += 1

        self.logger.debug(f"DummyAdapter: Rendered {n_rendered}/{len(star_mags)} catalog stars")

        image = np.clip(image, 0, 65535).astype(np.uint16)
        return image, wcs

    def _fetch_catalog_stars(
        self,
        ra: float,
        dec: float,
        fov_deg: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Query Tycho-2 via Vizier for stars in the current FOV.

        Raises on failure — we never fall back to random stars because the
        whole point of the DummyAdapter is to produce realistic images.

        Returns:
            Tuple of (ras_deg, decs_deg, mags) as float arrays.
        """
        from astroquery.vizier import Vizier  # type: ignore[import-untyped]

        v = Vizier(columns=["RAmdeg", "DEmdeg", "VTmag"], row_limit=5000)
        result = v.query_region(
            SkyCoord(ra=ra, dec=dec, unit="deg"),
            width=fov_deg * u.deg,
            height=fov_deg * u.deg,
            catalog="I/259/tyc2",
        )
        if not result:
            raise RuntimeError(f"Tycho-2 query returned no results for RA={ra:.3f}, Dec={dec:.3f}, FOV={fov_deg:.2f}°")

        tbl = result[0]
        mask = tbl["VTmag"] < _DUMMY_MAG_LIMIT
        ras = np.array(tbl["RAmdeg"][mask], dtype=float)
        decs = np.array(tbl["DEmdeg"][mask], dtype=float)
        mags = np.array(tbl["VTmag"][mask], dtype=float)

        if len(ras) == 0:
            raise RuntimeError(
                f"No Tycho-2 stars brighter than V={_DUMMY_MAG_LIMIT} " f"around RA={ra:.3f}, Dec={dec:.3f}"
            )

        self.logger.debug(
            f"DummyAdapter: Tycho-2 returned {len(ras)} stars "
            f"(Vmag < {_DUMMY_MAG_LIMIT}) around RA={ra:.3f}, Dec={dec:.3f}"
        )
        return ras, decs, mags

    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        """Simulate setting tracking rate."""
        self.logger.info(f"DummyAdapter: Setting tracking rate RA={ra_rate} arcsec/s, Dec={dec_rate} arcsec/s")
        self._tracking_rate = (ra_rate, dec_rate)

    def get_tracking_rate(self) -> tuple[float, float]:
        """Return current fake tracking rate."""
        return self._tracking_rate

    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        """Simulate plate solving alignment."""
        self.logger.info(f"DummyAdapter: Performing alignment to RA={target_ra}°, Dec={target_dec}°")
        self._simulate_delay()
        # Simulate small correction
        self._current_ra = target_ra + 0.001
        self._current_dec = target_dec + 0.001
        self.logger.info("DummyAdapter: Alignment successful")
        return True

    def supports_autofocus(self) -> bool:
        """Dummy adapter supports autofocus."""
        return True

    def do_autofocus(
        self,
        target_ra: float | None = None,
        target_dec: float | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        """Simulate autofocus routine."""
        if target_ra is not None and target_dec is not None:
            self.logger.info(f"DummyAdapter: Starting autofocus on target RA={target_ra:.4f}, Dec={target_dec:.4f}")
        else:
            self.logger.info("DummyAdapter: Starting autofocus (default target)")

        filters = [f for f in self.filter_map.values() if f.get("enabled", True)] if self.filter_map else []
        total = len(filters) or 1
        for idx, f in enumerate(filters or [{"name": "Default"}], 1):
            if on_progress:
                on_progress(f"Filter {idx}/{total}: {f['name']} — focusing...")
            self._simulate_delay(1.0)
            if on_progress:
                on_progress(f"Filter {idx}/{total}: {f['name']} — done")

        self.logger.info("DummyAdapter: Autofocus complete")

    def supports_filter_management(self) -> bool:
        """Dummy adapter supports filter management."""
        return True

    def supports_direct_camera_control(self) -> bool:
        """Dummy adapter supports direct camera control."""
        return True

    def expose_camera(self, exposure_seconds: float = 1.0) -> str:
        """Simulate manual camera exposure."""
        return self.take_image("manual_test", exposure_seconds)

    def _simulate_delay(self, override_delay: float | None = None):
        """Add artificial delay if slow simulation is enabled."""
        if self.simulate_slow:
            delay = override_delay if override_delay is not None else self.slow_delay
            time.sleep(delay)
