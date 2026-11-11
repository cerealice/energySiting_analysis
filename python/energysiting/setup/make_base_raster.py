"""make_base_raster.R — 1 km EPSG:3035 Italy grid (1 = Italy, NA outside)."""
import numpy as np

from .. import config, raster
from ._geo import gisco_countries, rasterize


def run(res_m=config.RES_M):
    config.ensure_dirs()
    italy = gisco_countries("IT").dissolve()
    xmin, ymin, xmax, ymax = italy.total_bounds
    xmin, ymin = np.floor(xmin / res_m) * res_m, np.floor(ymin / res_m) * res_m
    xmax, ymax = np.ceil(xmax / res_m) * res_m, np.ceil(ymax / res_m) * res_m
    grid = raster.Grid(xmin, ymax, res_m, int(round((ymax - ymin) / res_m)),
                       int(round((xmax - xmin) / res_m)), config.EPSG)
    print(f"Raster template: {grid.nrow} rows x {grid.ncol} cols")
    arr = rasterize(italy, grid, 1.0)
    print("Cells within Italy:", int(np.isfinite(arr).sum()))
    raster.write(config.BASE_RASTER, arr, grid, ["layer"])
    print("Saved:", config.BASE_RASTER)


if __name__ == "__main__":
    run()
