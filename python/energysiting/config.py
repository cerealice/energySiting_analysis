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
COV_LAYERS = CONT_LAYERS + LULC_LAYERS + NUTS2_LAYERS          # 73 + 8 + 21 = 102
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
    "env": "Environmental score", "cf": "Capacity factor", "lag": "Spatial lag",
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
