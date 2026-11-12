"""CERRA (Copernicus European Regional ReAnalysis, 5.5 km) 100 m wind speed:
interannual variability over the last 5 complete years → cerra_ws100_iav.tif.

The Global Wind Atlas gives the long-term mean wind resource at 250 m (2008–2017);
CERRA adds how much that resource varied from year to year recently
(SD of the annual means 2021–2025), computed from actual 100 m wind *speed*
(not from averaged U/V components as the ERA5 feature was).

fetch() (login node, resumable): one CDS request per month — 100 m wind speed at
00/06/12/18 UTC (≈ 280 MB of GRIB) — reduced immediately to a monthly-mean
array on the CERRA grid and the GRIB deleted; ≈ 5 MB kept per month.
Requests are queued by the CDS, so the first run can take several hours.
run(): annual means → SD across years → inverse-distance regridding (4 nearest
CERRA points) onto the 1 km grid. Also writes cerra_ws100_mean.tif (not in the
model; the Global Wind Atlas mean is used instead).
"""
from __future__ import annotations

import calendar
import json

import numpy as np

from .. import config

DIR = config.RAW / "cerra"
TIMES = ["00:00", "06:00", "12:00", "18:00"]


def month_file(y, m):
    return DIR / f"ws100_{y}{m:02d}.npz"


def request(y, m):
    """CDS request for one month. If the CDS form changes, put the request copied from
    the dataset page ('Show API request') in data/raw_downloads/cerra/request.json,
    with any year/month/day value; they are replaced here."""
    custom = DIR / "request.json"
    days = [f"{d:02d}" for d in range(1, calendar.monthrange(y, m)[1] + 1)]
    r = json.loads(custom.read_text()) if custom.exists() else {
        "variable": ["wind_speed"], "height_level": ["100_m"],
        "data_type": ["reanalysis"], "product_type": ["analysis"],
        "time": TIMES, "data_format": "grib"}
    r.update({"year": [str(y)], "month": [f"{m:02d}"], "day": days})
    return r


def _reduce(grib, out):
    import xarray as xr
    ds = xr.open_dataset(grib, engine="cfgrib", backend_kwargs={"indexpath": ""})
    da = ds[next(iter(ds.data_vars))]
    tdims = [d for d in da.dims if d not in ("y", "x")]
    mean = da.mean(dim=tdims, skipna=True).values.astype("float32")
    np.savez_compressed(out, mean=mean, n=da.sizes.get(tdims[0], 1) if tdims else 1)
    grid = DIR / "grid.npz"
    if not grid.exists():
        np.savez_compressed(grid, lat=ds["latitude"].values.astype("float64"),
                            lon=ds["longitude"].values.astype("float64"))
    ds.close()


def fetch():
    from ._cds import client
    DIR.mkdir(parents=True, exist_ok=True)
    todo = [(y, m) for y in config.CLIMATE_YEARS for m in range(1, 13) if not month_file(y, m).exists()]
    if not todo:
        print(f"  ok        CERRA 100 m wind {config.CLIMATE_YEARS[0]}–{config.CLIMATE_YEARS[-1]} (60 monthly means)")
        return
    c = client()
    print(f"  CERRA: {len(todo)} monthly requests to go (queued at the CDS; resumable)")
    for i, (y, m) in enumerate(todo, 1):
        grib = DIR / f"tmp_{y}{m:02d}.grib"
        c.retrieve("reanalysis-cerra-height-levels", request(y, m), str(grib))
        _reduce(grib, month_file(y, m))
        grib.unlink()
        for f in DIR.glob(f"tmp_{y}{m:02d}.grib*"):
            f.unlink()
        print(f"    [{i}/{len(todo)}] {y}-{m:02d}")


def ready():
    return (DIR / "grid.npz").exists() and all(month_file(y, m).exists()
                                               for y in config.CLIMATE_YEARS for m in range(1, 13))


def regrid(values, lat, lon, b, k=4, max_m=12_000):
    """Inverse-distance weights from the k nearest CERRA points to every 1 km cell."""
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    t = Transformer.from_crs(4326, config.EPSG, always_xy=True)
    lon = np.where(lon > 180, lon - 360, lon)
    x, y = t.transform(lon.ravel(), lat.ravel())
    v = values.ravel()
    ok = np.isfinite(v) & np.isfinite(x) & np.isfinite(y)
    tree = cKDTree(np.column_stack([np.asarray(x)[ok], np.asarray(y)[ok]]))
    inside = np.isfinite(b.band())
    rr, cc = np.nonzero(inside)
    cx, cy = b.grid.xy_of_cells(rr, cc)
    d, i = tree.query(np.column_stack([cx, cy]), k=k, distance_upper_bound=max_m)
    good = np.isfinite(d)
    w = np.where(good, 1.0 / np.maximum(d, 1.0) ** 2, 0.0)
    vals = np.where(good, v[ok][np.minimum(i, ok.sum() - 1)], 0.0)
    with np.errstate(invalid="ignore"):
        est = (w * vals).sum(1) / w.sum(1)
    out = np.full(b.grid.shape, np.nan)
    out[rr, cc] = est
    return out


def run():
    from ._geo import base, save_var
    config.ensure_dirs()
    if not ready():
        raise SystemExit("CERRA monthly means missing — run `python -m energysiting.setup.fetch` "
                         "on a login node (needs CDS credentials)")
    b = base()
    g = np.load(DIR / "grid.npz")
    annual = []
    for y in config.CLIMATE_YEARS:
        months = [np.load(month_file(y, m))["mean"] for m in range(1, 13)]
        w = np.array([calendar.monthrange(y, m)[1] for m in range(1, 13)], float)
        annual.append(np.tensordot(w / w.sum(), np.stack(months), axes=1))
    annual = np.stack(annual)
    save_var(regrid(np.std(annual, axis=0, ddof=1), g["lat"], g["lon"], b), "cerra_ws100_iav.tif", b)
    save_var(regrid(annual.mean(0), g["lat"], g["lon"], b), "cerra_ws100_mean.tif", b)


if __name__ == "__main__":
    run()
