"""SExtractor auto-tuning: score parameter combinations against debug bundles.

Runs SExtractor with many different (detect_thresh, detect_minarea, filter_name)
combinations against retained debug bundles and scores each one by:
  - Whether the target satellite was detected (binary, highest weight)
  - How many APASS catalog stars cross-match (photometric depth)
  - Source quality: fraction with plausible FWHM and low elongation

Usage (CLI)::

    uv run python -m citrascope.autotune /path/to/processing/ --num-bundles 5

Usage (library)::

    from citrascope.autotune import autotune_extraction, score_extraction
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import numpy as np
import pandas as pd
from astropy.io import fits

from citrascope.processors.builtin.source_extractor_processor import SourceExtractorProcessor
from citrascope.settings.citrascope_settings import CitraScopeSettings

logger = logging.getLogger("citrascope.Autotune")

SEXTRACTOR_CONFIG_DIR = Path(__file__).parent / "processors" / "builtin" / "sextractor_configs"

PARAM_GRID: dict[str, list] = {
    "detect_thresh": [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0],
    "detect_minarea": [2, 3, 5, 7, 10],
    "filter_name": ["default", "gauss_2.5_5x5", "tophat_3.0_3x3"],
}

W_SATELLITE = 0.5
W_PHOTOMETRIC = 0.3
W_QUALITY = 0.2


@dataclass
class ExtractionScore:
    """Result of scoring one SExtractor parameter combination."""

    detect_thresh: float
    detect_minarea: int
    filter_name: str
    num_sources: int = 0
    satellite_detected: bool = False
    num_calibration_stars: int = 0
    source_quality_ratio: float = 0.0
    score: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "detect_thresh": self.detect_thresh,
            "detect_minarea": self.detect_minarea,
            "filter_name": self.filter_name,
            "num_sources": self.num_sources,
            "satellite_detected": self.satellite_detected,
            "num_calibration_stars": self.num_calibration_stars,
            "source_quality_ratio": round(self.source_quality_ratio, 3),
            "score": round(self.score, 4),
            "error": self.error,
        }


@dataclass
class _BundleContext:
    """Pre-loaded data from a debug bundle needed for scoring."""

    image_path: Path
    working_dir: Path
    predicted_ra: float | None = None
    predicted_dec: float | None = None
    apass_catalog: pd.DataFrame | None = None


def _angular_distance_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    ra1_r, ra2_r = math.radians(ra1), math.radians(ra2)
    dec1_r, dec2_r = math.radians(dec1), math.radians(dec2)
    cos_d = math.sin(dec1_r) * math.sin(dec2_r) + math.cos(dec1_r) * math.cos(dec2_r) * math.cos(ra1_r - ra2_r)
    cos_d = max(-1.0, min(1.0, cos_d))
    return math.degrees(math.acos(cos_d))


def _load_bundle_context(debug_dir: Path) -> _BundleContext | None:
    """Extract the minimal data needed to score SExtractor configs from a bundle."""
    fits_files = sorted(debug_dir.glob("*.fits"))
    originals = [f for f in fits_files if f.name.startswith("original_")]
    calibrated = [f for f in fits_files if f.name == "calibrated.fits"]
    wcs_files = [f for f in fits_files if f.name.endswith("_wcs.fits")]

    image_path = None
    if wcs_files:
        image_path = wcs_files[0]
    elif calibrated:
        image_path = calibrated[0]
    elif originals:
        image_path = originals[0]
    elif fits_files:
        image_path = fits_files[0]

    if not image_path:
        return None

    try:
        with fits.open(image_path) as hdul:
            primary = hdul[0]
            assert isinstance(primary, fits.PrimaryHDU)
            if "CRVAL1" not in primary.header:
                return None
    except Exception:
        return None

    ctx = _BundleContext(image_path=image_path, working_dir=debug_dir)

    sat_debug_path = debug_dir / "satellite_matcher_debug.json"
    if sat_debug_path.exists():
        try:
            sat_debug = json.loads(sat_debug_path.read_text())
            preds = sat_debug.get("predictions_in_field", [])
            task_path = debug_dir / "task.json"
            target_sat_id = None
            if task_path.exists():
                task_data = json.loads(task_path.read_text())
                target_sat_id = task_data.get("satelliteId", "")
                if target_sat_id:
                    target_sat_id = str(target_sat_id).replace("sat-", "")

            if target_sat_id:
                for pred in preds:
                    if str(pred.get("satellite_id", "")) == target_sat_id:
                        ctx.predicted_ra = pred.get("predicted_ra_deg")
                        ctx.predicted_dec = pred.get("predicted_dec_deg")
                        break
            if ctx.predicted_ra is None and preds:
                ctx.predicted_ra = preds[0].get("predicted_ra_deg")
                ctx.predicted_dec = preds[0].get("predicted_dec_deg")
        except Exception:
            pass

    apass_path = debug_dir / "photometry_apass_catalog.csv"
    if apass_path.exists():
        try:
            ctx.apass_catalog = pd.read_csv(apass_path)
        except Exception:
            pass

    return ctx


def score_extraction(
    bundle: _BundleContext,
    detect_thresh: float,
    detect_minarea: int,
    filter_name: str,
) -> ExtractionScore:
    """Score a single SExtractor parameter combination against a bundle.

    Runs SExtractor, then evaluates:
    1. Satellite detection (nearest source within 1' of predicted position)
    2. APASS cross-match count (photometric depth)
    3. Source quality ratio (plausible FWHM + low elongation)
    """
    result = ExtractionScore(
        detect_thresh=detect_thresh,
        detect_minarea=detect_minarea,
        filter_name=filter_name,
    )

    extractor = SourceExtractorProcessor()
    try:
        sources = extractor._extract_sources(
            image_path=bundle.image_path,
            config_dir=SEXTRACTOR_CONFIG_DIR,
            working_dir=bundle.working_dir,
            detect_thresh=detect_thresh,
            detect_minarea=detect_minarea,
            filter_name=filter_name if filter_name != "default" else None,
        )
    except Exception as exc:
        result.error = str(exc)
        return result

    result.num_sources = len(sources)
    if result.num_sources == 0:
        return result

    # 1. Satellite detection
    if bundle.predicted_ra is not None and bundle.predicted_dec is not None:
        min_dist = float("inf")
        for _, row in sources.iterrows():
            dist = _angular_distance_deg(
                float(row["ra"]),  # type: ignore[arg-type]
                float(row["dec"]),  # type: ignore[arg-type]
                bundle.predicted_ra,
                bundle.predicted_dec,
            )
            min_dist = min(min_dist, dist)
        result.satellite_detected = min_dist < (1.0 / 60.0)

    # 2. APASS cross-match
    if bundle.apass_catalog is not None and len(bundle.apass_catalog) > 0:
        match_radius_deg = 5.0 / 3600.0
        matched = 0
        apass = bundle.apass_catalog
        if "RAJ2000" in apass.columns and "DEJ2000" in apass.columns:
            for _, star in apass.iterrows():
                for _, src in sources.iterrows():
                    dist = _angular_distance_deg(
                        float(src["ra"]),  # type: ignore[arg-type]
                        float(src["dec"]),  # type: ignore[arg-type]
                        float(star["RAJ2000"]),  # type: ignore[arg-type]
                        float(star["DEJ2000"]),  # type: ignore[arg-type]
                    )
                    if dist < match_radius_deg:
                        matched += 1
                        break
        result.num_calibration_stars = matched

    # 3. Source quality
    if "fwhm" in sources.columns and "elongation" in sources.columns:
        fwhm = sources["fwhm"]
        median_fwhm = fwhm.median()
        good_mask = (fwhm > 0) & (fwhm < 2 * median_fwhm) & (sources["elongation"] < 3.0)
        result.source_quality_ratio = float(good_mask.sum()) / len(sources)

    # Composite score
    sat_score = 1.0 if result.satellite_detected else 0.0
    depth_score = min(1.0, result.num_calibration_stars / 20.0) if result.num_calibration_stars > 0 else 0.0
    result.score = W_SATELLITE * sat_score + W_PHOTOMETRIC * depth_score + W_QUALITY * result.source_quality_ratio

    return result


def autotune_extraction(
    debug_dirs: list[Path],
    settings: CitraScopeSettings | None = None,
    log: logging.Logger | None = None,
    grid: dict | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Sweep SExtractor parameters across debug bundles and return ranked results.

    Args:
        debug_dirs: Paths to debug bundle directories.
        settings: Not currently used but reserved for future grid derivation.
        log: Logger.
        grid: Parameter grid override.  Defaults to ``PARAM_GRID``.
        on_progress: Called with ``(completed_combos, total_combos)``.

    Returns:
        List of averaged ``ExtractionScore.to_dict()`` dicts, sorted best-first.
    """
    log = log or logger
    grid = grid or PARAM_GRID

    thresholds = grid.get("detect_thresh", PARAM_GRID["detect_thresh"])
    minareas = grid.get("detect_minarea", PARAM_GRID["detect_minarea"])
    filters = grid.get("filter_name", PARAM_GRID["filter_name"])

    combos = [(t, m, f) for t in thresholds for m in minareas for f in filters]
    total = len(combos) * len(debug_dirs)

    log.info("Auto-tune: %d combos × %d bundles = %d evaluations", len(combos), len(debug_dirs), total)

    bundles: list[_BundleContext] = []
    for d in debug_dirs:
        ctx = _load_bundle_context(d)
        if ctx:
            bundles.append(ctx)
        else:
            log.warning("Skipping %s: could not load bundle context", d.name)

    if not bundles:
        log.error("No valid bundles to tune against")
        return []

    scores_by_combo: dict[tuple, list[ExtractionScore]] = {c: [] for c in combos}
    done = 0

    for combo in combos:
        thresh, minarea, fname = combo
        for bundle in bundles:
            s = score_extraction(bundle, thresh, minarea, fname)
            scores_by_combo[combo].append(s)
            done += 1
            if on_progress:
                on_progress(done, total)

    averaged: list[dict] = []
    for combo, scores in scores_by_combo.items():
        valid = [s for s in scores if s.error is None]
        if not valid:
            continue
        avg: dict[str, Any] = {
            "detect_thresh": combo[0],
            "detect_minarea": combo[1],
            "filter_name": combo[2],
            "avg_score": round(np.mean([s.score for s in valid]), 4),
            "avg_sources": round(np.mean([s.num_sources for s in valid]), 1),
            "satellite_detection_rate": round(sum(1 for s in valid if s.satellite_detected) / len(valid), 3),
            "avg_calibration_stars": round(np.mean([s.num_calibration_stars for s in valid]), 1),
            "avg_quality_ratio": round(np.mean([s.source_quality_ratio for s in valid]), 3),
            "bundles_evaluated": len(valid),
        }
        averaged.append(avg)

    averaged.sort(key=lambda x: x["avg_score"], reverse=True)
    return averaged


def _discover_bundles(base_dir: Path, max_bundles: int = 10) -> list[Path]:
    """Find debug bundle directories under *base_dir*."""
    bundles = []
    for d in sorted(base_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir() and (d / "task.json").exists():
            bundles.append(d)
            if len(bundles) >= max_bundles:
                break
    return bundles


@click.command()
@click.argument("processing_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--num-bundles", default=5, help="Max bundles to evaluate against.")
@click.option("--apply", "apply_settings", is_flag=True, help="Write best settings to config.json.")
@click.option("--top", default=10, help="Number of top results to display.")
def cli(processing_dir: Path, num_bundles: int, apply_settings: bool, top: int) -> None:
    """Auto-tune SExtractor parameters against retained debug bundles."""
    log = logging.getLogger("citrascope.Autotune")
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s"))
        log.addHandler(handler)

    bundles = _discover_bundles(processing_dir, max_bundles=num_bundles)
    if not bundles:
        click.echo("No debug bundles found with task.json")
        return

    click.echo(f"Found {len(bundles)} bundle(s). Running parameter sweep...")
    start = time.time()

    def _progress(done: int, total: int) -> None:
        if done % 10 == 0 or done == total:
            click.echo(f"  [{done}/{total}]")

    results = autotune_extraction(bundles, log=log, on_progress=_progress)
    elapsed = time.time() - start

    click.echo()
    click.echo(f"Completed in {elapsed:.1f}s. Top {min(top, len(results))} configs:")
    click.echo()
    hdr = (
        f"{'Rank':<5} {'Score':<8} {'Thresh':<8} {'MinArea':<9} {'Filter':<18}"
        f" {'Sources':<9} {'SatDet%':<9} {'CalStars':<10} {'Quality':<9}"
    )
    click.echo(hdr)
    click.echo("-" * 95)
    for i, r in enumerate(results[:top]):
        click.echo(
            f"{i + 1:<5} {r['avg_score']:<8.4f} {r['detect_thresh']:<8} {r['detect_minarea']:<9} "
            f"{r['filter_name']:<18} {r['avg_sources']:<9.1f} "
            f"{r['satellite_detection_rate'] * 100:<9.1f} "
            f"{r['avg_calibration_stars']:<10.1f} {r['avg_quality_ratio']:<9.3f}"
        )

    if apply_settings and results:
        best = results[0]
        settings = CitraScopeSettings.load()
        settings.sextractor_detect_thresh = best["detect_thresh"]
        settings.sextractor_detect_minarea = best["detect_minarea"]
        settings.sextractor_filter_name = best["filter_name"]
        settings.save()
        click.echo()
        click.echo(
            f"Applied best config: thresh={best['detect_thresh']}, "
            f"minarea={best['detect_minarea']}, filter={best['filter_name']}"
        )


if __name__ == "__main__":
    cli()
