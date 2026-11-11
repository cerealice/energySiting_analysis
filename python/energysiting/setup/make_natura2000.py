"""make_natura2000.R — environmental impact score
= 0.7 × proximity to Natura 2000 + 0.3 × normalised slope."""
from __future__ import annotations

import numpy as np
import geopandas as gpd

from .. import config, raster
from ._geo import base, distance, mask_base, rasterize, save_var

SHP = (config.RAW / "eea_v_3035_100_k_natura2000_p_2024_v01_r00" / "SHP"
       / "Natura2000_end2024_epsg3035.shp")


def run():
    config.ensure_dirs()
    b = base()
    nat = gpd.read_file(SHP)
    nat = nat[nat["SITECODE"].str.startswith("IT")].to_crs(config.EPSG)
    print("  Italian Natura 2000 sites:", len(nat))
    d = mask_base(distance(rasterize(nat, b.grid), b.grid), b)
    prox = 1 - d / np.nanmax(d)
    s = raster.read(config.VAR_PATH / "slope.tif").band()
    env = mask_base(prox * 0.7 + (s / np.nanmax(s)) * 0.3, b)
    save_var(env, "env_impactScore_solar.tif", b)
    save_var(env, "env_impactScore_wind.tif", b)


if __name__ == "__main__":
    run()
