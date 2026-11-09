#!/usr/bin/env python3
"""
Download selected WorldTensor variables from Zenodo (DOI 10.5281/zenodo.19047618).

WorldTensor is stored as domain-level ZIP archives on Zenodo. This script uses
HTTP range requests (via remotezip) to extract only the specific .nc files needed
without downloading the full archives (climate.zip alone is 35 GB).

Variables extracted:
  - ERA5 climate      (2000-2020, 24 variables)  from worldtensor_climate.zip
  - LUH3 land-use    (year 2020,  12 variables)  from worldtensor_land_use.zip
  - MODIS NDVI        (2003-2020,   1 variable)   from worldtensor_vegetation.zip

Requires: pip install remotezip

Usage (run from project root):
    python syntax/download_worldtensor.py              # extract everything missing
    python syntax/download_worldtensor.py --list       # list intended paths, no network
    python syntax/download_worldtensor.py --dry-run    # extract one file as a test
    python syntax/download_worldtensor.py --workers 2  # parallel workers (default: 2)
"""

import argparse
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    from remotezip import RemoteZip
except ImportError:
    raise SystemExit(
        "remotezip is required.  Install with:  python -m pip install remotezip"
    )

# ── Zenodo record ──────────────────────────────────────────────────────────────
ZENODO_RECORD = "19047618"
_BASE = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files"
OUT_DIR = Path("data/raw_downloads/worldtensor")

# Domain prefix -> Zenodo ZIP URL
ZIP_URLS = {
    "climate":    f"{_BASE}/worldtensor_climate.zip/content",
    "land_use":   f"{_BASE}/worldtensor_land_use.zip/content",
    "vegetation": f"{_BASE}/worldtensor_vegetation.zip/content",
}

# ── Variables ─────────────────────────────────────────────────────────────────

ERA5_VARS = [
    # Temperature
    "t2m_mean", "t2m_max", "t2m_min", "t2m_std",
    "d2m_mean",           # dewpoint
    # Precipitation & water cycle
    "tp_sum",             # total precipitation
    "cp_sum",             # convective precipitation
    "sf_sum",             # snowfall
    "e_sum",              # evaporation
    "pev_sum",            # potential evaporation
    "ro_sum",             # runoff
    # Wind (10 m and 100 m -- 100 m = standard hub height for wind turbines)
    "u10_mean", "v10_mean",
    "u100_mean", "v100_mean",
    "i10fg_mean",         # 10 m instantaneous wind gust
    # Radiation
    "ssrd_sum",           # surface solar radiation downwelling
    "ssr_sum",            # surface net solar radiation
    "cdir_sum",           # clear-sky direct solar at surface
    "ssrdc_sum",          # clear-sky solar radiation downwelling
    # Cloud & atmosphere
    "tcc_mean",           # total cloud cover
    "blh_mean",           # planetary boundary layer height
    "sp_mean",            # surface pressure (affects air density -> wind power)
    "cape_mean",          # convective available potential energy
]
ERA5_YEARS = range(2000, 2021)   # 21 years

LUH3_VARS = [
    "primf", "primn",          # primary forest / non-forest
    "secdf", "secdn",          # secondary forest / non-forest
    "pastr", "range", "urban", # managed land
    "c3ann", "c4ann",          # annual crops (C3/C4)
    "c3per", "c4per",          # perennial crops
    "c3nfx",                   # nitrogen-fixing crops
]
LUH3_YEAR = 2020

NDVI_YEARS = range(2003, 2021)  # MODIS Terra available from 2003


# ── Build task list ───────────────────────────────────────────────────────────

def build_tasks():
    """Return list of (zip_url, zip_internal_key, local_dest) tuples."""
    tasks = []
    for var in ERA5_VARS:
        for yr in ERA5_YEARS:
            key = f"climate/{var}/{yr}.nc"
            tasks.append((ZIP_URLS["climate"], key, OUT_DIR / key))
    for var in LUH3_VARS:
        key = f"land_use/states/{var}/{LUH3_YEAR}.nc"
        tasks.append((ZIP_URLS["land_use"], key, OUT_DIR / key))
    for yr in NDVI_YEARS:
        key = f"vegetation/ndvi_mean/{yr}.nc"
        tasks.append((ZIP_URLS["vegetation"], key, OUT_DIR / key))
    return tasks


# ── Retry-aware HTTP session ──────────────────────────────────────────────────
# Intercepts 429 responses at the HTTP level, before remotezip raises an error.
# This is transparent to remotezip — it just sees a successful response after
# the backoff sleep.

class _RetrySession(requests.Session):
    def send(self, request, **kwargs):
        for attempt in range(10):
            response = super().send(request, **kwargs)
            if response.status_code != 429:
                return response
            # Honour Retry-After if present, else use exponential backoff
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after else min(2 ** attempt * 15, 300)
            print(f"\n  [429] sleeping {wait}s before retry {attempt + 1}/10 ...",
                  flush=True)
            time.sleep(wait)
        return response  # return whatever we have after all retries


# Thread-local session so each worker thread has its own connection pool
_tl = threading.local()


def _get_session() -> _RetrySession:
    if not hasattr(_tl, "session"):
        _tl.session = _RetrySession()
    return _tl.session


# ── ZIP index cache (central directory read once globally per ZIP) ────────────

_index_cache: dict = {}
_index_lock  = threading.Lock()


def zip_index(zip_url: str) -> set:
    with _index_lock:
        if zip_url not in _index_cache:
            with RemoteZip(zip_url, session=_get_session()) as z:
                _index_cache[zip_url] = set(z.namelist())
    return _index_cache[zip_url]


# ── Worker: open one RemoteZip, extract an entire chunk ───────────────────────
# Opening RemoteZip once per chunk means the ZIP central directory (a few KB of
# range-request data) is fetched ONCE per worker, not once per file.

def process_chunk(zip_url: str, chunk: list) -> list:
    """
    Extract all (key, dest) pairs from zip_url using a single open RemoteZip.
    Returns list of ("OK  " | "SKIP" | "ERR ", key_or_message).
    """
    results = []
    session = _get_session()

    with RemoteZip(zip_url, session=session) as z:
        for key, dest in chunk:
            if dest.exists():
                results.append(("SKIP", key))
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")

            try:
                data = z.read(key)
                tmp.write_bytes(data)
                if dest.exists():       # Windows: rename fails if dest exists
                    dest.unlink()
                tmp.rename(dest)
                results.append(("OK  ", key))
            except Exception as exc:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                results.append(("ERR ", f"{key}: {exc}"))

    return results


def _split(lst: list, n: int) -> list:
    """Split lst into n roughly-equal chunks (fewer if len(lst) < n)."""
    n = max(1, min(n, len(lst)))
    size = (len(lst) + n - 1) // n
    return [lst[i:i + size] for i in range(0, len(lst), size)]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract WorldTensor .nc files from Zenodo ZIPs via HTTP range requests"
    )
    parser.add_argument("--list",    action="store_true",
                        help="Print intended file paths and exit (no network)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract one file to verify connectivity, then exit")
    parser.add_argument("--workers", type=int, default=2,
                        help="Parallel workers per ZIP archive (default: 2)")
    args = parser.parse_args()

    tasks = build_tasks()

    if args.list:
        print(f"Intended files ({len(tasks)} total):")
        for _, key, _ in tasks:
            print(f"  {key}")
        return

    if args.dry_run:
        zip_url, key, dest = next((u, k, d) for u, k, d in tasks if not d.exists())
        print(f"Dry-run: extracting {key} ...")
        result = process_chunk(zip_url, [(key, dest)])
        status, info = result[0]
        print(f"  Status: {status.strip()}  ({info})")
        return

    # ── Filter to files not yet on disk ───────────────────────────────────────
    to_dl   = [(u, k, d) for u, k, d in tasks if not d.exists()]
    skipped = len(tasks) - len(to_dl)
    print(f"Tasks: {len(tasks)}  |  Already on disk: {skipped}  |  To extract: {len(to_dl)}")

    if not to_dl:
        print("Nothing to download -- all files already present.")
        return

    # ── Read ZIP central directories (once per archive, globally) ─────────────
    unique_zips = {u for u, _, _ in to_dl}
    print(f"\nReading {len(unique_zips)} ZIP central "
          f"director{'y' if len(unique_zips) == 1 else 'ies'} ...")
    for zip_url in sorted(unique_zips):
        name = zip_url.split("/")[-2]
        print(f"  {name} ...", end="", flush=True)
        idx = zip_index(zip_url)
        print(f" {len(idx):,} entries")

    # Remove files absent from their ZIP (e.g. years not in the record)
    valid  = [(u, k, d) for u, k, d in to_dl if k in zip_index(u)]
    absent = [(u, k, d) for u, k, d in to_dl if k not in zip_index(u)]
    if absent:
        print(f"  Absent from ZIP ({len(absent)}): "
              + ", ".join(k for _, k, _ in absent[:5])
              + ("..." if len(absent) > 5 else ""))
    to_dl = valid

    if not to_dl:
        print("Nothing to extract after filtering.")
        return

    # ── Group by ZIP, split each group into chunks for parallel workers ────────
    # Each worker opens the ZIP *once* per chunk (central dir read per worker,
    # not per file), which greatly reduces the number of range requests.
    zip_groups: dict = defaultdict(list)
    for u, k, d in to_dl:
        zip_groups[u].append((k, d))

    all_chunks = []
    for zip_url, pairs in zip_groups.items():
        for chunk in _split(pairs, args.workers):
            all_chunks.append((zip_url, chunk))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = ok = err = 0
    t0 = time.time()
    total = len(to_dl)

    print(f"\nExtracting {total} files across {len(all_chunks)} worker chunks"
          f"  (workers={args.workers})\n")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        future_map = {ex.submit(process_chunk, u, chunk): chunk
                      for u, chunk in all_chunks}

        for fut in as_completed(future_map):
            try:
                results = fut.result()
            except Exception as e:
                # chunk-level failure (RemoteZip open failed, etc.)
                chunk = future_map[fut]
                for key, _ in chunk:
                    done += 1; err += 1
                    print(f"  [{done:>4}/{total}] ERR  {key}: {e}")
                continue

            for status, info in results:
                done += 1
                if status == "OK  ":
                    ok += 1
                    elapsed = time.time() - t0
                    rate = ok / elapsed if elapsed > 0 else 0
                    eta  = (total - done) / rate if rate > 0 else 0
                    print(f"  [{done:>4}/{total}] {status} {info}"
                          f"  ({rate:.1f}/s, ETA {eta/60:.0f}m)")
                elif status == "ERR ":
                    err += 1
                    print(f"  [{done:>4}/{total}] {status} {info}")
                # SKIP: silent

    print(f"\nDone.  OK={ok}  errors={err}  skipped={skipped}")
    if err:
        print("  Re-run to retry failed files (already-extracted files are skipped).")
    print("Next: source('syntax/make_worldtensor.R')")


if __name__ == "__main__":
    main()
