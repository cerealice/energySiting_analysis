"""Geo helpers for the one-time setup scripts (terra / sf / giscoR / geodata).

Requires the standard Python geospatial stack: geopandas, rasterio, shapely,
pyproj, requests (and xarray + netCDF4 for make_worldtensor).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import requests
import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.warp import Resampling, reproject
from scipy import ndimage

from .. import config, raster

GISCO = "https://gisco-services.ec.europa.eu/distribution/v2"
GEODATA = "https://geodata.ucdavis.edu"
CACHE = config.RAW / "gisco"


def download(url, dest: Path, chunk=1 << 20):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for b in r.iter_content(chunk):
                fh.write(b)
        tmp.rename(dest)
    return dest


# ── GISCO (giscoR) ────────────────────────────────────────────────────────────
def gisco_nuts(level, year="2021", resolution="03", country="IT"):
    """giscoR::gisco_get_nuts(country, nuts_level, year, resolution) in EPSG:3035."""
    fn = f"NUTS_RG_{resolution}M_{year}_3035_LEVL_{level}.geojson"
    p = download(f"{GISCO}/nuts/geojson/{fn}", CACHE / fn)
    g = gpd.read_file(p)
    return g[g["CNTR_CODE"] == country].to_crs(config.EPSG).reset_index(drop=True)


def gisco_countries(country="IT", year="2020", resolution="03"):
    fn = f"CNTR_RG_{resolution}M_{year}_3035.geojson"
    g = gpd.read_file(download(f"{GISCO}/countries/geojson/{fn}", CACHE / fn))
    return g[g["CNTR_ID"] == country].to_crs(config.EPSG)


def gisco_communes(country="IT", year="2016"):
    fn = f"COMM_RG_01M_{year}_3035.geojson"
    g = gpd.read_file(download(f"{GISCO}/communes/geojson/{fn}", CACHE / fn))
    col = "CNTR_CODE" if "CNTR_CODE" in g else "CNTR_ID"
    return g[g[col] == country].to_crs(config.EPSG).reset_index(drop=True)


def region_boundaries():
    """function.R: Italian NUTS-2 (2021) with NUTS_ID / NUTS_NAME."""
    return gisco_nuts(2)[["NUTS_ID", "NUTS_NAME", "geometry"]]


# ── grid operations ───────────────────────────────────────────────────────────
def base():
    return raster.read(config.BASE_RASTER)


def transform_of(grid):
    return rasterio.transform.from_origin(grid.x0, grid.y0, grid.res, grid.res)


def rasterize(gdf, grid, value=1.0, field=None, touches=False, fill=np.nan):
    ok = gdf.geometry.notna() & ~gdf.geometry.is_empty
    gdf = gdf[ok]
    vals = gdf[field].astype(float) if field else [value] * len(gdf)
    shapes = list(zip(gdf.geometry, vals))
    if not shapes:
        return np.full(grid.shape, fill, dtype="float64")
    return features.rasterize(shapes, out_shape=grid.shape, transform=transform_of(grid),
                              fill=fill, all_touched=touches, dtype="float64")


def mask_base(arr, b=None):
    b = b or base()
    return np.where(np.isfinite(b.band()), arr, np.nan)


def snap(src_path, method="bilinear", band=None, b=None):
    """terra: project(base) |> resample(base) |> mask(base)."""
    b = b or base()
    with rasterio.open(src_path) as src:
        bands = [band] if band else list(range(1, src.count + 1))
        out = np.full((len(bands),) + b.grid.shape, np.nan, dtype="float64")
        for k, bi in enumerate(bands):
            reproject(source=rasterio.band(src, bi), destination=out[k],
                      src_nodata=src.nodata, dst_transform=transform_of(b.grid),
                      dst_crs=f"EPSG:{config.EPSG}", dst_nodata=np.nan,
                      resampling=getattr(Resampling, method))
    out = np.where(np.isfinite(b.band())[None], out, np.nan)
    return out[0] if band or out.shape[0] == 1 else out


def snap_array(arr, transform, crs, method="bilinear", b=None):
    b = b or base()
    out = np.full(b.grid.shape, np.nan)
    reproject(source=np.asarray(arr, dtype="float64"), destination=out, src_transform=transform,
              src_crs=crs, src_nodata=np.nan, dst_transform=transform_of(b.grid),
              dst_crs=f"EPSG:{config.EPSG}", dst_nodata=np.nan,
              resampling=getattr(Resampling, method))
    return mask_base(out, b)


def distance(features_mask, grid):
    """terra::distance: metres from every cell to the nearest feature cell."""
    feat = np.isfinite(features_mask) & (features_mask != 0)
    return ndimage.distance_transform_edt(~feat) * grid.res


def save_var(arr, name, b=None, min_coverage=0.5):
    """Write a layer and report how much of Italy it covers. A few NA cells along
    the coast are normal (source land masks differ from the base raster); a
    mostly-empty layer means a download or reprojection went wrong, so stop."""
    b = b or base()
    inside = np.isfinite(b.band())
    cov = float(np.isfinite(np.asarray(arr)[inside]).mean()) if inside.any() else 0.0
    if cov < min_coverage:
        raise RuntimeError(f"{name}: only {cov:.1%} of Italian cells have values — "
                           "check the source file / download before continuing")
    raster.write(config.VAR_PATH / name, arr, b.grid, [Path(name).stem])
    print(f"  saved: {name}  (coverage of Italy {cov:.1%})")


def unzip_member(zip_path, member, dest):
    """Extract one member (searched by base name) without loading it into memory."""
    import shutil
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.rsplit("/", 1)[-1] == member)
        with z.open(name) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out, 1 << 24)
    return dest
