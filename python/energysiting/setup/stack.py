"""stack.R — assemble the 86-layer covariate stack (see config.COV_LAYERS: CHELSA,
ERA5-Land, selected ERA5, LUH3, WorldTensor extras, resource layers, land cover,
NUTS-2; continuous layers z-scored)
plus the solar / wind technology stacks and the future-infrastructure stack."""
from __future__ import annotations

import numpy as np

from .. import config, raster

# layer name → file in data/processed_data/variables (identity unless listed)
FILE_OF = {"tx": "transmission_110_qgis", "roads": "roads_qgis", "sub": "substations_110_qgis",
           "pop": "pop_density", "unemploy": "svi_unemp", "foreignborn": "svi_foreignborn",
           "poverty": "svi_pov", "gdp_pc": "zenodo_gdp_pc", "inst_quality": "zenodo_inst_quality",
           "lulc_sparse": "lulc_sparselyvegetated", "lulc_agriculture": "lulc_agricultural"}
FILES = [FILE_OF.get(l, l) for l in config.COV_LAYERS]
assert len(FILES) == len(config.COV_LAYERS) == 86


def input_paths():
    p = [config.VAR_PATH / f"{f}.tif" for f in FILES]
    for t in ("solar", "wind"):
        p += [config.VAR_PATH / f"env_impactScore_{t}.tif", config.VAR_PATH / f"{t}_capacity.tif",
              config.VAR_PATH / f"{t}_lag.tif"]
    return p + [config.VAR_PATH / "transmission_110_wPlanned.tif", config.VAR_PATH / "substations_110_wPlanned.tif"]


def up_to_date():
    outs = [config.DERIVED / f for f in ("covStack.tif", "solar_covStack.tif", "wind_covStack.tif", "future.tif")]
    if not all(o.exists() for o in outs):
        return False
    try:
        if raster.read(outs[0], cache=False).data.shape[0] != len(config.COV_LAYERS):
            return False
    except Exception:
        return False
    newest_in = max(p.stat().st_mtime for p in input_paths() if p.exists())
    return min(o.stat().st_mtime for o in outs) >= newest_in


def zscore(a, name=""):
    sd = np.nanstd(a, ddof=1)                                # terra::global sd = sample sd
    if not np.isfinite(sd) or sd == 0:
        # e.g. luh3_c4per (no C4 perennial crops in Italy): z-score undefined → NA,
        # as in R; the models impute it to a constant and it carries no signal
        print(f"  note: {name} is constant over Italy → stored as NA")
        return np.full_like(a, np.nan)
    return (a - np.nanmean(a)) / sd


def build(files, names, scale_up_to, out):
    layers = []
    grid = None
    for i, f in enumerate(files):
        r = raster.read(config.VAR_PATH / f"{f}.tif", cache=False)
        grid = r.grid
        a = r.band().astype("float64")
        layers.append(zscore(a, names[i]) if i < scale_up_to else a)
    raster.write(out, np.stack(layers), grid, names)
    print("Saved:", out)


def run():
    config.ensure_dirs()
    build(FILES, config.COV_LAYERS, len(config.CONT_LAYERS_V2), config.DERIVED / "covStack.tif")
    for tech in ("solar", "wind"):
        build([f"env_impactScore_{tech}", f"{tech}_capacity", f"{tech}_lag"],
              ["Environmental score", "Capacity factor", "Spatial lag"], 3,
              config.DERIVED / f"{tech}_covStack.tif")
    build(["transmission_110_wPlanned", "substations_110_wPlanned"],
          ["Transmission dist", "Substation dist"], 2, config.DERIVED / "future.tif")


if __name__ == "__main__":
    run()
