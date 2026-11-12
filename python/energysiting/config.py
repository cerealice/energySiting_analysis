"""Shared configuration — Python equivalent of syntax/function.R.

Paths, CRS, the model formula (as an ordered predictor list), display labels and
the Italian NUTS-2 / NUTS-1 lookup tables used by every step of the pipeline.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────
# ES_ROOT plays the role of RSCRIPT_ROOT in run_all.R / run_hpc.sh.
ROOT = Path(os.environ.get("ES_ROOT", Path(__file__).resolve().parents[2])).resolve()

DATA = ROOT / "data"
RAW = DATA / "raw_downloads"
VAR_PATH = DATA / "processed_data" / "variables"
MASK_PATH = DATA / "processed_data" / "masks"
BASE_RASTER = MASK_PATH / "Italy_base_raster.tif"

# Inputs shared with the R pipeline (covariate stacks, presence rasters).
DERIVED = ROOT / "derived"
# Outputs of the Python analysis steps are kept apart so they never overwrite R's.
OUT = Path(os.environ.get("ES_OUT", DERIVED / "py"))
FIG = Path(os.environ.get("ES_FIG", ROOT / "fig" / "python"))

EPSG = 3035                     # ETRS89 / LAEA Europe
RES_M = 1000                    # base grid resolution (m)
SEED = int(os.environ.get("ES_SEED", "42"))


def n_jobs() -> int:
    """Workers: LSF → SLURM → half of local cores (same rule as modeling.R)."""
    for var in ("LSB_DJOB_NUMPROC", "SLURM_CPUS_PER_TASK", "ES_N_JOBS"):
        v = os.environ.get(var)
        if v and v.isdigit() and int(v) > 0:
            return int(v)
    return max(1, (os.cpu_count() or 2) // 2)


def ensure_dirs() -> None:
    for p in (OUT, FIG, DERIVED, VAR_PATH, MASK_PATH):
        p.mkdir(parents=True, exist_ok=True)


# ── NUTS-2 regions (NUTS 2021) ────────────────────────────────────────────────
# id → (NUTS_NAME as returned by GISCO, short label, NUTS-1 macro-region)
NUTS2 = {
    "ITC1": ("Piemonte", "Piemonte", "Nord-Ovest"),
    "ITC2": ("Valle d’Aosta/Vallée d’Aoste", "Valle d'Aosta", "Nord-Ovest"),
    "ITC3": ("Liguria", "Liguria", "Nord-Ovest"),
    "ITC4": ("Lombardia", "Lombardia", "Nord-Ovest"),
    "ITH1": ("Provincia Autonoma di Bolzano/Bozen", "PA Bolzano", "Nord-Est"),
    "ITH2": ("Provincia Autonoma di Trento", "PA Trento", "Nord-Est"),
    "ITH3": ("Veneto", "Veneto", "Nord-Est"),
    "ITH4": ("Friuli-Venezia Giulia", "Friuli-VG", "Nord-Est"),
    "ITH5": ("Emilia-Romagna", "Emilia-Romagna", "Nord-Est"),
    "ITI1": ("Toscana", "Toscana", "Centro"),
    "ITI2": ("Umbria", "Umbria", "Centro"),
    "ITI3": ("Marche", "Marche", "Centro"),
    "ITI4": ("Lazio", "Lazio", "Centro"),
    "ITF1": ("Abruzzo", "Abruzzo", "Sud"),
    "ITF2": ("Molise", "Molise", "Sud"),
    "ITF3": ("Campania", "Campania", "Sud"),
    "ITF4": ("Puglia", "Puglia", "Sud"),
    "ITF5": ("Basilicata", "Basilicata", "Sud"),
    "ITF6": ("Calabria", "Calabria", "Sud"),
    "ITG1": ("Sicilia", "Sicilia", "Isole"),
    "ITG2": ("Sardegna", "Sardegna", "Isole"),
}
NUTS2_IDS = list(NUTS2)
NUTS2_NAME = {k: v[0] for k, v in NUTS2.items()}
NUTS2_BY_NAME = {v[0]: k for k, v in NUTS2.items()}
# GISCO has used both the typographic and the ASCII apostrophe over the years.
NUTS2_BY_NAME["Valle d'Aosta/Vallée d'Aoste"] = "ITC2"
NUTS1_OF = {k: v[2] for k, v in NUTS2.items()}
NUTS1_LEVELS = ["Nord-Ovest", "Nord-Est", "Centro", "Sud", "Isole"]
NUTS1_ID = {"ITC": "Nord-Ovest", "ITH": "Nord-Est", "ITI": "Centro", "ITF": "Sud", "ITG": "Isole"}

# ── Covariate stack layer order (stack.R / zonal.R) ───────────────────────────
CONT_LAYERS = (
    ["tx", "roads", "sub", "slope", "pop",
     "unemploy", "foreignborn", "poverty", "gdp_pc", "inst_quality"]
    + [f"wclim_bio{i:02d}" for i in range(1, 20)]
    + ["era5_t2m_mean", "era5_t2m_max", "era5_t2m_min", "era5_t2m_std", "era5_d2m_mean",
       "era5_tp_sum", "era5_cp_sum", "era5_sf_sum", "era5_e_sum", "era5_pev_sum", "era5_ro_sum",
       "era5_u10_mean", "era5_v10_mean", "era5_u100_mean", "era5_v100_mean", "era5_i10fg_mean",
       "era5_ssrd_sum", "era5_ssr_sum", "era5_cdir_sum", "era5_ssrdc_sum",
       "era5_tcc_mean", "era5_blh_mean", "era5_sp_mean", "era5_cape_mean"]
    + ["luh3_primf", "luh3_primn", "luh3_secdf", "luh3_secdn", "luh3_pastr", "luh3_range",
       "luh3_urban", "luh3_c3ann", "luh3_c4ann", "luh3_c3per", "luh3_c4per", "luh3_c3nfx"]
    + ["wt_ndvi_mean"]
    + ["era5_ws10_mean", "era5_ws100_mean", "era5_wpd100", "era5_clearness",
       "era5_direct_frac", "era5_ssrd_iav", "era5_ws100_iav"]
)
LULC_LAYERS = ["lulc_forest", "lulc_grassland", "lulc_shrubland", "lulc_riparian",
               "lulc_sparse", "lulc_agriculture", "lulc_developed", "lulc_other"]
NUTS2_LAYERS = ["nuts2_" + i.lower() for i in NUTS2_IDS]
# Extra WorldTensor layers added in the Python port (continuous, z-scored).
WT_EXTRA_LAYERS = ["aq_aod550_mean", "aq_pm2p5_mean",            # CAMS EAC4 air quality
                   "wt_population_density", "wt_ntl_harmonized",  # human systems
                   "wt_elevation_mean", "wt_slope_mean"]          # GMTED2010 topography (static)
CONT_LAYERS_ALL = CONT_LAYERS + WT_EXTRA_LAYERS                    # 73 + 6 = 79
COV_LAYERS_WT = CONT_LAYERS_ALL + LULC_LAYERS + NUTS2_LAYERS       # previous Python stack: 108
COV_LAYERS_R = CONT_LAYERS + LULC_LAYERS + NUTS2_LAYERS            # R's covStack: 102

# ── Climate & resource block (current Python stack) ──────────────────────────
# One source per role, no overlapping variables:
#   CHELSA v2.1 BIO1–19 (1 km, 1981–2010)      climate normals (replaces WorldClim)
#   Global Solar Atlas PVOUT / Global Wind Atlas → the `cf` layer (resource)
#   Global Wind Atlas 100 m mean wind speed      wind resource (wind model)
#   CERRA 100 m wind speed, SD of annual means   recent variability (wind model)
#   ERA5-Land (0.1°) solar radiation, pressure   recent conditions at 9 km
#   ERA5 (0.25°) only what the others lack       gust, clear-sky direct radiation,
#                                                cloud cover, boundary layer, CAPE
import datetime as _dt
CLIMATE_YEARS = list(range(_dt.date.today().year - 5, _dt.date.today().year))  # last 5 complete years
INFRA_SOCIO = CONT_LAYERS[:10]
CHELSA_LAYERS = [f"chelsa_bio{i:02d}" for i in range(1, 20)]
ERA5_KEEP = ["era5_i10fg_mean", "era5_cdir_sum", "era5_tcc_mean", "era5_blh_mean", "era5_cape_mean"]
ERA5LAND_LAYERS = ["era5land_ssrd", "era5land_sp"]
LUH3_NDVI = CONT_LAYERS[53:66]
WIND_RESOURCE = ["gwa_ws100", "cerra_ws100_iav"]
CONT_LAYERS_V2 = (INFRA_SOCIO + CHELSA_LAYERS + ERA5_KEEP + ERA5LAND_LAYERS + LUH3_NDVI
                  + WT_EXTRA_LAYERS + WIND_RESOURCE)                # 10+19+5+2+13+6+2 = 57
COV_LAYERS = CONT_LAYERS_V2 + LULC_LAYERS + NUTS2_LAYERS           # 57 + 8 + 21 = 86


def cov_layout(n_bands: int) -> list:
    """Layer names of a covStack.tif with n_bands layers (current 86, previous 108, R 102)."""
    for layout in (COV_LAYERS, COV_LAYERS_WT, COV_LAYERS_R):
        if n_bands == len(layout):
            return layout
    raise ValueError(f"covStack.tif has {n_bands} layers; expected {len(COV_LAYERS)}, "
                     f"{len(COV_LAYERS_WT)} or {len(COV_LAYERS_R)}")


# ── WorldTensor (Zenodo 10.5281/zenodo.19047618) ──────────────────────────────
# output layer → (path inside the domain archives, variable, temporal?)
# Time-varying variables are averaged over the latest WT_YEARS years each
# variable has in the archive (resolved at download time → manifest.json).
WT_YEARS = int(os.environ.get("ES_WT_YEARS", "5"))
_ERA5 = ["t2m_mean", "t2m_max", "t2m_min", "t2m_std", "d2m_mean", "tp_sum", "cp_sum", "sf_sum",
         "e_sum", "pev_sum", "ro_sum", "u10_mean", "v10_mean", "u100_mean", "v100_mean", "i10fg_mean",
         "ssrd_sum", "ssr_sum", "cdir_sum", "ssrdc_sum", "tcc_mean", "blh_mean", "sp_mean", "cape_mean"]
_LUH3 = ["primf", "primn", "secdf", "secdn", "pastr", "range", "urban",
         "c3ann", "c4ann", "c3per", "c4per", "c3nfx"]
WT_CATALOG = (
    {f"era5_{v}": ("climate", v, True) for v in _ERA5}
    | {f"luh3_{v}": ("land_use/states", v, True) for v in _LUH3}
    | {"wt_ndvi_mean": ("vegetation", "ndvi_mean", True),
       "aq_aod550_mean": ("air_quality", "aod550_mean", True),
       "aq_pm2p5_mean": ("air_quality", "pm2p5_mean", True),
       "wt_population_density": ("human_systems", "population_density", True),
       "wt_ntl_harmonized": ("human_systems", "ntl_harmonized", True),
       "wt_elevation_mean": ("static/topography", "elevation_mean", False),
       "wt_slope_mean": ("static/topography", "slope_mean", False)}
)
TECH_LAYERS = ["env", "cf", "lag"]
FUTURE_LAYERS = ["tx", "sub"]

# ── Model predictors (region_model in function.R) ─────────────────────────────
# lulc_other and nuts2_itg2 are omitted (reference classes). The 7 derived ERA5
# features are in the stack but not in the formula — kept identical to R.
MODEL_VARS = (
    ["tx", "roads", "sub", "slope", "pop",
     "unemploy", "foreignborn", "poverty", "gdp_pc", "inst_quality"]
    + [f"wclim_bio{i:02d}" for i in range(1, 20)]
    + CONT_LAYERS[29:53]                      # 24 ERA5 variables
    + CONT_LAYERS[53:65]                      # 12 LUH3 states
    + ["wt_ndvi_mean"]
    + LULC_LAYERS[:-1]                        # lulc_other = reference
    + [l for l in NUTS2_LAYERS if l != "nuts2_itg2"]   # Sardegna = reference
    + TECH_LAYERS
)
assert len(MODEL_VARS) == 96

# Derived ERA5 wind-resource features (make_worldtensor.R section 4). They are in
# the stack but were not in R's region_model; the wind model now uses them.
# NB: WorldTensor provides annual-mean U/V only, so these are speeds of the
# mean wind *vector* (lower than the true mean speed where direction varies).
WIND_ERA5_DERIVED = ["era5_ws10_mean", "era5_ws100_mean", "era5_wpd100", "era5_ws100_iav"]


def model_vars(tech: str, columns=None) -> list:
    """Predictors for one technology.

    Current climate block (stack has CHELSA layers): solar 85, wind 87 —
      infrastructure & socioeconomic 10, CHELSA 19, ERA5 5, ERA5-Land 2,
      LUH3 + NDVI 13, extra WorldTensor 6, land cover 7, NUTS-2 20,
      [wind: GWA 100 m speed, CERRA variability], env + cf + lag.
    Legacy block (R's 102- or the 108-layer stack): R's 96 + 6 WorldTensor
      (+ 4 derived ERA5 wind features for wind).

    ``columns``: the columns available (zonal output); only those are returned,
    and the block is chosen from them.
    ES_CLIMATE_SET=legacy   → force the legacy block
    ES_WT_EXTRA=0           → leave out the 6 extra WorldTensor layers
    ES_WIND_ERA5_DERIVED=0  → (legacy) leave out the derived ERA5 wind features
    ES_DROP_VARS=lag,...    → drop predictors (sensitivity runs)
    """
    cols = set(columns) if columns is not None else set(COV_LAYERS) | set(TECH_LAYERS)
    wt_extra = WT_EXTRA_LAYERS if os.environ.get("ES_WT_EXTRA", "1") != "0" else []
    if "chelsa_bio01" in cols and os.environ.get("ES_CLIMATE_SET", "v2") != "legacy":
        v = (INFRA_SOCIO + CHELSA_LAYERS + ERA5_KEEP + ERA5LAND_LAYERS + LUH3_NDVI + wt_extra
             + LULC_LAYERS[:-1] + [l for l in NUTS2_LAYERS if l != "nuts2_itg2"]
             + (WIND_RESOURCE if tech == "wind" else []) + TECH_LAYERS)
    else:
        v = list(MODEL_VARS[:-3]) + wt_extra
        if tech == "wind" and os.environ.get("ES_WIND_ERA5_DERIVED", "1") != "0":
            v += WIND_ERA5_DERIVED
        v += TECH_LAYERS
    drop = {d.strip() for d in os.environ.get("ES_DROP_VARS", "").split(",") if d.strip()}
    return [x for x in v if x not in drop and x in cols]

# ── Display labels (modeling.R var_labels / imp recode) ───────────────────────
VAR_LABELS = {
    "tx": "Transmission dist", "roads": "Road dist", "sub": "Substation dist",
    "slope": "Slope", "pop": "Population density",
    "unemploy": "Unemployment", "foreignborn": "Foreign born", "poverty": "Poverty",
    "gdp_pc": "GDP per capita", "inst_quality": "Institutional quality",
    "wclim_bio01": "Annual mean temp (WC)", "wclim_bio02": "Diurnal temp range (WC)",
    "wclim_bio03": "Isothermality (WC)", "wclim_bio04": "Temp seasonality (WC)",
    "wclim_bio05": "Max temp warmest (WC)", "wclim_bio06": "Min temp coldest (WC)",
    "wclim_bio07": "Annual temp range (WC)", "wclim_bio08": "Temp wettest qtr (WC)",
    "wclim_bio09": "Temp driest qtr (WC)", "wclim_bio10": "Temp warmest qtr (WC)",
    "wclim_bio11": "Temp coldest qtr (WC)", "wclim_bio12": "Annual precip (WC)",
    "wclim_bio13": "Precip wettest mo (WC)", "wclim_bio14": "Precip driest mo (WC)",
    "wclim_bio15": "Precip seasonality (WC)", "wclim_bio16": "Precip wettest qtr (WC)",
    "wclim_bio17": "Precip driest qtr (WC)", "wclim_bio18": "Precip warmest qtr (WC)",
    "wclim_bio19": "Precip coldest qtr (WC)",
    "era5_t2m_mean": "Temperature mean (ERA5)", "era5_t2m_max": "Temperature max (ERA5)",
    "era5_t2m_min": "Temperature min (ERA5)", "era5_t2m_std": "Temperature SD (ERA5)",
    "era5_d2m_mean": "Dewpoint temp (ERA5)", "era5_tp_sum": "Precipitation (ERA5)",
    "era5_cp_sum": "Convective precip (ERA5)", "era5_sf_sum": "Snowfall (ERA5)",
    "era5_e_sum": "Evaporation (ERA5)", "era5_pev_sum": "Potential evap (ERA5)",
    "era5_ro_sum": "Runoff (ERA5)", "era5_u10_mean": "Wind U 10m (ERA5)",
    "era5_v10_mean": "Wind V 10m (ERA5)", "era5_u100_mean": "Wind U 100m (ERA5)",
    "era5_v100_mean": "Wind V 100m (ERA5)", "era5_i10fg_mean": "Wind gust (ERA5)",
    "era5_ssrd_sum": "Solar radiation (ERA5)", "era5_ssr_sum": "Net solar rad (ERA5)",
    "era5_cdir_sum": "Clear-sky direct solar (ERA5)", "era5_ssrdc_sum": "Clear-sky solar down (ERA5)",
    "era5_tcc_mean": "Cloud cover (ERA5)", "era5_blh_mean": "Boundary layer H (ERA5)",
    "era5_sp_mean": "Surface pressure (ERA5)", "era5_cape_mean": "CAPE (ERA5)",
    "luh3_primf": "Primary forest (LUH3)", "luh3_primn": "Primary non-forest (LUH3)",
    "luh3_secdf": "Secondary forest (LUH3)", "luh3_secdn": "Secondary non-forest (LUH3)",
    "luh3_pastr": "Pasture (LUH3)", "luh3_range": "Rangeland (LUH3)",
    "luh3_urban": "Urban (LUH3)", "luh3_c3ann": "C3 annual crops (LUH3)",
    "luh3_c4ann": "C4 annual crops (LUH3)", "luh3_c3per": "C3 perennial crops (LUH3)",
    "luh3_c4per": "C4 perennial crops (LUH3)", "luh3_c3nfx": "N-fixing crops (LUH3)",
    "wt_ndvi_mean": "NDVI (MODIS)",
    "lulc_forest": "Forest", "lulc_grassland": "Grassland", "lulc_shrubland": "Shrubland",
    "lulc_riparian": "Riparian", "lulc_sparse": "Vegetated", "lulc_agriculture": "Agriculture",
    "lulc_developed": "Developed", "lulc_other": "Otherland",
    "env": "Environmental score", "cf": "Capacity factor", "lag": "Spatial lag (pre-2017 plants)",
    "era5_ws10_mean": "Wind speed 10m (ERA5)", "era5_ws100_mean": "Wind speed 100m (ERA5)",
    "era5_wpd100": "Wind power density 100m (ERA5)", "era5_ws100_iav": "Wind speed 100m IAV (ERA5)",
    "era5_clearness": "Clearness index (ERA5)", "era5_direct_frac": "Direct irradiance frac (ERA5)",
    "era5_ssrd_iav": "Solar radiation IAV (ERA5)",
    "aq_aod550_mean": "Aerosol optical depth (CAMS)", "aq_pm2p5_mean": "PM2.5 (CAMS)",
    "wt_population_density": "Population density (WT)", "wt_ntl_harmonized": "Nighttime lights (WT)",
    "wt_elevation_mean": "Elevation (GMTED)", "wt_slope_mean": "Terrain slope (GMTED)",
    "chelsa_bio01": "Annual mean temp (CHELSA)",
    "chelsa_bio02": "Diurnal temp range (CHELSA)",
    "chelsa_bio03": "Isothermality (CHELSA)",
    "chelsa_bio04": "Temp seasonality (CHELSA)",
    "chelsa_bio05": "Max temp warmest (CHELSA)",
    "chelsa_bio06": "Min temp coldest (CHELSA)",
    "chelsa_bio07": "Annual temp range (CHELSA)",
    "chelsa_bio08": "Temp wettest qtr (CHELSA)",
    "chelsa_bio09": "Temp driest qtr (CHELSA)",
    "chelsa_bio10": "Temp warmest qtr (CHELSA)",
    "chelsa_bio11": "Temp coldest qtr (CHELSA)",
    "chelsa_bio12": "Annual precip (CHELSA)",
    "chelsa_bio13": "Precip wettest mo (CHELSA)",
    "chelsa_bio14": "Precip driest mo (CHELSA)",
    "chelsa_bio15": "Precip seasonality (CHELSA)",
    "chelsa_bio16": "Precip wettest qtr (CHELSA)",
    "chelsa_bio17": "Precip driest qtr (CHELSA)",
    "chelsa_bio18": "Precip warmest qtr (CHELSA)",
    "chelsa_bio19": "Precip coldest qtr (CHELSA)",
    "era5land_ssrd": "Solar radiation (ERA5-Land)", "era5land_sp": "Surface pressure (ERA5-Land)",
    "gwa_ws100": "Wind speed 100m (GWA)", "cerra_ws100_iav": "Wind speed 100m variability (CERRA)",
}
# GLM coefficient plot (f2): NUTS-2 dummies collapse to their NUTS-1 macro-region.
COEF_LABELS = dict(VAR_LABELS)
COEF_LABELS.update({"nuts2_" + k.lower(): v[2] for k, v in NUTS2.items()})
COEF_LABELS["nuts2_itg1"] = "Sicilia"
# Variable-importance plots: NUTS-2 dummies keep their own region name.
IMP_LABELS = dict(VAR_LABELS)
IMP_LABELS.update({"nuts2_" + k.lower(): v[1] for k, v in NUTS2.items()})
IMP_LABELS["lulc_sparse"] = "Sparsely vegetated"

LULC_SEP_LABELS = ["Forest", "Grassland", "Shrubland", "Riparian", "Vegetated",
                   "Agriculture", "Developed", "Other lands"]

MODEL_NAMES = ["glm", "lasso", "xg", "rf", "nn"]          # caret list names
MODEL_DISPLAY = {"glm": "GLM", "lasso": "Lasso", "xg": "GBM", "rf": "RF", "nn": "NN"}
PRED_FILES = {"glm": "pred_logReg", "lasso": "pred_lasso", "xg": "pred_xg",
              "rf": "pred_randomForest", "nn": "pred_nn"}
TECHS = {"solar": "s", "wind": "w"}
