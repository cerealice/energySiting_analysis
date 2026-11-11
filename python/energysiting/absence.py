"""Pseudo-absence sampling by Italian NUTS-2 region — absence.R.

For each technology:
  1. eligible area = suitability mask minus the 500 m-buffered existing plants;
  2. absence counts per NUTS-2 region ∝ presence counts (regions with no
     presences still get 10 points);
  3. 10 independent draws (seeds 1..10) of cell centres without replacement;
  4. each absence gets a buffer radius resampled from the presence radii.

Region membership is read from the nuts2_<id>.tif indicator rasters (same
1 km grid), which is equivalent to R's crop+mask by region polygon.
Output: derived/py/absence_<tech>.csv  (id, x, y, radius_m, iteration, nuts2)
        derived/py/<tech>_absence_roi.tif
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, raster
from .common import log


def random_pts(roi, region_idx, grid, locations: pd.DataFrame, seeds=range(1, 11)):
    n_pts = len(locations)
    props = locations["state_code"].value_counts()
    counts = {}
    for name, n in props.items():
        counts[config.NUTS2_BY_NAME.get(name, name)] = int(np.round(n / props.sum() * n_pts))
    for rid in config.NUTS2_IDS:                      # regions with no projects → 10
        counts.setdefault(rid, 10)

    radii = locations["radius_m"].to_numpy(float)
    total = sum(counts.values())
    radii = np.append(radii, np.repeat(radii.mean(), max(0, total - len(radii))))

    region_cells = {}
    for rid in counts:
        k = config.NUTS2_IDS.index(rid)
        region_cells[rid] = np.flatnonzero(((roi == 1) & (region_idx == k)).ravel())

    rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for rid, n in counts.items():
            cells = region_cells[rid]
            n = min(n, len(cells))
            if n == 0:
                continue
            pick = rng.choice(cells, size=n, replace=False)
            r, c = np.unravel_index(pick, roi.shape)
            x, y = grid.xy_of_cells(r, c)
            rows.append(pd.DataFrame({"x": x, "y": y, "iteration": seed, "nuts2": rid}))
    ab = pd.concat(rows, ignore_index=True)
    ab.insert(0, "id", np.arange(1, len(ab) + 1))
    rng = np.random.default_rng(config.SEED)
    ab["radius_m"] = rng.choice(radii, size=len(ab), replace=True)
    return ab


def run():
    config.ensure_dirs()
    base = raster.read(config.BASE_RASTER)
    region_idx = raster.nuts2_index()
    for tech in config.TECHS:
        mask = raster.read(config.DERIVED / f"{tech}_hull_existing_mask.tif").band()
        loc = pd.read_csv(config.DERIVED / f"{tech}_hull_existing.csv")
        suit_path = config.MASK_PATH / f"{tech}_suitability_SL1.tif"
        if suit_path.exists():
            suit = raster.read(suit_path).band()
        else:
            log(f"WARNING: {suit_path.name} not found — using base raster as placeholder")
            suit = base.band()
        roi = np.where(np.isfinite(mask), np.nan, suit)       # mask(..., inverse = TRUE)
        raster.write(config.OUT / f"{tech}_absence_roi.tif", roi, base.grid, ["layer"])
        ab = random_pts(roi, region_idx, base.grid, loc)
        ab.to_csv(config.OUT / f"absence_{tech}.csv", index=False)
        log(f"{tech}: {len(loc)} presences → {len(ab)} pseudo-absences "
            f"({ab.iteration.nunique()} iterations)")


if __name__ == "__main__":
    run()
