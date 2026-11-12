"""Copernicus Climate Data Store access (ERA5-Land, CERRA)."""
from __future__ import annotations

import os
from pathlib import Path

HELP = """Copernicus Climate Data Store credentials are needed for ERA5-Land and CERRA:
  1. create a free account at https://cds.climate.copernicus.eu
  2. accept the licences on the 'Download' tab of both datasets (once):
       https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-monthly-means
       https://cds.climate.copernicus.eu/datasets/reanalysis-cerra-height-levels
  3. put your personal access token (profile page) in ~/.cdsapirc on the login node:
       url: https://cds.climate.copernicus.eu/api
       key: <your-token>"""


def has_credentials() -> bool:
    return (Path.home() / ".cdsapirc").exists() or bool(os.environ.get("CDSAPI_KEY"))


def client():
    if not has_credentials():
        raise RuntimeError(HELP)
    import cdsapi
    return cdsapi.Client(quiet=True, progress=False)
