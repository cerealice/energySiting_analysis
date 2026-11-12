"""Presence locations — tech.R, with OSM plant footprints instead of RSE centroids.

Tracker plants (GEM): solar GSPT utility-scale PV / wind GWPT onshore, operating, Italy.
  Presences = start year >= 2017 and >= 1 MW (solar) / >= 10 MW (wind), as in R.
  Each is matched to the nearest OSM plant footprint within 2 km (GEM locations
  are often "approximate") and takes that footprint as its location.
Other plants (ES_PRESENCE_SOURCE):
  osm (default) — OSM solar farms >= 1 ha and wind farms >= 3 turbines that are
                  not a tracker plant (osm_plants.py). Real footprints.
  rse           — R's version: RSE Atlante municipal totals placed at the
                  municipality centroid.
Absence mask = every tracker plant and every OSM site, buffered 500 m.
A per-region comparison with the RSE totals is written to
derived/py/<tech>_presence_coverage.csv to show how complete OSM is.

Writes (shared with R): derived/<tech>_hull_existing{,_mask}.tif, <tech>_hull_existing.csv
Python only:            derived/<tech>_pre2017.tif (0/1 tracker plants operating before 2017)
Requires geopandas + rasterio + pyogrio (GDAL OSM driver).
"""
from __future__ import annotations

import json
import os
import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd

from . import config, osm_plants, raster
from .setup._geo import base, mask_base, rasterize, region_boundaries

SOURCE = os.environ.get("ES_PRESENCE_SOURCE", "osm")       # "osm" (default) | "rse" (as in R)
MATCH_M = 2_000          # tracker point → OSM footprint search radius (GEM accuracy is often "approximate")
METHOD = {"presence_source": SOURCE, "match_m": MATCH_M, "min_solar_m2": osm_plants.MIN_SOLAR_M2,
          "min_turbines": osm_plants.MIN_TURBINES, "wind_link_m": osm_plants.WIND_LINK_M}
STATE = config.DERIVED / "presence_locations.json"

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


def read_gem(tech, regions):
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
    return sf.reset_index(drop=True)


def read_rse(tech, regions):
    rse = gpd.read_file(rse_shapefile(SPEC[tech]["rse"]))
    rse["VALORE"] = pd.to_numeric(rse["VALORE"], errors="coerce")
    rse = rse[rse["VALORE"] >= 1].to_crs(config.EPSG)
    rse["geometry"] = rse.geometry.centroid
    rse = gpd.sjoin(rse, regions[["NUTS_NAME", "geometry"]], predicate="within", how="left") \
        .drop(columns="index_right").rename(columns={"NUTS_NAME": "state_code"})
    return rse[rse.state_code.notna()]


def add_region(g, regions):
    pts = gpd.GeoDataFrame(geometry=g.geometry.representative_point(), crs=g.crs)
    j = gpd.sjoin(pts, regions[["NUTS_NAME", "geometry"]], predicate="within", how="left")
    g = g.copy()
    g["state_code"] = j.loc[~j.index.duplicated(), "NUTS_NAME"].reindex(g.index).to_numpy()
    return g


def osm_presences(tech, sf, loc, regions):
    """Tracker presences get the matching OSM footprint (within MATCH_M); OSM
    sites not matched to any tracker plant (any year) and > 500 m from it are
    added as presences. Returns (loc, extra mask geometries)."""
    sites = osm_plants.solar_sites() if tech == "solar" else osm_plants.wind_sites()
    sites = add_region(sites, regions)
    sites = sites[sites.state_code.notna()].reset_index(drop=True)
    sites["site_id"] = np.arange(len(sites))

    # nearest OSM footprint for every operating tracker plant
    near = gpd.sjoin_nearest(sf[["geometry"]], sites[["site_id", "geometry"]], max_distance=MATCH_M,
                             how="left", distance_col="d")
    near = near[near.site_id.notna()].sort_values("d")
    near = near[~near.index.duplicated()]                       # one site per plant
    near = near[~near.site_id.duplicated()]                     # one plant per site (nearest)
    matched_site_of_plant = near["site_id"].astype(int)

    # tracker presences: footprint instead of the (often approximate) point
    loc = loc.copy()
    hit = loc.index.intersection(matched_site_of_plant.index)
    fp = sites.set_index("site_id").geometry
    geoms = loc.geometry.copy()
    geoms.loc[hit] = gpd.GeoSeries(fp.loc[matched_site_of_plant.loc[hit].to_numpy()].to_numpy(),
                                   index=hit, crs=config.EPSG)
    loc = loc.set_geometry(geoms)
    loc["location_source"] = np.where(loc.index.isin(hit), "GEM+OSM footprint", "GEM point")

    # OSM-only sites: not matched to any tracker plant and not within 500 m of one
    free = sites[~sites.site_id.isin(matched_site_of_plant)]
    close = gpd.sjoin_nearest(free[["geometry"]], sf[["geometry"]], max_distance=500, how="left")
    free = free.drop(index=close.index[close["index_right"].notna()].unique())
    new = free.copy()
    new["Start year"] = np.nan                                   # OSM rarely dates plants
    if tech == "solar":
        new["radius_m"] = np.sqrt(new["area_m2"] / np.pi)
    else:
        new["p_cap"] = new["Capacity (MW)"]
        new["area_m2"] = new["Capacity (MW)"] * SPEC[tech]["m2_per_mw"]
        new["radius_m"] = np.sqrt(new["area_m2"] / np.pi)
    new["location_source"] = "OSM"
    keep = [c for c in ("state_code", "Capacity (MW)", "Start year", "area_m2", "radius_m", "p_cap",
                        "n_turbines", "location_source", "geometry") if c in new]
    out = gpd.GeoDataFrame(pd.concat([loc, new[keep]], ignore_index=True), crs=config.EPSG)
    print(f"  tracker plants matched to an OSM footprint: {len(hit)}/{len(loc)} presences "
          f"({len(matched_site_of_plant)} of {len(sf)} operating plants); OSM-only presences: {len(new)}")
    return out, sites.geometry


def coverage_report(tech, loc, rse):
    """OSM/tracker capacity vs RSE municipal totals by region (OSM completeness check)."""
    a = loc.groupby("state_code")["Capacity (MW)"].sum().rename("presences_MW")
    r = rse.groupby("state_code")["VALORE"].sum().rename("RSE_MW")
    t = pd.concat([a, r], axis=1).fillna(0)
    t["ratio"] = (t.presences_MW / t.RSE_MW.replace(0, np.nan)).round(2)
    print(f"  {tech}: capacity by region, presences vs RSE ({SPEC[tech]['rse_year']}):")
    print(t.round(0).sort_values("RSE_MW", ascending=False).to_string().replace("\n", "\n    "))
    t.to_csv(config.OUT / f"{tech}_presence_coverage.csv")


def run_tech(tech, regions, b):
    s = SPEC[tech]
    sf = read_gem(tech, regions)
    loc = sf[(sf["Start year"] >= 2017) & (sf["Capacity (MW)"] >= s["min_mw"]) & sf.state_code.notna()].copy()
    if tech == "wind":
        loc["p_cap"] = loc["Capacity (MW)"]
    loc["area_m2"] = loc["Capacity (MW)"] * s["m2_per_mw"]
    loc["radius_m"] = np.sqrt(loc["area_m2"] / np.pi)
    rse = read_rse(tech, regions)

    mask_geoms = [sf.geometry.buffer(500)]
    if SOURCE == "osm":
        loc, site_geoms = osm_presences(tech, sf, loc, regions)
        mask_geoms.append(site_geoms.buffer(500))
    else:                                                    # R behaviour: RSE municipality centroids
        near = gpd.sjoin_nearest(rse[["geometry"]], gpd.GeoDataFrame(geometry=mask_geoms[0], crs=sf.crs),
                                 max_distance=500, how="left")
        new = rse.drop(index=near.index[near["index_right"].notna()].unique()).copy()
        print(f"RSE {tech}: {len(rse)} comuni >= 1 MW; {len(new)} new (not already in tracker mask)")
        new["Capacity (MW)"] = new["VALORE"].astype(float)
        if tech == "wind":
            new["p_cap"] = new["VALORE"].astype(float)
        new["Start year"] = s["rse_year"]
        new["area_m2"] = new["Capacity (MW)"] * s["m2_per_mw"]
        new["radius_m"] = np.sqrt(new["area_m2"] / np.pi)
        new["location_source"] = "RSE centroid"
        mask_geoms.append(new.geometry.buffer(500))
        keep = ["state_code", "Capacity (MW)", "Start year", "area_m2", "radius_m", "location_source",
                "geometry"] + (["p_cap"] if tech == "wind" else [])
        loc = gpd.GeoDataFrame(pd.concat([loc, new[keep]], ignore_index=True), crs=config.EPSG)
    loc = loc.reset_index(drop=True)
    loc["unique_id"] = np.arange(1, len(loc) + 1)
    print(f"{tech} presences: {len(loc)} — " + ", ".join(f"{k}: {v}" for k, v in
                                                         loc.location_source.value_counts().items()))
    coverage_report(tech, loc, rse)

    mask = gpd.GeoDataFrame(geometry=pd.concat(mask_geoms, ignore_index=True), crs=config.EPSG)
    mask["unique_id"] = np.arange(1, len(mask) + 1)
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
    pts = gpd.GeoDataFrame(loc[["unique_id", "location_source"]],
                           geometry=loc.geometry.representative_point(), crs=config.EPSG)
    pts.to_file(config.OUT / f"{tech}_locations.gpkg")


def run():
    config.ensure_dirs()
    print(f"Presence locations: {SOURCE} (ES_PRESENCE_SOURCE)")
    b = base()
    regions = region_boundaries()
    for tech in ("solar", "wind"):
        run_tech(tech, regions, b)
    STATE.write_text(json.dumps(METHOD))


def up_to_date():
    return STATE.exists() and json.loads(STATE.read_text()) == METHOD and all(
        (config.DERIVED / f"{t}_{f}").exists() for t in ("solar", "wind")
        for f in ("hull_existing.tif", "hull_existing_mask.tif", "hull_existing.csv", "pre2017.tif"))


if __name__ == "__main__":
    run()
