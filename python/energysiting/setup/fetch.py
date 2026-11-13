"""Download every raw input the setup steps need — run on a node WITH internet.

Compute nodes on most clusters cannot reach the internet, so ``run_all.sh``
calls this on the login node before submitting the job. Every file lands
exactly where the setup scripts look for it, and the setup scripts skip
downloads that are already on disk, so the batch job then runs fully offline.

    python -m energysiting.setup.fetch            # download what is missing
    python -m energysiting.setup.fetch --check    # only report what is missing

Sizes (approx.): CERRA ~17 GB transferred but ~0.3 GB kept, CHELSA Italy crops ~0.2 GB,
Global Solar/Wind Atlas Italy ~0.5 GB, ERA5-Land < 0.1 GB, OSM Italy PBF
2.2 GB, GISCO communes 0.3 GB, WorldTensor selection ~0.5 GB, others < 0.5 GB.
"""
from __future__ import annotations

import argparse
import os
import sys

from .. import config
from ._geo import CACHE, GISCO, download
from .make_natura2000 import SHP as NATURA_SHP
from .make_variables_italy import DEM_URL, LC_URL, LULC_MAP, PBF_URL, POP_URL

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

    from . import worldtensor
    if worldtensor.ready():
        m = worldtensor.load_manifest()["layers"]
        print(f"  ok        WorldTensor: {len(m)} layers, latest {config.WT_YEARS} years each (manifest)")
    elif a.check:
        problems.append("WorldTensor selection not downloaded yet (python -m energysiting.setup.worldtensor)")
    else:
        print("  WorldTensor: resolving the latest years in the archives and extracting ...")
        worldtensor.download()

    # climate & resource sources (CHELSA, Global Solar/Wind Atlas, ERA5-Land, CERRA)
    from . import make_cerra, make_chelsa, make_era5land, make_resource
    from ._cds import HELP as CDS_HELP, has_credentials
    if a.check:
        for name, mod in (("CHELSA BIO1–19 Italy crops", make_chelsa), ("Global Solar/Wind Atlas", make_resource),
                          ("ERA5-Land monthly means", make_era5land), ("CERRA 100 m wind (60 months)", make_cerra)):
            if mod.ready():
                print(f"  ok        {name}")
            else:
                problems.append(f"not downloaded yet: {name}")
    else:
        make_chelsa.fetch()
        problems += make_resource.fetch() or []
        if has_credentials():
            for name, mod in (("ERA5-Land", make_era5land), ("CERRA", make_cerra)):
                try:
                    mod.fetch()
                except Exception as e:  # noqa: BLE001
                    problems.append(f"{name} download failed: {e}\n      (re-run this step to resume)")
        else:
            problems.append(CDS_HELP)

    # geospatial embeddings (NN only; optional — problems are reported, not blocking)
    from . import make_embeddings
    if a.check:
        print(f"  {'ok' if make_embeddings.ready() else 'missing'}   embeddings needing internet "
              "(Tessera, only with ES_EMB_TESSERA=1)")
    elif os.environ.get("ES_EMBEDDINGS", None) != "":
        for w in make_embeddings.fetch():
            print(f"  WARNING (optional, NN embeddings): {w}")

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
