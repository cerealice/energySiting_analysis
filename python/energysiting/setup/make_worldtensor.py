"""make_worldtensor.R — WorldTensor layers on the 1 km grid.

Each layer in config.WT_CATALOG is the mean of the yearly files selected in
data/raw_downloads/worldtensor/manifest.json (latest ES_WT_YEARS years each
variable has: ERA5 2021–2025, LUH3 2020–2024, NDVI 2021–2025, CAMS aerosols /
PM2.5 2020–2024, population 2016–2020, nighttime lights 2014–2018) or the single
static file (GMTED elevation / slope). Derived ERA5 features (wind speed, power
density, clearness, direct fraction, interannual variability) use the same window.

A layer is rebuilt whenever its source files change (tracked in
data/processed_data/variables/worldtensor_layers.json), so changing the window
never leaves stale 2000–2020 layers behind.
"""
from __future__ import annotations

import json

import numpy as np
import xarray as xr
from rasterio.transform import from_bounds

from .. import config, raster
from ._geo import base, mask_base, save_var, snap_array
from .worldtensor import WT_DIR, load_manifest

BBOX = (6.5, 18.5, 36.0, 47.5)       # lon/lat crop before reprojection
STATE = config.VAR_PATH / "worldtensor_layers.json"


def orient(arr, lon, lat):
    """(layers, lat, lon) array → north-up, longitudes in [-180, 180), cropped to BBOX."""
    arr = np.asarray(arr, dtype="float64")
    if arr.ndim == 2:
        arr = arr[None]
    lon = np.asarray(lon, dtype="float64")
    lat = np.asarray(lat, dtype="float64")
    if lon.max() > 180:
        lon = ((lon + 180) % 360) - 180
    oi = np.argsort(lon, kind="stable")
    li = np.argsort(-lat, kind="stable")
    lon, lat, arr = lon[oi], lat[li], arr[:, li][:, :, oi]
    mx = (lon >= BBOX[0]) & (lon <= BBOX[1])
    my = (lat >= BBOX[2]) & (lat <= BBOX[3])
    return arr[:, my][:, :, mx], lon[mx], lat[my]


def read_nc(path):
    """All layers of the first gridded variable (time steps kept as layers,
    like terra::rast on a multi-layer NetCDF)."""
    ds = xr.open_dataset(path, decode_times=False)
    name = next(v for v in ds.data_vars if ds[v].ndim >= 2)
    da = ds[name]
    latn = next(d for d in da.dims if d.lower().startswith("lat") or d == "y")
    lonn = next(d for d in da.dims if d.lower().startswith("lon") or d == "x")
    other = [d for d in da.dims if d not in (latn, lonn)]
    da = da.transpose(*other, latn, lonn)
    vals = da.values.reshape(-1, da.sizes[latn], da.sizes[lonn])
    out = orient(vals, da[lonn].values, da[latn].values)
    ds.close()
    return out


def to_grid(arr2d, lons, lats, b):
    dx, dy = abs(lons[1] - lons[0]), abs(lats[1] - lats[0])
    tr = from_bounds(lons.min() - dx / 2, lats.min() - dy / 2, lons.max() + dx / 2, lats.max() + dy / 2,
                     arr2d.shape[-1], arr2d.shape[-2])
    return snap_array(arr2d, tr, "EPSG:4326", "bilinear", b)


def stack_keys(keys, b, per_file=False):
    """Snap every layer of the given archive members → (layers, rows, cols).
    per_file=True averages layers within each file first (one layer per year)."""
    out = []
    for k in keys:
        a, lo, la = read_nc(WT_DIR / k)
        g = [to_grid(layer, lo, la, b) for layer in a]
        out.extend([np.nanmean(g, 0)] if per_file and len(g) > 1 else g)
    return np.stack(out)


def run():
    config.ensure_dirs()
    m = load_manifest()
    if m is None:
        raise SystemExit("No WorldTensor manifest — run `python -m energysiting.setup.fetch` "
                         "(or energysiting.setup.worldtensor) on a node with internet first.")
    layers = m["layers"]
    b = base()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    def build(name, source_keys, fn, na_fill=None):
        out = config.VAR_PATH / f"{name}.tif"
        if out.exists() and state.get(name) == source_keys:
            print("Up to date:", out.name)
            return
        with np.errstate(invalid="ignore", divide="ignore"):
            r = fn()
        if na_fill is not None:
            r = mask_base(np.where(np.isnan(r), na_fill, r), b)
        save_var(r, out.name, b)
        state[name] = source_keys
        STATE.write_text(json.dumps(state, indent=1))

    for name, (path, var, temporal) in config.WT_CATALOG.items():
        keys = layers[name]["keys"]
        yrs = layers[name]["years"]
        print(f"{name}: {f'mean {yrs[0]}–{yrs[-1]}' if yrs else 'static'}")
        fill = 0 if name.startswith("luh3_") else None    # absent land-use type → 0
        build(name, keys, lambda keys=keys: np.nanmean(stack_keys(keys, b), 0), na_fill=fill)

    # Derived ERA5 features — same window as their inputs
    L = lambda n: raster.read(config.VAR_PATH / f"{n}.tif", cache=False).band().astype("float64")  # noqa: E731
    K = lambda *ns: [k for n in ns for k in layers[n]["keys"]]                                      # noqa: E731
    build("era5_ws10_mean", K("era5_u10_mean", "era5_v10_mean"),
          lambda: np.hypot(L("era5_u10_mean"), L("era5_v10_mean")))
    build("era5_ws100_mean", K("era5_u100_mean", "era5_v100_mean"),
          lambda: np.hypot(L("era5_u100_mean"), L("era5_v100_mean")))
    build("era5_wpd100", K("era5_u100_mean", "era5_v100_mean"),
          lambda: np.hypot(L("era5_u100_mean"), L("era5_v100_mean")) ** 3)
    build("era5_clearness", K("era5_ssr_sum", "era5_ssrd_sum"),
          lambda: L("era5_ssr_sum") / L("era5_ssrd_sum"))
    build("era5_direct_frac", K("era5_cdir_sum", "era5_ssrdc_sum"),
          lambda: L("era5_cdir_sum") / L("era5_ssrdc_sum"))
    # interannual variability: SD of the yearly values within the window
    build("era5_ssrd_iav", K("era5_ssrd_sum"),
          lambda: np.nanstd(stack_keys(layers["era5_ssrd_sum"]["keys"], b, per_file=True), 0, ddof=1))
    build("era5_ws100_iav", K("era5_u100_mean", "era5_v100_mean"),
          lambda: np.nanstd(np.hypot(stack_keys(layers["era5_u100_mean"]["keys"], b, per_file=True),
                                     stack_keys(layers["era5_v100_mean"]["keys"], b, per_file=True)),
                            0, ddof=1))


if __name__ == "__main__":
    run()
