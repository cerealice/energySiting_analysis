"""make_worldtensor.R — ERA5 (mean 2000–2020), LUH3 states (2020), MODIS NDVI
(mean 2003–2020) and derived ERA5 features from the WorldTensor NetCDFs
downloaded by syntax/download_worldtensor.py."""
from __future__ import annotations

import numpy as np
import xarray as xr
from rasterio.transform import from_bounds

from .. import config, raster
from ._geo import base, mask_base, save_var, snap_array

WT = config.RAW / "worldtensor"
BBOX = (6.5, 18.5, 36.0, 47.5)       # lon/lat crop before reprojection
ERA5 = ["t2m_mean", "t2m_max", "t2m_min", "t2m_std", "d2m_mean", "tp_sum", "cp_sum", "sf_sum",
        "e_sum", "pev_sum", "ro_sum", "u10_mean", "v10_mean", "u100_mean", "v100_mean", "i10fg_mean",
        "ssrd_sum", "ssr_sum", "cdir_sum", "ssrdc_sum", "tcc_mean", "blh_mean", "sp_mean", "cape_mean"]
LUH3 = ["primf", "primn", "secdf", "secdn", "pastr", "range", "urban",
        "c3ann", "c4ann", "c3per", "c4per", "c3nfx"]


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


def years_stack(domain, var, years, b):
    """Every layer of every year, snapped to the base grid → (layers, rows, cols)."""
    out = []
    for y in years:
        p = WT / domain / var / f"{y}.nc"
        if p.exists():
            a, lo, la = read_nc(p)
            out.extend(to_grid(layer, lo, la, b) for layer in a)
    if not out:
        raise FileNotFoundError(f"No files for {domain}/{var}")
    return np.stack(out)


def safe_write(name, fn, b, na_fill=None):
    if (config.VAR_PATH / name).exists():
        print("Exists:", name)
        return
    try:
        r = fn()
        if na_fill is not None:
            r = mask_base(np.where(np.isnan(r), na_fill, r), b)
        save_var(r, name, b)
    except Exception as e:  # noqa: BLE001
        print(f"SKIP:   {name} — {e}")


def run():
    config.ensure_dirs()
    b = base()
    yrs = range(2000, 2021)
    for v in ERA5:
        safe_write(f"era5_{v}.tif", lambda v=v: np.nanmean(years_stack("climate", v, yrs, b), 0), b)
    for v in LUH3:
        safe_write(f"luh3_{v}.tif", lambda v=v: np.nanmean(years_stack("land_use/states", v, [2020], b), 0), b, na_fill=0)
    safe_write("wt_ndvi_mean.tif",
               lambda: np.nanmean(years_stack("vegetation", "ndvi_mean", range(2003, 2021), b), 0), b)

    L = lambda n: raster.read(config.VAR_PATH / n).band().astype("float64")  # noqa: E731
    safe_write("era5_ws10_mean.tif", lambda: np.hypot(L("era5_u10_mean.tif"), L("era5_v10_mean.tif")), b)
    safe_write("era5_ws100_mean.tif", lambda: np.hypot(L("era5_u100_mean.tif"), L("era5_v100_mean.tif")), b)
    safe_write("era5_wpd100.tif", lambda: np.hypot(L("era5_u100_mean.tif"), L("era5_v100_mean.tif")) ** 3, b)
    safe_write("era5_clearness.tif", lambda: L("era5_ssr_sum.tif") / L("era5_ssrd_sum.tif"), b)
    safe_write("era5_direct_frac.tif", lambda: L("era5_cdir_sum.tif") / L("era5_ssrdc_sum.tif"), b)
    safe_write("era5_ssrd_iav.tif", lambda: np.nanstd(years_stack("climate", "ssrd_sum", yrs, b), 0, ddof=1), b)
    safe_write("era5_ws100_iav.tif", lambda: np.nanstd(np.hypot(years_stack("climate", "u100_mean", yrs, b),
                                                                years_stack("climate", "v100_mean", yrs, b)),
                                                       0, ddof=1), b)


if __name__ == "__main__":
    run()
