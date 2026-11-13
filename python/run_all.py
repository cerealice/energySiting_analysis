#!/usr/bin/env python3
"""Full pipeline runner — Python / scikit-learn port of run_all.R.

Usage (from the repository root):
    python python/run_all.py                 # main analysis (absence → plots)
    python python/run_all.py --setup         # one-time data prep first (skips existing outputs)
    python python/run_all.py --force-setup   # re-run every setup step
    python python/run_all.py --from modeling # resume from a given step
    python python/run_all.py --only spatial_cv

Environment variables:
    ES_ROOT    project root (default: repository root)   ≈ RSCRIPT_ROOT
    ES_OUT     analysis outputs (default: derived/py)
    ES_FIG     figures          (default: fig/python)
    ES_N_JOBS  parallel workers (LSB_DJOB_NUMPROC / SLURM_CPUS_PER_TASK also honoured)
    ES_SEED    random seed (default 42)
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from energysiting import config  # noqa: E402

MAIN = [
    # (step, module, outputs that let --setup-style skipping work; None = always run)
    ("tech", "energysiting.tech", [config.DERIVED / "solar_hull_existing.csv",
                                   config.DERIVED / "wind_hull_existing.csv"]),
    ("absence", "energysiting.absence", [config.OUT / "absence_solar.csv", config.OUT / "absence_wind.csv"]),
    ("zonal", "energysiting.zonal", None),
    ("modeling", "energysiting.modeling", None),
    ("performance", "energysiting.performance", None),
    ("spatial_cv", "energysiting.spatial_cv", None),
    ("sensitivity", "energysiting.sensitivity", None),   # leakage check: refit without Developed
    ("data", "energysiting.data", None),
    ("plot", "energysiting.plot", None),
]

V = config.VAR_PATH
SETUP = [
    # (step, outputs that mark it done; None = the step decides itself)
    ("make_base_raster", [config.BASE_RASTER]),
    # tech precedes the variables: the spatial lag is built from its pre-2017 rasters
    ("tech", None),                      # rebuilt unless built with the current location method
    ("make_variables_italy", [V / f for f in ("slope.tif", "pop_density.tif",
                                              "transmission_110_qgis.tif", "roads_qgis.tif")]),
    ("make_substations", None),          # rebuilt unless built with the power-area OSM config
    ("make_spatial_lag", None),          # rebuilt unless built with the current method
    ("make_socioeconomic", [V / f for f in ("svi_pov.tif", "svi_unemp.tif", "svi_foreignborn.tif")]),
    ("make_zenodo_socioeconomic", [V / "zenodo_gdp_pc.tif", V / "zenodo_inst_quality.tif"]),
    ("make_natura2000", [V / "env_impactScore_solar.tif", V / "env_impactScore_wind.tif"]),
    ("make_nuts2_regions", [V / f"{l}.tif" for l in config.NUTS2_LAYERS]),
    ("worldtensor", None),               # download (needs internet) unless manifest + files present
    ("make_worldtensor", None),          # rebuilds only layers whose source years changed
    ("make_chelsa", [V / f"{l}.tif" for l in config.CHELSA_LAYERS]),
    ("make_resource", [V / "solar_capacity.tif", V / "wind_capacity.tif", V / "gwa_ws100.tif"]),
    ("make_era5land", [V / f"{l}.tif" for l in config.ERA5LAND_LAYERS]),
    ("make_cerra", [V / "cerra_ws100_iav.tif"]),
    ("stack", None),                     # rebuilt when any input layer is newer
]


def inputs_of(step):
    """Files whose change invalidates a main-pipeline step's outputs."""
    if step == "absence":
        return [config.DERIVED / f"{t}_hull_existing{s}" for t in ("solar", "wind")
                for s in (".csv", "_mask.tif")]
    return []


def fresh(outputs, inputs):
    ins = [p for p in inputs if p.exists()]
    return not ins or min(p.stat().st_mtime for p in outputs) >= max(p.stat().st_mtime for p in ins)


def stamp(msg):
    print(f"\n[{time.strftime('%H:%M:%S')}] ── {msg}", flush=True)


def run_module(name, module):
    stamp(f"Running: {name}")
    t0 = time.time()
    try:
        importlib.import_module(module).run()
    except Exception:
        print(f"\n  !! ERROR in {name} !!")
        traceback.print_exc()
        sys.exit(f"Pipeline stopped: error in '{name}'.")
    print(f"  [{name}] Done in {time.time() - t0:.0f}s")


def run_setup(force=False):
    for name, outputs in SETUP:
        module = "energysiting.tech" if name == "tech" else f"energysiting.setup.{name}"
        if name == "worldtensor":
            from energysiting.setup import worldtensor
            if worldtensor.ready():
                stamp("SKIP: worldtensor download (manifest and files present)")
                continue
            try:
                run_module_raw(module, "download")
            except Exception as e:  # noqa: BLE001
                sys.exit(f"WorldTensor inputs missing and download failed ({e}).\n"
                         "Run `python -m energysiting.setup.fetch` on a node with internet first.")
            continue
        if name == "tech" and not force:
            from energysiting import tech
            if tech.up_to_date():
                stamp(f"SKIP: tech (presence locations already built from '{tech.SOURCE}')")
                continue
        if name == "make_substations" and not force:
            from energysiting.setup import make_substations
            if make_substations.up_to_date():
                stamp("SKIP: make_substations (built with the power-area OSM config)")
                continue
        if name == "make_spatial_lag" and not force:
            from energysiting.setup import make_spatial_lag
            if make_spatial_lag.up_to_date():
                stamp("SKIP: make_spatial_lag (pre-2017 binary lag already built)")
                continue
        if name == "stack" and not force:
            from energysiting.setup import stack
            if stack.up_to_date():
                stamp(f"SKIP: stack (covStack.tif has {len(config.COV_LAYERS)} layers and is newer than its inputs)")
                continue
        if outputs and not force and all(p.exists() for p in outputs):
            stamp(f"SKIP: {name} ({len(outputs)}/{len(outputs)} outputs exist)")
            continue
        run_module(name, module)


def run_module_raw(module, func):
    stamp(f"Running: {module}.{func}")
    getattr(importlib.import_module(module), func)()


def build_docs():
    """docs/pipeline.html: what this version does + this run's results (never fails the run)."""
    try:
        from energysiting import docs
        stamp(f"Docs: {docs.build()}")
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: could not build docs/pipeline.html ({e})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--force-setup", action="store_true")
    ap.add_argument("--from", dest="start", choices=[s for s, *_ in MAIN])
    ap.add_argument("--only", choices=[s for s, *_ in MAIN])
    ap.add_argument("--docs", action="store_true", help="only (re)build docs/pipeline.html")
    a = ap.parse_args()
    config.ensure_dirs()
    if a.docs:
        build_docs()
        return

    print("═" * 59 + "\n  Italy Renewable Energy Siting Analysis — Python pipeline\n"
          f"  Root: {config.ROOT}\n  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n" + "═" * 59)
    t0 = time.time()
    if a.setup or a.force_setup:
        run_setup(force=a.force_setup)

    steps = MAIN
    if a.only:
        steps = [s for s in MAIN if s[0] == a.only]
    elif a.start:
        steps = MAIN[[s[0] for s in MAIN].index(a.start):]
    for name, module, outputs in steps:
        if name == "tech":
            if a.setup or a.force_setup:
                continue                  # already handled inside the setup sequence
            from energysiting import tech
            if not a.only and tech.up_to_date():
                stamp(f"SKIP: tech (presence locations already built from '{tech.SOURCE}')")
                continue
        if outputs and not a.only and not a.force_setup and all(p.exists() for p in outputs) \
                and fresh(outputs, inputs_of(name)):
            stamp(f"SKIP: {name} (outputs exist)")
            continue
        run_module(name, module)
    build_docs()
    el = time.time() - t0
    print("\n" + "═" * 59 + f"\n  Pipeline complete in {int(el // 60)}m {int(el % 60)}s\n" + "═" * 59)


if __name__ == "__main__":
    main()
