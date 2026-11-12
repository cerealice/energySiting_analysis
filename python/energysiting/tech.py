"""Presence locations from the GEM trackers + RSE Atlante — tech.R.

Solar: GSPT utility-scale PV, operating, Italy; mask = all plants buffered 500 m;
       presences = start year ≥ 2017 and ≥ 1 MW; area = 10 000 m²/MW.
Wind : GWPT onshore, operating, Italy; presences = start year ≥ 2017 and ≥ 10 MW;
       area = 300 000 m²/MW.
Both are enriched with RSE municipal installed capacity (≥ 1 MW comuni whose
centroid is > 500 m from any tracker plant).

Writes (shared with R): derived/<tech>_hull_existing{,_mask}.tif, <tech>_hull_existing.csv
Python only:            derived/<tech>_pre2017.tif (0/1 plants operating before 2017)
Requires geopandas + rasterio.
"""
from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd

from . import config, raster
from .setup._geo import base, mask_base, rasterize, region_boundaries

SPEC = {
    "solar": dict(xlsx="Global-Solar-Power-Tracker-February-2026.xlsx", sheet="Utility-Scale (1 MW+)",
                  filt=lambda d: d["Technology Type"].isin(["PV", "Assumed PV"]),
                  min_mw=1, m2_per_mw=10_000, rse="fv_pot_comunale_2021", rse_year=2021),
    "wind": dict(xlsx="Global-Wind-Power-Tracker-February-2026.xlsx", sheet="Data",
                 filt=lambda d: d["Installation Type"] == "Onshore",
                 min_mw=10, m2_per_mw=300_000, rse="eo_pot_comunale_2019", rse_year=2019),
}


def rse_shapefile(name):
    shp = config.RAW / "rse_atlante" / name / f"{name}.shp"
    if not shp.exists():
        shp.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(config.RAW / f"d__temp_{name}.zip") as z:
            z.extractall(shp.parent)
        if not shp.exists():                         # archive may hold a sub-folder
            found = list(shp.parent.rglob("*.shp"))
            shp = found[0]
    return shp


def run_tech(tech, regions, b):
    s = SPEC[tech]
    raw = pd.read_excel(config.DATA / s["xlsx"], sheet_name=s["sheet"])
    for col in ("Latitude", "Longitude", "Capacity (MW)", "Start year"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw[(raw["Country/Area"] == "Italy") & s["filt"](raw) & (raw["Status"] == "operating")
              & raw.Latitude.notna() & raw.Longitude.notna()]
    sf = gpd.GeoDataFrame(raw, geometry=gpd.points_from_xy(raw.Longitude, raw.Latitude),
                          crs=4326).to_crs(config.EPSG)
    sf = gpd.sjoin(sf, regions[["NUTS_NAME", "geometry"]], predicate="within", how="left") \
        .drop(columns="index_right").rename(columns={"NUTS_NAME": "state_code"})

    mask = sf[["geometry"]].copy()
    mask["unique_id"] = np.arange(1, len(mask) + 1)
    mask["geometry"] = mask.buffer(500)

    loc = sf[(sf["Start year"] >= 2017) & (sf["Capacity (MW)"] >= s["min_mw"]) & sf.state_code.notna()].copy()
    loc["unique_id"] = np.arange(1, len(loc) + 1)
    if tech == "wind":
        loc["p_cap"] = loc["Capacity (MW)"]
    loc["area_m2"] = loc["Capacity (MW)"] * s["m2_per_mw"]
    loc["radius_m"] = np.sqrt(loc["area_m2"] / np.pi)

    # RSE Atlante municipal capacity
    rse = gpd.read_file(rse_shapefile(s["rse"]))
    rse["VALORE"] = pd.to_numeric(rse["VALORE"], errors="coerce")
    rse = rse[rse["VALORE"] >= 1].to_crs(config.EPSG)
    rse["geometry"] = rse.geometry.centroid
    rse = gpd.sjoin(rse, regions[["NUTS_NAME", "geometry"]], predicate="within", how="left") \
        .drop(columns="index_right").rename(columns={"NUTS_NAME": "state_code"})
    rse = rse[rse.state_code.notna()]
    near = gpd.sjoin_nearest(rse[["geometry"]], mask[["geometry"]], max_distance=500, how="left")
    covered = near.index[near["index_right"].notna()].unique()
    new = rse.drop(index=covered).copy()
    print(f"RSE {tech}: {len(rse)} comuni >= 1 MW; {len(new)} new (not already in tracker mask)")
    new["Capacity (MW)"] = new["VALORE"].astype(float)
    if tech == "wind":
        new["p_cap"] = new["VALORE"].astype(float)
    new["Start year"] = s["rse_year"]
    new["area_m2"] = new["Capacity (MW)"] * s["m2_per_mw"]
    new["radius_m"] = np.sqrt(new["area_m2"] / np.pi)

    nb = new[["geometry"]].copy()
    nb["geometry"] = nb.buffer(500)
    nb["unique_id"] = len(mask) + np.arange(1, len(nb) + 1)
    mask = pd.concat([mask, nb], ignore_index=True)
    keep = ["state_code", "Capacity (MW)", "Start year", "area_m2", "radius_m", "geometry"] + \
           (["p_cap"] if tech == "wind" else [])
    new = new[keep].copy()
    new["unique_id"] = len(loc) + np.arange(1, len(new) + 1)
    loc = gpd.GeoDataFrame(pd.concat([loc, new], ignore_index=True), crs=config.EPSG)
    print(f"{tech} locations total: {len(loc)} (tracker + RSE Atlante)")

    m = mask_base(rasterize(mask, b.grid, field="unique_id", touches=True), b)
    l = mask_base(rasterize(loc, b.grid, field="unique_id", touches=True), b)
    raster.write(config.DERIVED / f"{tech}_hull_existing_mask.tif", m, b.grid, ["unique_id"])
    raster.write(config.DERIVED / f"{tech}_hull_existing.tif", l, b.grid, ["unique_id"])
    # Plants already operating before 2017 (0/1) — source of the spatial-lag
    # predictor. Using only pre-2017 plants keeps the modelled presences
    # (start year >= 2017) out of their own predictor.
    old = sf[sf["Start year"] < 2017]
    pre = mask_base(np.where(np.isfinite(rasterize(old, b.grid, 1.0, touches=True)), 1.0, 0.0), b)
    raster.write(config.DERIVED / f"{tech}_pre2017.tif", pre, b.grid, ["pre2017"])
    print(f"{tech}: {len(old)} tracker plants operating before 2017 → {int(np.nansum(pre))} cells")
    loc.drop(columns="geometry").to_csv(config.DERIVED / f"{tech}_hull_existing.csv", index=False)
    loc[["unique_id", "geometry"]].to_file(config.OUT / f"{tech}_locations.gpkg")


def run():
    config.ensure_dirs()
    b = base()
    regions = region_boundaries()
    for tech in ("solar", "wind"):
        run_tech(tech, regions, b)


if __name__ == "__main__":
    run()
