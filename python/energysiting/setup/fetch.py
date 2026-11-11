"""Download every raw input the setup steps need — run on a node WITH internet.

Compute nodes on most clusters cannot reach the internet, so ``run_all.sh``
calls this on the login node before submitting the job. Every file lands
exactly where the setup scripts look for it, and the setup scripts skip
downloads that are already on disk, so the batch job then runs fully offline.

    python -m energysiting.setup.fetch            # download what is missing
    python -m energysiting.setup.fetch --check    # only report what is missing

Sizes (approx.): WorldClim bio 9.7 GB, srad 2.6 GB, wind 0.7 GB, OSM Italy PBF
2.2 GB, GISCO communes 0.3 GB, WorldTensor subset 0.9 GB, others < 0.5 GB.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from .. import config
from ._geo import CACHE, GISCO, download
from .make_natura2000 import SHP as NATURA_SHP
from .make_variables_italy import DEM_URL, LC_URL, LULC_MAP, PBF_URL, POP_URL, WC_URL

R = config.RAW

GISCO_FILES = {
    "countries": ["CNTR_RG_03M_2020_3035.geojson"],
    "nuts": ["NUTS_RG_03M_2021_3035_LEVL_1.geojson", "NUTS_RG_03M_2021_3035_LEVL_2.geojson",
             "NUTS_RG_03M_2016_3035_LEVL_2.geojson", "NUTS_RG_03M_2016_3035_LEVL_3.geojson",
             "NUTS_RG_03M_2006_3035_LEVL_3.geojson"],
    "communes": ["COMM_RG_01M_2016_3035.geojson"],
}


def targets():
    t = [(f"{GISCO}/{kind}/geojson/{fn}", CACHE / fn) for kind, fns in GISCO_FILES.items() for fn in fns]
    t += [
        (DEM_URL, R / "elevation" / "ITA_elv_msk.zip"),
        (POP_URL, R / "population" / POP_URL.rsplit("/", 1)[1]),
        (PBF_URL, R / "geofabrik_italy-latest.osm.pbf"),
    ]
    t += [(WC_URL.format(var=v), R / "worldclim" / f"wc2.1_30s_{v}.zip") for v in ("bio", "srad", "wind")]
    t += [(LC_URL.format(var=v), R / "landuse" / f"WorldCover_{v}_30s.tif") for v in LULC_MAP.values()]
    return t


# Inputs that ship with the git repository (no download needed)
REPO_INPUTS = [
    config.DATA / "Global-Solar-Power-Tracker-February-2026.xlsx",
    config.DATA / "Global-Wind-Power-Tracker-February-2026.xlsx",
    R / "NUTS_3_DATA.csv",
    R / "Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.csv",
    R / "Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv",
    R / "Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv",
    R / "d__temp_fv_pot_comunale_2021.zip",
    R / "d__temp_eo_pot_comunale_2019.zip",
]


def worldtensor_complete():
    probe = [R / "worldtensor" / p for p in ("climate/t2m_mean/2010.nc", "climate/ssrd_sum/2010.nc",
                                             "land_use/states/urban/2020.nc", "vegetation/ndvi_mean/2010.nc")]
    return all(p.exists() for p in probe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report missing inputs, download nothing")
    a = ap.parse_args()

    problems = []
    for p in REPO_INPUTS:
        if not p.exists():
            problems.append(f"missing from the git checkout: {p.relative_to(config.ROOT)}")

    for url, dest in targets():
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  ok        {dest.relative_to(config.ROOT)}")
        elif a.check:
            problems.append(f"not downloaded yet: {dest.relative_to(config.ROOT)}")
        else:
            download(url, dest)

    if not worldtensor_complete():
        if a.check:
            problems.append("WorldTensor NetCDFs not downloaded yet")
        else:
            print("  downloading WorldTensor subset (syntax/download_worldtensor.py)")
            r = subprocess.run([sys.executable, "syntax/download_worldtensor.py", "--workers", "2"],
                               cwd=config.ROOT)
            if r.returncode != 0 or not worldtensor_complete():
                problems.append("WorldTensor download incomplete — re-run this step")

    if not NATURA_SHP.exists():
        problems.append(
            "EEA Natura 2000 (end-2024, EPSG:3035) must be downloaded manually (~2.4 GB):\n"
            "      https://www.eea.europa.eu/en/datahub/datahubitem-view/6fc8ad2d-195d-40f4-bdec-576e7d1268b4\n"
            f"      unzip so that this file exists: {NATURA_SHP.relative_to(config.ROOT)}")

    if problems:
        print("\nNOT READY:\n  - " + "\n  - ".join(problems))
        sys.exit(1)
    print("\nAll raw inputs present — the batch job can run offline.")


if __name__ == "__main__":
    main()
