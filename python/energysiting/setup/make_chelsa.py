"""CHELSA v2.1 bioclimatic variables BIO1–BIO19 (1981–2010, 30″ ≈ 1 km) — replaces WorldClim.

CHELSA uses the same 19 BIO definitions as WorldClim but a more recent baseline
(1981–2010 vs 1970–2000) and terrain-aware downscaling, which matters in the Alps
and Apennines.

fetch() (login node): reads only the Italy window of each global GeoTIFF over
HTTP range requests (GDAL /vsicurl/) and stores it under data/raw_downloads/chelsa/;
falls back to a full download when range reads are refused.
run(): snaps the crops to the 1 km base grid → chelsa_bioNN.tif.
"""
from __future__ import annotations

import numpy as np

from .. import config

URL = ("https://os.zhdk.cloud.switch.ch/envicloud/chelsa/chelsa_V2/GLOBAL/climatologies/"
       "1981-2010/bio/CHELSA_bio{n}_1981-2010_V.2.1.tif")
DIR = config.RAW / "chelsa"
WINDOW = (6.0, 35.5, 19.0, 48.0)          # lon/lat box around Italy (W, S, E, N)


def crop_path(n):
    return DIR / f"CHELSA_bio{n}_1981-2010_V.2.1_IT.tif"


def _crop(src_path, dest):
    import rasterio
    from rasterio.windows import from_bounds
    with rasterio.open(src_path) as src:
        win = from_bounds(*WINDOW, transform=src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win, masked=True).astype("float32")
        scale = (src.scales or (1.0,))[0] or 1.0
        offset = (src.offsets or (0.0,))[0] or 0.0
        a = (a * scale + offset).filled(np.nan)          # physical units (°C, mm, …)
        prof = dict(driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype="float32",
                    crs=src.crs, transform=src.window_transform(win), nodata=np.nan, compress="deflate")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dest, "w", **prof) as dst:
        dst.write(a, 1)


def fetch():
    import rasterio
    from ._geo import download
    missing = [n for n in range(1, 20) if not crop_path(n).exists()]
    if not missing:
        print("  ok        CHELSA BIO1–19 (Italy crops)")
        return
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5",
                      GDAL_HTTP_RETRY_DELAY="10", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        for n in missing:
            url = URL.format(n=n)
            try:
                _crop(f"/vsicurl/{url}", crop_path(n))
                print(f"  CHELSA bio{n}: Italy window read remotely")
            except Exception as e:  # noqa: BLE001
                print(f"  CHELSA bio{n}: range read failed ({e}); downloading the global file")
                full = download(url, DIR / f"CHELSA_bio{n}_1981-2010_V.2.1.tif")
                _crop(full, crop_path(n))
                full.unlink()


def ready():
    return all(crop_path(n).exists() for n in range(1, 20))


def run():
    from ._geo import base, save_var, snap
    config.ensure_dirs()
    if not ready():
        raise SystemExit("CHELSA crops missing — run `python -m energysiting.setup.fetch` on a login node")
    b = base()
    for n in range(1, 20):
        save_var(snap(crop_path(n), "bilinear", b=b), f"chelsa_bio{n:02d}.tif", b)


if __name__ == "__main__":
    run()
