"""Covariate extraction at presence / absence zones — zonal.R.

* Absence zones: each buffered point is burned into the base grid using the
  fasterize rule (cells whose centre falls inside the circle; later ids
  overwrite earlier ones).
* Presence zones: the <tech>_hull_existing.tif raster (cell value = plant id).
* For every zone, the mean of each of the stack layers (108 shared, or R's 102, + env/cf/lag),
  NA-ignoring — raster::zonal(fun = "mean", na.rm = TRUE).

Output: derived/py/bg_cov_<tech>.csv and existing_cov_<tech>.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, raster
from .common import load_stacks, log


def burn_circles(ab: pd.DataFrame, grid) -> np.ndarray:
    z = np.full(grid.shape, np.nan, dtype=np.float64)
    xs, ys = grid.centres()
    for zid, x, y, r in ab[["id", "x", "y", "radius_m"]].itertuples(index=False):
        c0 = max(0, int(np.floor((x - r - grid.x0) / grid.res)))
        c1 = min(grid.ncol - 1, int(np.floor((x + r - grid.x0) / grid.res)))
        r0 = max(0, int(np.floor((grid.y0 - (y + r)) / grid.res)))
        r1 = min(grid.nrow - 1, int(np.floor((grid.y0 - (y - r)) / grid.res)))
        if c1 < c0 or r1 < r0:
            continue
        dx = xs[c0:c1 + 1][None, :] - x
        dy = ys[r0:r1 + 1][:, None] - y
        inside = dx * dx + dy * dy <= r * r
        sub = z[r0:r1 + 1, c0:c1 + 1]
        sub[inside] = zid
    return z


def zonal_mean(stack: np.ndarray, names, zones: np.ndarray) -> pd.DataFrame:
    ok = np.isfinite(zones)
    zid = zones[ok].astype(np.int64)
    uz, inv = np.unique(zid, return_inverse=True)
    out = {"zone": uz}
    for i, n in enumerate(names):
        v = stack[i][ok].astype(np.float64)
        fin = np.isfinite(v)
        s = np.bincount(inv[fin], weights=v[fin], minlength=len(uz))
        c = np.bincount(inv[fin], minlength=len(uz))
        with np.errstate(invalid="ignore", divide="ignore"):
            out[n] = np.where(c > 0, s / c, np.nan)
    return pd.DataFrame(out)


def run():
    config.ensure_dirs()
    cov, fut, tech_stacks = load_stacks()
    base = raster.read(config.BASE_RASTER)
    for tech in config.TECHS:
        iv = np.concatenate([cov.data, tech_stacks[tech].data], axis=0)
        names = cov.names + config.TECH_LAYERS
        ab = pd.read_csv(config.OUT / f"absence_{tech}.csv")
        zones_ab = burn_circles(ab, base.grid)
        zones_ex = raster.read(config.DERIVED / f"{tech}_hull_existing.tif").band()
        bg = zonal_mean(iv, names, zones_ab).assign(treat=0)
        ex = zonal_mean(iv, names, zones_ex).assign(treat=1)
        bg.to_csv(config.OUT / f"bg_cov_{tech}.csv", index=False)
        ex.to_csv(config.OUT / f"existing_cov_{tech}.csv", index=False)
        log(f"{tech}: {len(bg)} absence zones (of {len(ab)} points), {len(ex)} presence zones")


if __name__ == "__main__":
    run()
