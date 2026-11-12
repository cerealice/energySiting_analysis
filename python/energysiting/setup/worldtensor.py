"""WorldTensor download — replaces syntax/download_worldtensor.py for the Python pipeline.

Every layer in ``config.WT_CATALOG`` is resolved against the archive's own file
index, so the year window is whatever the archive really contains:

* time-varying variables → the latest ``ES_WT_YEARS`` (default 5) yearly files
  ``<domain>/<var>/<YYYY>.nc`` — e.g. ERA5 2021–2025, LUH3 2020–2024,
  CAMS air quality 2020–2024, nighttime lights 2014–2018;
* static variables → ``static/<group>/<var>.nc``.

Only the needed members are pulled out of the multi-GB Zenodo ZIPs with HTTP
range requests (remotezip). The resolved selection is written to
``data/raw_downloads/worldtensor/manifest.json``; make_worldtensor reads it, so
the batch job never needs the network.

    python -m energysiting.setup.worldtensor            # resolve + download
    python -m energysiting.setup.worldtensor --list     # show the resolved selection only
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict

from .. import config

RECORD = "19047618"
ZIP_URL = "https://zenodo.org/api/records/{rec}/files/worldtensor_{domain}.zip/content"
WT_DIR = config.RAW / "worldtensor"
MANIFEST = WT_DIR / "manifest.json"
_YEAR = re.compile(r"(\d{4})\.nc$")


def _session():
    import requests

    class RetrySession(requests.Session):          # Zenodo answers 429 when busy
        def send(self, request, **kw):
            for attempt in range(10):
                r = super().send(request, **kw)
                if r.status_code != 429:
                    return r
                wait = int(r.headers.get("Retry-After") or min(2 ** attempt * 15, 300))
                print(f"    [429] waiting {wait}s", flush=True)
                time.sleep(wait)
            return r
    return RetrySession()


def resolve(index_by_domain: dict, n_years: int = None) -> dict:
    """Pick archive members for every catalogue layer.
    index_by_domain: {domain: [member names]} → {layer: {"keys": [...], "years": [...]}}"""
    n_years = n_years or config.WT_YEARS
    out, missing = {}, {}
    for layer, (path, var, temporal) in config.WT_CATALOG.items():
        domain = path.split("/")[0]
        names = index_by_domain[domain]
        if temporal:
            pat = re.compile(rf"(^|/){re.escape(path)}/{re.escape(var)}/(\d{{4}})\.nc$")
            hits = sorted((int(m.group(2)), n) for n in names if (m := pat.search(n)))
            if hits:
                sel = hits[-n_years:]
                out[layer] = {"keys": [n for _, n in sel], "years": [y for y, _ in sel]}
                continue
        else:
            pat = re.compile(rf"(^|/){re.escape(path)}/{re.escape(var)}\.nc$")
            hits = sorted(n for n in names if pat.search(n))
            if hits:
                out[layer] = {"keys": hits[:1], "years": []}
                continue
        cand = sorted({n.split("/")[-2] if _YEAR.search(n) else n.rsplit("/", 1)[-1][:-3]
                       for n in names if n.endswith(".nc") and f"/{path.split('/')[-1]}" in f"/{n}"})
        missing[layer] = f"{path}/{var} not found; variables under {path}: {cand[:40]}"
    if missing:
        raise SystemExit("WorldTensor layers not found in the archives:\n  "
                         + "\n  ".join(f"{k}: {v}" for k, v in missing.items()))
    return out


def files_present(manifest: dict) -> bool:
    return all((WT_DIR / k).exists() for v in manifest.values() for k in v["keys"])


def load_manifest():
    if not MANIFEST.exists():
        return None
    return json.loads(MANIFEST.read_text())


def download(list_only=False):
    from remotezip import RemoteZip

    domains = sorted({p.split("/")[0] for p, _, _ in config.WT_CATALOG.values()})
    sess = _session()
    index = {}
    for d in domains:
        url = ZIP_URL.format(rec=RECORD, domain=d)
        print(f"  reading index of worldtensor_{d}.zip ...", end="", flush=True)
        with RemoteZip(url, session=sess) as z:
            index[d] = z.namelist()
        print(f" {len(index[d]):,} members")
    manifest = resolve(index)
    for layer, v in manifest.items():
        yrs = f"{v['years'][0]}–{v['years'][-1]}" if v["years"] else "static"
        print(f"    {layer:24s} {yrs:10s} {v['keys'][0].rsplit('/', 2)[0]}")
    if list_only:
        return manifest

    todo = defaultdict(list)
    for v in manifest.values():
        for k in v["keys"]:
            if not (WT_DIR / k).exists():
                todo[k.split("/")[0]].append(k)
    n = sum(len(v) for v in todo.values())
    print(f"  {n} files to extract")
    done = 0
    for d, keys in todo.items():
        with RemoteZip(ZIP_URL.format(rec=RECORD, domain=d), session=sess) as z:
            for k in keys:
                dest = WT_DIR / k
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".part")
                for attempt in range(3):
                    try:
                        tmp.write_bytes(z.read(k))
                        tmp.replace(dest)
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 2:
                            raise RuntimeError(f"failed to extract {k}: {e}") from e
                        time.sleep(10)
                done += 1
                print(f"    [{done}/{n}] {k}", flush=True)
    WT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"record": RECORD, "n_years": config.WT_YEARS, "layers": manifest},
                                   indent=1))
    print(f"  manifest: {MANIFEST.relative_to(config.ROOT)}")
    return manifest


def ready() -> bool:
    m = load_manifest()
    return bool(m) and m.get("n_years") == config.WT_YEARS and files_present(m["layers"]) \
        and set(m["layers"]) == set(config.WT_CATALOG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="resolve and print the selection, download nothing")
    download(list_only=ap.parse_args().list)


if __name__ == "__main__":
    main()
