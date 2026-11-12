"""Distance to electrical substations (section 3b of make_variables_italy.R).

Substations come from OSM nodes and areas tagged power=substation. Most Italian
substations are mapped as closed ways tagged only power=substation; GDAL's
default OSM config files those under "lines", so they were missed. This step
reads the .pbf with osm_plants.osm_config(), which makes them areas.
Planned substations are not in OSM: the "wPlanned" layer is a copy (as in R).
"""
from __future__ import annotations

import json

import pandas as pd
import geopandas as gpd

from .. import config, osm_plants
from ._geo import base, distance, mask_base, rasterize, save_var

METHOD = {"osmconf": "power_areas_v1"}
STATE = config.VAR_PATH / "substations.json"


def up_to_date():
    return STATE.exists() and json.loads(STATE.read_text()) == METHOD and all(
        (config.VAR_PATH / f).exists() for f in ("substations_110_qgis.tif", "substations_110_wPlanned.tif"))


def run():
    config.ensure_dirs()
    b = base()
    where = "other_tags LIKE '%\"power\"=>\"substation\"%'"
    pts = osm_plants.read_osm("points", where, ["other_tags"])
    poly = osm_plants.read_osm("multipolygons", where, ["other_tags"])
    print(f"  OSM substations: {len(pts)} nodes + {len(poly)} areas")
    subs = gpd.GeoDataFrame(geometry=pd.concat([poly.geometry.representative_point(), pts.geometry],
                                               ignore_index=True), crs=config.EPSG)
    d = mask_base(distance(rasterize(subs, b.grid), b.grid), b)
    save_var(d, "substations_110_qgis.tif", b)
    save_var(d, "substations_110_wPlanned.tif", b)
    STATE.write_text(json.dumps(METHOD))


if __name__ == "__main__":
    run()
