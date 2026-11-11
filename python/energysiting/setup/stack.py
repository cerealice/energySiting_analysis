"""stack.R — assemble the 102-layer covariate stack (continuous layers z-scored)
plus the solar / wind technology stacks and the future-infrastructure stack."""
from __future__ import annotations

import numpy as np

from .. import config, raster

FILES = (
    ["transmission_110_qgis", "roads_qgis", "substations_110_qgis", "slope", "pop_density",
     "svi_unemp", "svi_foreignborn", "svi_pov", "zenodo_gdp_pc", "zenodo_inst_quality"]
    + [f"wclim_bio{i:02d}" for i in range(1, 20)]
    + ["era5_" + n for n in config.CONT_LAYERS[29:53]]
    + config.CONT_LAYERS[53:66]
    + ["era5_ws10_mean", "era5_ws100_mean", "era5_wpd100", "era5_clearness", "era5_direct_frac",
       "era5_ssrd_iav", "era5_ws100_iav"]
    + ["lulc_forest", "lulc_grassland", "lulc_shrubland", "lulc_riparian", "lulc_sparselyvegetated",
       "lulc_agricultural", "lulc_developed", "lulc_other"]
    + config.NUTS2_LAYERS
)
# CONT_LAYERS[29:53] already carry the "era5_" prefix
FILES = [f.replace("era5_era5_", "era5_") for f in FILES]
assert len(FILES) == 102


def zscore(a):
    return (a - np.nanmean(a)) / np.nanstd(a, ddof=1)       # terra::global sd = sample sd


def build(files, names, scale_up_to, out):
    layers = []
    grid = None
    for i, f in enumerate(files):
        r = raster.read(config.VAR_PATH / f"{f}.tif", cache=False)
        grid = r.grid
        a = r.band().astype("float64")
        layers.append(zscore(a) if i < scale_up_to else a)
    raster.write(out, np.stack(layers), grid, names)
    print("Saved:", out)


def run():
    config.ensure_dirs()
    build(FILES, config.COV_LAYERS, 73, config.DERIVED / "covStack.tif")
    for tech in ("solar", "wind"):
        build([f"env_impactScore_{tech}", f"{tech}_capacity", f"{tech}_lag"],
              ["Environmental score", "Capacity factor", "Spatial lag"], 3,
              config.DERIVED / f"{tech}_covStack.tif")
    build(["transmission_110_wPlanned", "substations_110_wPlanned"],
          ["Transmission dist", "Substation dist"], 2, config.DERIVED / "future.tif")


if __name__ == "__main__":
    run()
