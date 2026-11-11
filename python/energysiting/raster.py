"""Minimal raster layer — replaces terra / raster for the analysis steps.

All rasters in this project live on the same 1 km EPSG:3035 grid
(Italy_base_raster.tif), so the analysis only needs: read a GeoTIFF into a
(bands, rows, cols) float array, know the grid geometry, and write results back.

* If ``rasterio`` is installed it is used (recommended, required by setup/).
* Otherwise a pure-Python fallback built on ``tifffile`` reads/writes the
  GeoTIFFs, including a small LZW decoder so terra's default LZW-compressed
  files open without GDAL or imagecodecs.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:  # pragma: no cover - optional
    import rasterio
    from rasterio.transform import Affine
    HAVE_RASTERIO = True
except Exception:  # pragma: no cover
    HAVE_RASTERIO = False


@dataclass(frozen=True)
class Grid:
    """Axis-aligned north-up grid: top-left corner, cell size, shape, EPSG."""
    x0: float
    y0: float
    res: float
    nrow: int
    ncol: int
    epsg: int = 3035

    @property
    def shape(self):
        return (self.nrow, self.ncol)

    @property
    def extent(self):  # xmin, xmax, ymin, ymax
        return (self.x0, self.x0 + self.ncol * self.res, self.y0 - self.nrow * self.res, self.y0)

    def xy_of_cells(self, rows, cols):
        """Cell-centre coordinates (terra::xyFromCell)."""
        return (self.x0 + (np.asarray(cols) + 0.5) * self.res,
                self.y0 - (np.asarray(rows) + 0.5) * self.res)

    def cell_of_xy(self, x, y):
        col = np.floor((np.asarray(x) - self.x0) / self.res).astype(int)
        row = np.floor((self.y0 - np.asarray(y)) / self.res).astype(int)
        return row, col

    def centres(self):
        xs = self.x0 + (np.arange(self.ncol) + 0.5) * self.res
        ys = self.y0 - (np.arange(self.nrow) + 0.5) * self.res
        return xs, ys


@dataclass
class Raster:
    data: np.ndarray            # (bands, rows, cols) float32/float64 with NaN = NA
    grid: Grid
    names: list

    def __getitem__(self, name):
        return self.data[self.names.index(name)]

    def band(self, i=0):
        return self.data[i]


# ── LZW (TIFF flavour, MSB-first, early change) ───────────────────────────────
def lzw_decode(encoded: bytes) -> bytes:
    data = encoded + b"\x00\x00\x00"
    nbits_total = len(encoded) * 8
    out = bytearray()
    table = [bytes((i,)) for i in range(256)] + [b"", b""]
    append = table.append
    bitpos, nbits, mask = 0, 9, 0x1FF
    prev = None
    while bitpos + nbits <= nbits_total:
        i = bitpos >> 3
        code = ((data[i] << 16 | data[i + 1] << 8 | data[i + 2]) >> (24 - (bitpos & 7) - nbits)) & mask
        bitpos += nbits
        if code == 256:                     # clear
            del table[258:]
            nbits, mask, prev = 9, 0x1FF, None
            continue
        if code == 257:                     # end of information
            break
        if prev is None:
            entry = table[code]
            out += entry
            prev = entry
            continue
        if code < len(table):
            entry = table[code]
            append(prev + entry[:1])
        else:
            entry = prev + prev[:1]
            append(entry)
        out += entry
        prev = entry
        n = len(table)
        if n == 511:
            nbits, mask = 10, 0x3FF
        elif n == 1023:
            nbits, mask = 11, 0x7FF
        elif n == 2047:
            nbits, mask = 12, 0xFFF
    return bytes(out)


def _gdal_names(page, nbands):
    tag = page.tags.get(42112)  # GDAL_METADATA
    names = [None] * nbands
    if tag is not None:
        for m in re.finditer(r'<Item name="DESCRIPTION" sample="(\d+)" role="description">([^<]*)</Item>',
                             str(tag.value)):
            s = int(m.group(1))
            if s < nbands:
                names[s] = m.group(2)
    return [n if n else f"band{i + 1}" for i, n in enumerate(names)]


def _read_tifffile(path):
    import tifffile
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        scale = page.tags[33550].value
        tie = page.tags[33922].value
        nd = page.tags.get(42113)
        try:
            nodata = float(str(nd.value).strip("\x00 ")) if nd is not None else np.nan
        except ValueError:
            nodata = np.nan
        spp = page.samplesperpixel
        nrow, ncol = page.imagelength, page.imagewidth
        names = _gdal_names(page, spp)
        if page.compression in (1, 8, 32946) or page.compression == 5 and _has_imagecodecs():
            arr = page.asarray()
        elif page.compression == 5:
            if page.is_tiled or page.predictor not in (1, None):
                raise RuntimeError(f"{path}: tiled/predicted LZW needs rasterio or imagecodecs")
            dtype = np.dtype(page.dtype).newbyteorder("<" if tf.byteorder == "<" else ">")
            fh = tf.filehandle
            chunks = []
            for off, cnt in zip(page.dataoffsets, page.databytecounts):
                fh.seek(off)
                chunks.append(lzw_decode(fh.read(cnt)))
            if page.planarconfig == 1:
                buf = np.frombuffer(b"".join(chunks), dtype=dtype)[: nrow * ncol * spp]
                arr = buf.reshape(nrow, ncol, spp) if spp > 1 else buf.reshape(nrow, ncol)
            else:
                buf = np.frombuffer(b"".join(chunks), dtype=dtype)[: nrow * ncol * spp]
                arr = buf.reshape(spp, nrow, ncol)
                arr = np.moveaxis(arr, 0, -1) if spp > 1 else arr[0]
        else:
            raise RuntimeError(f"{path}: compression {page.compression} unsupported without rasterio")
        if arr.ndim == 2:
            arr = arr[None]
        elif page.planarconfig == 1:
            arr = np.moveaxis(arr, -1, 0)
        epsg = 3035
        try:
            epsg = int(tf.geotiff_metadata.get("ProjectedCSTypeGeoKey", 3035))
        except Exception:
            pass
    grid = Grid(x0=tie[3] - tie[0] * scale[0], y0=tie[4] + tie[1] * scale[1], res=scale[0],
                nrow=nrow, ncol=ncol, epsg=epsg)
    arr = arr.astype(np.float32, copy=True)
    if not np.isnan(nodata):
        arr[np.isclose(arr, np.float32(nodata), rtol=1e-6)] = np.nan
    arr[arr < -1e37] = np.nan            # terra/raster float32 NA flag (-3.4e38)
    return arr, grid, names


def _has_imagecodecs():
    try:
        import imagecodecs  # noqa: F401
        return True
    except Exception:
        return False


_CACHE: dict = {}


def read(path, names=None, cache=True) -> Raster:
    """Read a GeoTIFF → Raster(data[bands,rows,cols], grid, names)."""
    path = Path(path)
    key = (str(path), path.stat().st_mtime)
    if cache and key in _CACHE:
        arr, grid, nm = _CACHE[key]
    else:
        if HAVE_RASTERIO:
            with rasterio.open(path) as src:
                arr = src.read(masked=True).filled(np.nan).astype(np.float32)
                t = src.transform
                grid = Grid(t.c, t.f, t.a, src.height, src.width, src.crs.to_epsg() or 3035)
                nm = [d or f"band{i + 1}" for i, d in enumerate(src.descriptions)]
        else:
            arr, grid, nm = _read_tifffile(path)
        if cache:
            _CACHE[key] = (arr, grid, nm)
    if names is not None:
        if len(names) != arr.shape[0]:
            raise ValueError(f"{path.name}: {arr.shape[0]} bands but {len(names)} names")
        nm = list(names)
    return Raster(arr, grid, list(nm))


def _geokeys(epsg):
    keys = [1, 1, 0, 4,
            1024, 0, 1, 1,        # GTModelType = projected
            1025, 0, 1, 1,        # RasterType = PixelIsArea
            3072, 0, 1, int(epsg),
            3076, 0, 1, 9001]     # metre
    return keys


def write(path, data, grid: Grid, names=None, nodata=np.nan):
    """Write a (bands,rows,cols) or (rows,cols) array as a deflate GeoTIFF."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 2:
        data = data[None]
    names = list(names) if names is not None else [f"band{i + 1}" for i in range(data.shape[0])]
    if HAVE_RASTERIO:
        prof = dict(driver="GTiff", height=grid.nrow, width=grid.ncol, count=data.shape[0],
                    dtype="float32", crs=f"EPSG:{grid.epsg}", nodata=nodata, compress="deflate",
                    transform=Affine(grid.res, 0, grid.x0, 0, -grid.res, grid.y0))
        with rasterio.open(path, "w", **prof) as dst:
            dst.write(data)
            for i, n in enumerate(names, 1):
                dst.set_band_description(i, n)
    else:
        import tifffile
        meta = "<GDALMetadata>" + "".join(
            f'<Item name="DESCRIPTION" sample="{i}" role="description">{n}</Item>'
            for i, n in enumerate(names)) + "</GDALMetadata>"
        gk = _geokeys(grid.epsg)
        extratags = [
            (33550, "d", 3, (grid.res, grid.res, 0.0), False),
            (33922, "d", 6, (0.0, 0.0, 0.0, grid.x0, grid.y0, 0.0), False),
            (34735, "H", len(gk), tuple(gk), False),
            (42112, "s", 0, meta, False),
            (42113, "s", 0, "nan" if np.isnan(nodata) else str(nodata), False),
        ]
        tifffile.imwrite(path, data, photometric="minisblack", planarconfig="separate",
                         compression="zlib", extratags=extratags)
    _CACHE.pop(str(path), None)
    return path


def nuts2_index(grid_like: Raster | None = None):
    """Integer raster of NUTS-2 membership (index into config.NUTS2_IDS; -1 = none),
    built from the nuts2_<id>.tif indicator rasters written by make_nuts2_regions."""
    from . import config
    idx = None
    for k, rid in enumerate(config.NUTS2_IDS):
        r = read(config.VAR_PATH / f"nuts2_{rid.lower()}.tif").band()
        if idx is None:
            idx = np.full(r.shape, -1, dtype=np.int16)
        idx[(r == 1) & (idx < 0)] = k
    return idx
