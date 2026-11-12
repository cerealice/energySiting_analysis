"""ERA5-Land (0.1° ≈ 9 km) surface solar radiation and surface pressure, mean of the
last 5 complete years (config.CLIMATE_YEARS) — replaces the 0.25° ERA5 versions.

ERA5-Land is ERA5's land component re-run at 2.5× finer resolution. It has no
100 m wind, cloud cover, boundary layer or CAPE (those stay ERA5) and its
temperature / precipitation are covered by CHELSA, so it supplies radiation
and pressure only.

fetch(): one CDS request (monthly means, Italy box) → data/raw_downloads/era5land/.
run(): average all months, snap to the 1 km grid → era5land_ssrd.tif, era5land_sp.tif.
"""
from __future__ import annotations

import json

import numpy as np

from .. import config

DIR = config.RAW / "era5land"
VARS = {"era5land_ssrd": ("surface_solar_radiation_downwards", "ssrd"),
        "era5land_sp": ("surface_pressure", "sp")}
AREA = [48.0, 6.0, 35.5, 19.0]          # N, W, S, E


def target():
    y = config.CLIMATE_YEARS
    return DIR / f"era5land_monthly_{y[0]}_{y[-1]}.nc"


def request():
    return {"product_type": ["monthly_averaged_reanalysis"],
            "variable": [v[0] for v in VARS.values()],
            "year": [str(y) for y in config.CLIMATE_YEARS],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": ["00:00"], "area": AREA,
            "data_format": "netcdf", "download_format": "unarchived"}


def fetch():
    if target().exists():
        print(f"  ok        {target().relative_to(config.ROOT)}")
        return
    from ._cds import client
    DIR.mkdir(parents=True, exist_ok=True)
    print(f"  ERA5-Land monthly means {config.CLIMATE_YEARS[0]}–{config.CLIMATE_YEARS[-1]} (CDS request)…")
    client().retrieve("reanalysis-era5-land-monthly-means", request(), str(target()))
    (DIR / "request.json").write_text(json.dumps(request(), indent=1))


def ready():
    return target().exists()


def run():
    import xarray as xr
    from ._geo import base, save_var
    from .make_worldtensor import orient, to_grid
    config.ensure_dirs()
    if not ready():
        raise SystemExit("ERA5-Land file missing — run `python -m energysiting.setup.fetch` on a login node")
    b = base()
    ds = xr.open_dataset(target())
    for out, (_, short) in VARS.items():
        da = ds[short]
        latn = next(d for d in da.dims if d.startswith("lat"))
        lonn = next(d for d in da.dims if d.startswith("lon"))
        da = da.mean(dim=[d for d in da.dims if d not in (latn, lonn)], skipna=True)
        arr, lo, la = orient(da.transpose(latn, lonn).values, da[lonn].values, da[latn].values)
        with np.errstate(invalid="ignore"):
            save_var(to_grid(arr[0], lo, la, b), f"{out}.tif", b)


if __name__ == "__main__":
    run()
