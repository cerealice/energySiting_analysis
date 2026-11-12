"""Spatial lag of existing development (replaces section 8 of make_variables_italy.R).

lag = share of 1 km cells within 50 km that contained a solar (resp. wind)
tracker plant already operating BEFORE 2017.

Changes from the R version:
* R averaged the presence raster, whose cell values are plant ID numbers, so
  the lag depended on the row order of the GEM spreadsheet. Here plants are 0/1.
* R built it from the same >= 2017 plants the model predicts, so every presence
  partly explained itself. Here only plants that predate the modelled ones are
  used: "is there earlier development nearby?".
RSE Atlante municipal totals have no commissioning date and are not used.
"""
from __future__ import annotations

import json

import numpy as np
from scipy import ndimage

from .. import config, raster

RADIUS_M = 50_000
METHOD = {"method": "pre2017_binary", "radius_m": RADIUS_M}
STATE = config.VAR_PATH / "spatial_lag.json"


def circular_mean(binary, res, radius=RADIUS_M):
    """Mean over a circular window (terra::focalMat(type="circle") weights),
    counting only cells inside the raster."""
    r = int(radius // res)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    w = ((xx ** 2 + yy ** 2) * res ** 2 <= radius ** 2).astype(float)
    num = ndimage.convolve(np.nan_to_num(binary), w, mode="constant", cval=0.0)
    den = ndimage.convolve(np.ones_like(binary, dtype=float), w, mode="constant", cval=0.0)
    return num / den


def up_to_date():
    return STATE.exists() and json.loads(STATE.read_text()) == METHOD and all(
        (config.VAR_PATH / f"{t}_lag.tif").exists() for t in ("solar", "wind"))


def run():
    config.ensure_dirs()
    b = raster.read(config.BASE_RASTER)
    inside = np.isfinite(b.band())
    for tech in ("solar", "wind"):
        src = config.DERIVED / f"{tech}_pre2017.tif"
        if not src.exists():
            raise SystemExit(f"{src.name} missing — re-run the tech step first")
        pre = raster.read(src, cache=False).band().astype(float)
        pre = np.where(np.isfinite(pre), pre, 0.0)
        lag = circular_mean(pre, b.grid.res)
        raster.write(config.VAR_PATH / f"{tech}_lag.tif", np.where(inside, lag, np.nan), b.grid, [f"{tech}_lag"])
        print(f"  saved: {tech}_lag.tif  ({int(pre.sum())} pre-2017 plant cells, "
              f"lag max {np.nanmax(np.where(inside, lag, np.nan)):.3f})")
    STATE.write_text(json.dumps(METHOD))


if __name__ == "__main__":
    run()
