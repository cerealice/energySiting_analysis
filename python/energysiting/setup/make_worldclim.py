"""make_worldclim.R — WorldClim 2.1 BIO1–BIO19 (30″) snapped to the base grid."""
from .. import config
from ._geo import GEODATA, base, download, save_var, snap, unzip_member


def run():
    config.ensure_dirs()
    outs = [config.VAR_PATH / f"wclim_bio{i:02d}.tif" for i in range(1, 20)]
    if all(p.exists() for p in outs):
        print("All WorldClim BIO layers already exist — nothing to do.")
        return
    b = base()
    dl = config.RAW / "worldclim"
    z = download(f"{GEODATA}/climate/worldclim/2_1/base/wc2.1_30s_bio.zip", dl / "wc2.1_30s_bio.zip")
    for i, out in enumerate(outs, 1):
        if out.exists():
            continue
        tif = dl / f"wc2.1_30s_bio_{i}.tif"
        if not tif.exists():
            unzip_member(z, tif.name, tif)
        save_var(snap(tif, b=b), out.name, b)


if __name__ == "__main__":
    run()
