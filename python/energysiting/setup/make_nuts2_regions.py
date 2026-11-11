"""make_nuts2_regions.R — one binary indicator raster per Italian NUTS-2 region."""
from .. import config
from ._geo import base, gisco_nuts, mask_base, rasterize, save_var


def run():
    config.ensure_dirs()
    b = base()
    n2 = gisco_nuts(2, "2016")
    print(f"Found {len(n2)} NUTS-2 regions: {', '.join(sorted(n2.NUTS_ID))}")
    for _, row in n2.iterrows():
        r = rasterize(n2[n2.NUTS_ID == row.NUTS_ID], b.grid, 1.0, fill=0.0)
        save_var(mask_base(r, b), f"nuts2_{row.NUTS_ID.lower()}.tif", b)


if __name__ == "__main__":
    run()
