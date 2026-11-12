"""Solar and wind resource layers — replace the WorldClim 'capacity factor' proxies.

* Global Solar Atlas (Solargis / World Bank, CC BY 4.0): PVOUT, long-term
  photovoltaic power potential (kWh/kWp) → solar `cf` (solar_capacity.tif).
* Global Wind Atlas v3 (DTU / World Bank): ~250 m, ERA5 2008–2017 downscaled with
  WRF + WAsP — capacity factor of an IEC class II turbine at 100 m → wind `cf`
  (wind_capacity.tif), and mean wind speed at 100 m → gwa_ws100.tif.

The fine rasters are averaged onto the 1 km grid (resampling = average).

fetch() tries the atlases' download endpoints. If they change, it prints where
to download the files by hand and where to put them (a few minutes, no account).
"""
from __future__ import annotations

import zipfile

from .. import config

DIR = config.RAW / "resource"
FILES = {
    "pvout": DIR / "GSA_Italy_PVOUT.tif",
    "gwa_cf": DIR / "GWA_ITA_capacity-factor_IEC2.tif",
    "gwa_ws100": DIR / "GWA_ITA_wind-speed_100m.tif",
}
# names the files have when downloaded by hand from the atlas websites
ORIGINAL = {
    "pvout": ["PVOUT.tif"],
    "gwa_cf": ["ITA_capacity-factor_IEC2.tif", "ITA_capacity_factor_IEC2.tif"],
    "gwa_ws100": ["ITA_wind-speed_100m.tif", "ITA_wind_speed_100m.tif"],
}


def path(key):
    """The file for `key`: the canonical name, or the website's original name."""
    for p in [FILES[key]] + [DIR / n for n in ORIGINAL[key]]:
        if p.exists():
            return p
    return FILES[key]
CANDIDATES = {
    "pvout": ["https://api.globalsolaratlas.info/download/Italy/Italy_GISdata_LTAy_AvgDailyTotals_GlobalSolarAtlas-v2_GEOTIFF.zip",
              "https://api.globalsolaratlas.info/download/Italy/Italy_GISdata_LTAy_YearlyMonthlyTotals_GlobalSolarAtlas-v2_GEOTIFF.zip"],
    "gwa_cf": ["https://globalwindatlas.info/api/gis/country/ITA/capacity-factor_IEC2",
               "https://globalwindatlas.info/api/gis/country/ITA/capacity-factor/IEC2"],
    "gwa_ws100": ["https://globalwindatlas.info/api/gis/country/ITA/wind-speed/100"],
}
MANUAL = {
    "pvout": "https://globalsolaratlas.info/download/italy → 'GIS data', LTAym YearlyMonthlyTotals GeoTIFF; "
             "take the yearly PVOUT.tif from the zip",
    "gwa_cf": "open https://globalwindatlas.info/api/gis/country/ITA/capacity-factor_IEC2 in a browser",
    "gwa_ws100": "open https://globalwindatlas.info/api/gis/country/ITA/wind-speed/100 in a browser",
}


def _get(url, dest):
    import requests
    r = requests.get(url, timeout=600, allow_redirects=True)
    r.raise_for_status()
    head = r.content[:4]
    if head[:2] == b"PK":                                   # zip: pull out the PVOUT GeoTIFF
        tmp = dest.with_suffix(".zip")
        tmp.write_bytes(r.content)
        with zipfile.ZipFile(tmp) as z:
            name = next(n for n in z.namelist() if n.upper().endswith("PVOUT.TIF"))
            dest.write_bytes(z.read(name))
        tmp.unlink()
    elif head in (b"II*\x00", b"MM\x00*"):                  # GeoTIFF
        dest.write_bytes(r.content)
    else:
        raise ValueError("response is not a GeoTIFF or zip")


def fetch():
    DIR.mkdir(parents=True, exist_ok=True)
    problems = []
    for key, dest in FILES.items():
        if path(key).exists():
            print(f"  ok        {path(key).relative_to(config.ROOT)}")
            continue
        for url in CANDIDATES[key]:
            try:
                _get(url, dest)
                print(f"  downloaded {dest.name} ← {url}")
                break
            except Exception as e:  # noqa: BLE001
                print(f"  {key}: {url} failed ({e})")
        if not dest.exists():
            problems.append(f"download by hand: {MANUAL[key]}\n      save in {DIR.relative_to(config.ROOT)}/")
    return problems


def ready():
    return all(path(k).exists() for k in FILES)


def run():
    from ._geo import base, save_var, snap
    config.ensure_dirs()
    if not ready():
        raise SystemExit("Resource atlases missing — run `python -m energysiting.setup.fetch` on a login node")
    b = base()
    save_var(snap(path("pvout"), "average", b=b), "solar_capacity.tif", b)
    save_var(snap(path("gwa_cf"), "average", b=b), "wind_capacity.tif", b)
    save_var(snap(path("gwa_ws100"), "average", b=b), "gwa_ws100.tif", b)


if __name__ == "__main__":
    run()
