"""Helpers shared by several steps."""
from __future__ import annotations

import time
from contextlib import contextmanager

import numpy as np
import pandas as pd

from . import config, raster


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@contextmanager
def step(name):
    log(f"── Running: {name}")
    t0 = time.time()
    yield
    log(f"   {name} done in {time.time() - t0:.0f}s")


def impute_dat(df: pd.DataFrame, medians: pd.Series | None = None) -> pd.DataFrame:
    """modeling.R impute_dat(): LUH3 NA → 0, other numeric NA → column median.
    Pass ``medians`` (from training data) to impute new data the same way."""
    df = df.copy()
    luh = [c for c in df.columns if c.startswith("luh3_")]
    df[luh] = df[luh].fillna(0)
    num = df.select_dtypes("number").columns
    med = df[num].median() if medians is None else medians.reindex(num)
    df[num] = df[num].fillna(med)
    return df


def load_stacks():
    """covStack (102 layers), tech stacks (env, cf, lag) and future tx/sub."""
    cov = raster.read(config.DERIVED / "covStack.tif", names=config.COV_LAYERS)
    fut = raster.read(config.DERIVED / "future.tif", names=config.FUTURE_LAYERS)
    tech = {t: raster.read(config.DERIVED / f"{t}_covStack.tif", names=config.TECH_LAYERS)
            for t in config.TECHS}
    return cov, fut, tech


def prediction_frame(cov, fut, tech_stack, base_mask):
    """Cell-level predictor table for the *future* scenario (current tx/sub swapped
    for the planned-infrastructure layers), restricted to cells inside Italy."""
    rr, cc = np.nonzero(base_mask)
    cols = {}
    for name in config.MODEL_VARS:
        if name in config.FUTURE_LAYERS:
            src = fut[name]
        elif name in config.TECH_LAYERS:
            src = tech_stack[name]
        else:
            src = cov[name]
        cols[name] = src[rr, cc]
    return pd.DataFrame(cols), (rr, cc)


def presence_xy(hull: raster.Raster):
    """Mean x/y of the cells carrying each presence zone id (spatial_cv.R)."""
    a = hull.band()
    rr, cc = np.nonzero(np.isfinite(a))
    x, y = hull.grid.xy_of_cells(rr, cc)
    df = pd.DataFrame({"zone": a[rr, cc].astype(int), "x": x, "y": y})
    return df.groupby("zone", as_index=False)[["x", "y"]].mean()


def region_edges(idx):
    """Boolean raster marking boundaries between different region indices."""
    e = np.zeros(idx.shape, bool)
    e[:-1, :] |= idx[:-1, :] != idx[1:, :]
    e[:, :-1] |= idx[:, :-1] != idx[:, 1:]
    return e
