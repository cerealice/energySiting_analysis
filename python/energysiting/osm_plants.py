"""Utility-scale solar and wind plant locations from OpenStreetMap.

Replaces the RSE Atlante municipality centroids as presence locations: OSM maps
most Italian ground-mounted PV farms as areas and wind turbines as points, so
covariates are measured where the plants actually are.

Solar sites: areas tagged power=plant|generator with (plant|generator):source=solar,
  excluding rooftop systems; overlapping/adjacent parts are merged into one
  footprint; footprints >= MIN_SOLAR_M2 (1 ha ≈ 1 MW at 10 000 m²/MW, the
  conversion R uses) are kept. Capacity = area / 10 000 m²/MW.
Wind sites: turbine nodes (power=generator, generator:source=wind), excluding
  small turbines (tagged height < 40 m or rotor < 30 m); turbines within
  WIND_LINK_M of each other form one farm; farms with >= MIN_TURBINES are kept.
  Capacity = sum of tagged turbine outputs, else 2 MW per turbine.

The OSM .pbf is read with GDAL's OSM driver. Its default config treats closed
ways tagged only `power=*` as lines; ``osm_config()`` writes a copy that makes
them areas (this also fixes substation areas in make_variables_italy).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from . import config

PBF = config.RAW / "geofabrik_italy-latest.osm.pbf"
OSMCONF = config.RAW / "osmconf_power_areas.ini"
MIN_SOLAR_M2 = 10_000
SOLAR_M2_PER_MW = 10_000
WIND_LINK_M = 1_000
MIN_TURBINES = 3
DEFAULT_TURBINE_MW = 2.0


# ── pure helpers (no geo stack needed) ────────────────────────────────────────
def parse_tags(other_tags: str) -> dict:
    """GDAL OSM 'other_tags' hstore string → dict."""
    if not isinstance(other_tags, str):
        return {}
    return dict(re.findall(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"', other_tags))


def parse_mw(value) -> float:
    """'12 MW', '12.5 MWp', '800 kW', '2,3 MW', '3000' (W) → MW; NaN if unparsable."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    s = str(value).strip().replace(",", ".").split(";")[0]
    m = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([kKmMgG]?)[wW]?[pP]?\s*$", s)
    if not m:
        return np.nan
    v, unit = float(m.group(1)), m.group(2).lower()
    return {"k": v / 1e3, "m": v, "g": v * 1e3}.get(unit, v / 1e6)


def parse_m(value) -> float:
    if value is None:
        return np.nan
    m = re.match(r"^\s*([0-9]*\.?[0-9]+)", str(value).replace(",", "."))
    return float(m.group(1)) if m else np.nan


def cluster_points(xy: np.ndarray, link_m: float) -> np.ndarray:
    """Single-linkage clusters: points closer than link_m share a label."""
    if len(xy) == 0:
        return np.zeros(0, int)
    pairs = cKDTree(xy).query_pairs(link_m, output_type="ndarray")
    from scipy.sparse import coo_matrix
    n = len(xy)
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)) if len(pairs) \
        else coo_matrix((n, n))
    return connected_components(g, directed=False)[1]


def is_rooftop(tags: dict) -> bool:
    return (tags.get("generator:place") == "roof" or tags.get("location") in ("roof", "rooftop")
            or "building" in tags)


def is_small_turbine(tags: dict) -> bool:
    h = parse_m(tags.get("height") or tags.get("generator:height"))
    d = parse_m(tags.get("rotor:diameter"))
    out = parse_mw(tags.get("generator:output:electricity"))
    return (np.isfinite(h) and h < 40) or (np.isfinite(d) and d < 30) or (np.isfinite(out) and out < 0.5)


# ── OSM reading (GDAL OSM driver via pyogrio) ─────────────────────────────────
def osm_config() -> Path:
    """GDAL osmconf.ini with `power` added to closed_ways_are_polygons."""
    if OSMCONF.exists():
        return OSMCONF
    import pyogrio
    src = Path(pyogrio.get_gdal_data_path() or "") / "osmconf.ini"
    if not src.exists():
        raise FileNotFoundError(f"GDAL osmconf.ini not found at {src}")
    lines = src.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("closed_ways_are_polygons=") and "power" not in line.split("=", 1)[1].split(","):
            lines[i] = line + ",power"
    OSMCONF.parent.mkdir(parents=True, exist_ok=True)
    OSMCONF.write_text("\n".join(lines) + "\n")
    return OSMCONF


def read_osm(layer, where, columns=None):
    import geopandas as gpd
    import pyogrio
    pyogrio.set_gdal_config_options({"OSM_CONFIG_FILE": str(osm_config()),
                                     "OSM_MAX_TMPFILE_SIZE": "4096"})
    g = gpd.read_file(PBF, layer=layer, where=where, columns=columns, engine="pyogrio")
    return g.to_crs(config.EPSG)


def solar_sites():
    import geopandas as gpd
    where = ("other_tags LIKE '%\"power\"=>\"plant\"%' OR other_tags LIKE '%\"power\"=>\"generator\"%'")
    g = read_osm("multipolygons", where, ["osm_id", "osm_way_id", "other_tags"])
    tags = g["other_tags"].map(parse_tags)
    src = tags.map(lambda t: t.get("plant:source") or t.get("generator:source") or "")
    solar = g[(src == "solar") & ~tags.map(is_rooftop)]
    print(f"  OSM solar areas: {len(g)} power areas → {len(solar)} ground-mounted solar")
    geoms = solar.geometry.buffer(0)
    union = geoms.union_all() if hasattr(geoms, "union_all") else geoms.unary_union
    merged = gpd.GeoDataFrame(geometry=[union], crs=config.EPSG) \
        .explode(index_parts=False).reset_index(drop=True)
    merged["area_m2"] = merged.area
    sites = merged[merged["area_m2"] >= MIN_SOLAR_M2].copy()
    sites["Capacity (MW)"] = sites["area_m2"] / SOLAR_M2_PER_MW
    print(f"  → {len(merged)} merged footprints, {len(sites)} ≥ {MIN_SOLAR_M2 / 1e4:.0f} ha "
          f"({sites['Capacity (MW)'].sum():,.0f} MW at {SOLAR_M2_PER_MW:,} m²/MW)")
    return sites.reset_index(drop=True)


def wind_sites():
    import geopandas as gpd
    from shapely.geometry import MultiPoint
    g = read_osm("points", "other_tags LIKE '%\"generator:source\"=>\"wind\"%'", ["osm_id", "other_tags"])
    tags = g["other_tags"].map(parse_tags)
    keep = (tags.map(lambda t: t.get("power")) == "generator") & ~tags.map(is_small_turbine)
    t = g[keep].copy()
    t["mw"] = tags[keep].map(lambda d: parse_mw(d.get("generator:output:electricity")))
    print(f"  OSM wind turbines: {len(g)} tagged → {len(t)} after removing small turbines")
    xy = np.column_stack([t.geometry.x, t.geometry.y])
    t["farm"] = cluster_points(xy, WIND_LINK_M)
    rows = []
    for _, f in t.groupby("farm"):
        if len(f) < MIN_TURBINES:
            continue
        cap = f["mw"].fillna(DEFAULT_TURBINE_MW).sum()
        rows.append({"geometry": MultiPoint(list(f.geometry)), "n_turbines": len(f), "Capacity (MW)": cap})
    sites = gpd.GeoDataFrame(rows, geometry="geometry", crs=config.EPSG)
    print(f"  → {t['farm'].nunique()} turbine clusters, {len(sites)} farms with ≥ {MIN_TURBINES} turbines "
          f"({sites['Capacity (MW)'].sum():,.0f} MW, {int(sites['n_turbines'].sum())} turbines)")
    return sites
