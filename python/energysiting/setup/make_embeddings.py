"""Geospatial embeddings → a separate stack of principal components (embStack.tif).

Products (through crp94/geospatial_embeddings_wrapper, one 1 km value per cell):

  key            encoder           what it encodes                              detail     year
  geoclip        geoclip           location ↔ ground-level Flickr photos        continuous fixed
  rangeplus      range_plus        location ↔ Sentinel-2 patches (SatCLIP) + DB  ~2.5 km   fixed
  copernicus     copernicus_embed  Copernicus-FM map (Sentinel-1/2/3/5P)         0.25°     2021
  terranova2016  terranova         TerraNova spatiotemporal (WorldTensor fields) 0.25°     2016
  terranova2024  terranova         idem                                          0.25°     2024
  tessera2017    tessera           Sentinel-1/2 time series, per pixel           10 m      2017
  tessera2024    tessera           idem                                          10 m      2024

The 0.25° products are queried on the 0.25° nodes around Italy and bilinearly
interpolated to the 1 km cell centres (their information is at 25 km anyway);
the others are queried at every 1 km cell centre. Tessera is opt-in
(ES_EMB_TESSERA=1): it downloads Sentinel tiles for all of Italy (hundreds of GB;
point ES_EMB_CACHE at a scratch disk).

Each product is reduced to ES_EMB_K (16) principal components, fitted on all
Italian cells; the explained variance is recorded in derived/embStack.json.
These layers are NOT in the main models (config.model_vars): the sensitivity
step adds them one product at a time, so their value and any leakage
(2016/2017 vs 2024: before vs after most plants) can be judged.

fetch() (login node, internet): installs nothing, but instantiates every encoder so
model weights / rasters / Tessera tiles are cached, and computes the embeddings
of the downloading products. run() (job, offline): computes what is left, PCA,
writes derived/embStack.tif.

Raw embeddings are cached in data/raw_downloads/embeddings/<key>.npy (float16).
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import numpy as np

from .. import config, raster

DIR = config.RAW / "embeddings"
CACHE = Path(os.environ.get("ES_EMB_CACHE", DIR / "cache"))
# model weights from the Hugging Face Hub: keep them with the project so the
# offline job finds what the login node downloaded
os.environ.setdefault("HF_HOME", str(CACHE / "huggingface"))

PRODUCTS = {
    "geoclip": ("geoclip", None, "cells"),
    "rangeplus": ("range_plus", None, "cells"),
    "copernicus": ("copernicus_embed", None, "cells"),
    "terranova2016": ("terranova", 2016, "nodes"),
    "terranova2024": ("terranova", 2024, "nodes"),
    "tessera2017": ("tessera", 2017, "cells"),
    "tessera2024": ("tessera", 2024, "cells"),
}
# products that need internet while embedding (they fetch data per query) → done in fetch()
ONLINE = {"tessera2017", "tessera2024"}
K = int(os.environ.get("ES_EMB_K", "16"))
STACK = config.DERIVED / "embStack.tif"
META = config.DERIVED / "embStack.json"
NODE_BOX = (6.0, 19.0, 35.5, 47.5)       # lon min/max, lat min/max (0.25° nodes)
BATCH = 50_000


def selected():
    default = "geoclip,rangeplus,copernicus,terranova2016,terranova2024"
    if os.environ.get("ES_EMB_TESSERA", "0") == "1":
        default += ",tessera2017,tessera2024"
    keys = [k.strip() for k in os.environ.get("ES_EMBEDDINGS", default).split(",") if k.strip()]
    bad = [k for k in keys if k not in PRODUCTS]
    if bad:
        raise SystemExit(f"ES_EMBEDDINGS: unknown product(s) {bad}; choose from {list(PRODUCTS)}")
    return keys


def layer_names(key):
    return [f"emb_{key}_{i + 1:02d}" for i in range(K)]


@contextlib.contextmanager
def _in_cache():
    """The wrapper caches under ./data_cache relative to the working directory."""
    CACHE.mkdir(parents=True, exist_ok=True)
    old = os.getcwd()
    os.chdir(CACHE)
    try:
        yield
    finally:
        os.chdir(old)


RANGE_REPO = CACHE / "data_cache" / "external" / "RANGE"
RANGE_ZIP = "https://github.com/mvrl/RANGE/archive/refs/heads/main.zip"


def _range_repo():
    """RANGE+ needs the mvrl/RANGE code. The wrapper clones it with git, which fails
    on clusters whose git has no CA bundle and on offline compute nodes: download
    the zip with requests (certifi) on the login node and point RANGE_REPO at it."""
    if not (RANGE_REPO / "README.md").exists() and not any(RANGE_REPO.glob("*.py")):
        import io
        import shutil
        import zipfile

        import requests
        print("  downloading the RANGE code (zip) …", flush=True)
        r = requests.get(RANGE_ZIP, timeout=300)
        r.raise_for_status()
        tmp = RANGE_REPO.parent / ".RANGE_unzip"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(tmp)
        top = next(tmp.iterdir())                        # RANGE-main/
        shutil.rmtree(RANGE_REPO, ignore_errors=True)
        RANGE_REPO.parent.mkdir(parents=True, exist_ok=True)
        top.replace(RANGE_REPO)
        shutil.rmtree(tmp, ignore_errors=True)
    os.environ["RANGE_REPO"] = str(RANGE_REPO)


def _encoder(name):
    try:
        from wrappers.registry import get_encoder_class
    except ImportError as e:
        raise SystemExit(
            "geospatial_embeddings_wrapper is not installed. On the login node run:\n"
            "  pip install -r python/requirements-embeddings.txt") from e
    if name == "range_plus":
        _range_repo()
    with _in_cache():
        return get_encoder_class(name)(device="cuda" if _cuda() else "cpu")


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def cell_lonlat(b=None):
    """lon/lat of every Italian 1 km cell centre (row-major order of the base grid)."""
    from pyproj import Transformer
    b = b or raster.read(config.BASE_RASTER)
    rr, cc = np.nonzero(np.isfinite(b.band()))
    x, y = b.grid.xy_of_cells(rr, cc)
    lon, lat = Transformer.from_crs(f"EPSG:{config.EPSG}", "EPSG:4326", always_xy=True).transform(x, y)
    return np.column_stack([lon, lat]), (rr, cc)


def _nodes():
    lons = np.arange(NODE_BOX[0], NODE_BOX[1] + 1e-9, 0.25)
    lats = np.arange(NODE_BOX[2], NODE_BOX[3] + 1e-9, 0.25)
    LON, LAT = np.meshgrid(lons, lats)
    return lons, lats, np.column_stack([LON.ravel(), LAT.ravel()])


def _encode(enc, lonlat, year):
    import torch
    out = []
    with _in_cache():
        for s in range(0, len(lonlat), BATCH):
            latlon = torch.as_tensor(lonlat[s:s + BATCH][:, ::-1].copy(), dtype=torch.float32)  # as the wrapper's own CLI
            e = enc.encode(latlon, year=year) if year is not None else enc.encode(latlon)
            out.append(np.asarray(e.detach().cpu().numpy(), dtype=np.float32))
            print(f"    {min(s + BATCH, len(lonlat)):,}/{len(lonlat):,}", flush=True)
    return np.concatenate(out)


def _interp_nodes(lons, lats, emb_nodes, lonlat):
    """Bilinear interpolation of node embeddings to cell centres (NaN-aware)."""
    from scipy.interpolate import RegularGridInterpolator
    E = emb_nodes.reshape(len(lats), len(lons), -1)
    f = RegularGridInterpolator((lats, lons), E, method="linear", bounds_error=False, fill_value=np.nan)
    out = f(lonlat[:, ::-1])
    bad = ~np.isfinite(out).all(axis=1)
    if bad.any():                                   # nodes over sea are NaN for some products
        g = RegularGridInterpolator((lats, lons), E, method="nearest", bounds_error=False, fill_value=np.nan)
        out[bad] = g(lonlat[bad, ::-1])
    return out.astype(np.float32)


def raw_path(key):
    return DIR / f"{key}.npy"


def compute(key, lonlat=None, enc_cache=None):
    """Embeddings of one product at every Italian cell → data/raw_downloads/embeddings/<key>.npy"""
    p = raw_path(key)
    if p.exists():
        print(f"  ok        embeddings {key} (cached)")
        return
    name, year, query = PRODUCTS[key]
    if lonlat is None:
        lonlat, _ = cell_lonlat()
    enc_cache = {} if enc_cache is None else enc_cache
    if name not in enc_cache:
        print(f"  loading encoder {name} …", flush=True)
        enc_cache[name] = _encoder(name)
    enc = enc_cache[name]
    print(f"  embedding {key}: {name}, year {year or '–'}, query at {query}", flush=True)
    if query == "nodes":
        lons, lats, nodes = _nodes()
        e = _interp_nodes(lons, lats, _encode(enc, nodes, year), lonlat)
    else:
        e = _encode(enc, lonlat, year)
    DIR.mkdir(parents=True, exist_ok=True)
    np.save(p, e.astype(np.float16))
    print(f"  saved {p.relative_to(config.ROOT)}  {e.shape}  NaN rows {int((~np.isfinite(e).all(1)).sum()):,}")


def fetch():
    """Login node: cache every model / raster, and embed the products that need internet."""
    problems = []
    keys = selected()
    if all(raw_path(k).exists() for k in keys):
        print(f"  ok        embeddings ({', '.join(keys)})")
        return problems
    try:
        lonlat, _ = cell_lonlat()
    except FileNotFoundError:
        return ["embeddings: build the base raster first (python python/run_all.py --setup) "
                "or let the job compute them — only Tessera must be embedded here"]
    encs = {}
    for k in keys:
        name, year, _ = PRODUCTS[k]
        try:
            if k in ONLINE:
                compute(k, lonlat, encs)
            elif not raw_path(k).exists():
                if name not in encs:
                    print(f"  caching encoder {name} …", flush=True)
                    encs[name] = _encoder(name)
                _encode(encs[name], np.array([[12.5, 41.9]]), year)     # forces raster/weights download
                print(f"  ok        {name} cached (embedded in the job)")
        except SystemExit as e:
            return [str(e)]
        except Exception as e:  # noqa: BLE001
            problems.append(f"embeddings {k}: {e}")
    return problems


def ready():
    keys = selected()
    return all(raw_path(k).exists() for k in keys if k in ONLINE)


def up_to_date():
    if not (STACK.exists() and META.exists()):
        return False
    m = json.loads(META.read_text())
    return (m.get("products") == selected() and m.get("k") == K
            and STACK.stat().st_mtime >= config.BASE_RASTER.stat().st_mtime)


def run():
    from sklearn.decomposition import PCA
    config.ensure_dirs()
    keys = selected()
    if not keys:
        print("  no embedding products selected (ES_EMBEDDINGS is empty)")
        return
    b = raster.read(config.BASE_RASTER)
    lonlat, (rr, cc) = cell_lonlat(b)
    if any(not raw_path(k).exists() for k in keys):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    encs, layers, names, meta = {}, [], [], {"products": keys, "k": K, "explained_variance": {}}
    for k in keys:
        if k in ONLINE and not raw_path(k).exists():
            raise SystemExit(f"embeddings {k} need internet — run `python -m energysiting.setup.fetch` "
                             "on the login node first")
        try:
            compute(k, lonlat, encs)
        except (SystemExit, Exception) as e:  # noqa: BLE001 — embeddings are optional
            print(f"  WARNING: embeddings {k} skipped: {e}")
            continue
        e = np.load(raw_path(k)).astype(np.float32)
        ok = np.isfinite(e).all(axis=1)
        pca = PCA(n_components=min(K, e.shape[1]), random_state=config.SEED).fit(e[ok])
        pcs = np.full((len(e), pca.n_components_), np.nan, np.float32)
        pcs[ok] = pca.transform(e[ok])
        ev = pca.explained_variance_ratio_
        meta["explained_variance"][k] = {"dim": int(e.shape[1]), "cells_ok": float(ok.mean()),
                                         "per_pc": ev.round(4).tolist(), "total": round(float(ev.sum()), 4)}
        print(f"  {k}: {e.shape[1]}-d → {pca.n_components_} PCs explain {ev.sum():.1%}; "
              f"cells with values {ok.mean():.1%}")
        for i in range(pca.n_components_):
            a = np.full(b.grid.shape, np.nan, np.float32)
            a[rr, cc] = pcs[:, i]
            layers.append(a)
        names += layer_names(k)[:pca.n_components_]
    if not layers:
        print("  WARNING: no embedding product could be computed — embStack.tif not written")
        return
    meta["products"] = [k for k in keys if any(nm.startswith(f"emb_{k}_") for nm in names)]
    raster.write(STACK, np.stack(layers), b.grid, names)
    meta["layers"] = names
    META.write_text(json.dumps(meta, indent=1))
    print(f"  saved {STACK.relative_to(config.ROOT)} ({len(names)} layers)")


def load():
    """(Raster, names) of the embedding stack, or None if it was not built."""
    if not (STACK.exists() and META.exists()):
        return None
    names = json.loads(META.read_text())["layers"]
    return raster.read(STACK, names=names)


if __name__ == "__main__":
    run()
