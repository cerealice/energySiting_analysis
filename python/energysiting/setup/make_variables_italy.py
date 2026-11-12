"""make_variables_italy.R — slope, population, OSM roads / grid, capacity
proxies, land cover, NUTS-1 dummies, spatial lag, FER placeholder, slope-only
environmental score.

Downloads mirror the R ``geodata`` / ``osmextract`` sources:
  * SRTM 30″ DEM            geodata.ucdavis.edu/geodata/elv/ITA_elv_msk.tif
  * WorldPop/GPW 2020 30″   geodata.ucdavis.edu/geodata/pop/...
  (capacity factors → make_resource.py: Global Solar Atlas / Global Wind Atlas)
  * ESA WorldCover 30″      geodata.ucdavis.edu/geodata/landuse/WorldCover_<var>_30s.tif
  * OSM Italy PBF           download.geofabrik.de (read with GDAL's OSM driver)
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from scipy import ndimage

from .. import config, raster
from ._geo import (GEODATA, base, distance, download, gisco_nuts, mask_base, rasterize, save_var,
                   snap, unzip_member)

PBF_URL = "https://download.geofabrik.de/europe/italy-latest.osm.pbf"
DEM_URL = f"{GEODATA}/geodata/elv/ITA_elv_msk.zip"
POP_URL = f"{GEODATA}/geodata/pop/gpw_v4_population_density_rev11_2020_30s.tif"
WC_URL = f"{GEODATA}/climate/worldclim/2_1/base/wc2.1_30s_{{var}}.zip"
LC_URL = f"{GEODATA}/geodata/landuse/WorldCover_{{var}}_30s.tif"
LULC_MAP = {"lulc_forest": "trees", "lulc_shrubland": "shrubs", "lulc_grassland": "grassland",
            "lulc_agricultural": "cropland", "lulc_developed": "built",
            "lulc_sparselyvegetated": "bare", "lulc_riparian": "water"}


def slope_deg(dem, res):
    """terra::terrain(v = 'slope', unit = 'degrees') — 3×3 Horn method."""
    z = np.pad(dem, 1, mode="edge")
    dzdx = ((z[:-2, 2:] + 2 * z[1:-1, 2:] + z[2:, 2:]) - (z[:-2, :-2] + 2 * z[1:-1, :-2] + z[2:, :-2])) / (8 * res)
    dzdy = ((z[2:, :-2] + 2 * z[2:, 1:-1] + z[2:, 2:]) - (z[:-2, :-2] + 2 * z[:-2, 1:-1] + z[:-2, 2:])) / (8 * res)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def osm(layer, where, columns=None):
    pbf = download(PBF_URL, config.RAW / "geofabrik_italy-latest.osm.pbf")
    return gpd.read_file(pbf, layer=layer, where=where, columns=columns,
                         engine="pyogrio").to_crs(config.EPSG)


def run():
    config.ensure_dirs()
    b = base()
    g = b.grid
    cache = config.RAW

    print("1. Slope")
    dem_tif = cache / "elevation" / "ITA_elv_msk.tif"
    if not dem_tif.exists():
        unzip_member(download(DEM_URL, cache / "elevation" / "ITA_elv_msk.zip"), dem_tif.name, dem_tif)
    dem = snap(dem_tif)
    save_var(mask_base(slope_deg(dem, g.res), b), "slope.tif", b)

    print("2. Population density")
    pop = download(POP_URL, cache / "population" / POP_URL.rsplit("/", 1)[1])
    save_var(snap(pop), "pop_density.tif", b)

    print("3. Roads distance (OSM)")
    roads = osm("lines", "highway IS NOT NULL", ["highway"])
    save_var(mask_base(distance(rasterize(roads, g), g), b), "roads_qgis.tif", b)

    print("3b. Transmission lines (>=110 kV) (OSM)")
    lines = osm("lines", "other_tags LIKE '%\"power\"=>\"line\"%'", ["other_tags"])
    v = lines["other_tags"].str.extract(r'"voltage"=>"([0-9]+)')[0].astype(float)
    tx = lines[v >= 110000]
    d_tx = mask_base(distance(rasterize(tx, g), g), b)
    save_var(d_tx, "transmission_110_qgis.tif", b)
    save_var(d_tx, "transmission_110_wPlanned.tif", b)   # planned lines not in OSM: placeholder
    # substations → separate step make_substations.py (needs the power-area OSM config)

    # 4-5. Capacity factor → make_resource.py (Global Solar Atlas PVOUT / Global Wind Atlas)

    print("6. Land use / land cover (ESA WorldCover fractions)")
    stack = []
    for out, var in LULC_MAP.items():
        p = download(LC_URL.format(var=var), cache / "landuse" / f"WorldCover_{var}_30s.tif")
        lc = snap(p)
        save_var(lc, f"{out}.tif", b)
        stack.append(lc)
    other = np.clip(1 - np.nansum(stack, axis=0), 0, 1)
    save_var(mask_base(other, b), "lulc_other.tif", b)

    print("7. NUTS-1 region dummies")
    nuts1 = gisco_nuts(1)
    for out, nid in {"region_nordovest": "ITC", "region_nordest": "ITH", "region_centro": "ITI",
                     "region_sud": "ITF", "region_isole": "ITG"}.items():
        r = rasterize(nuts1[nuts1.NUTS_ID == nid], g, 1.0, fill=0.0)
        save_var(mask_base(r, b), f"{out}.tif", b)

    # 8. Spatial lag → separate step make_spatial_lag.py (pre-2017 plants, 0/1)

    print("9. FER incentive (national placeholder)")
    save_var(b.band().copy(), "fer_incentive.tif", b)

    print("10. Environmental impact score (slope only until Natura 2000 is added)")
    s = raster.read(config.VAR_PATH / "slope.tif").band()
    env = mask_base(s / np.nanmax(s), b)
    save_var(env, "env_impactScore_solar.tif", b)
    save_var(env, "env_impactScore_wind.tif", b)


if __name__ == "__main__":
    run()
