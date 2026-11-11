"""Spatial block cross-validation — spatial_cv.R (blockCV equivalent).

1. Recover x/y for every training row (presence: mean of its hull cells;
   absence: buffer centre).
2. Estimate the spatial autocorrelation range of the response with an
   empirical variogram + best-fitting spherical / exponential / gaussian model
   (blockCV::cv_spatial_autocor uses automap::autofitVariogram the same way).
3. Block size = max(50 km, range rounded up to 10 km); square blocks on the
   raster grid are randomly allocated to k = 5 folds, repeating 100 random
   allocations and keeping the one with the best class balance
   (cv_spatial(selection = "random", iteration = 100)).
4. Refit GBM and RF on the spatial folds and compare with random 10-fold CV.
"""
from __future__ import annotations

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.spatial.distance import pdist

from . import config, raster
from .common import log, presence_xy, region_edges
from .learners import train


# ── variogram ─────────────────────────────────────────────────────────────────
def _sph(h, nug, psill, a):
    h = np.asarray(h) / a
    return nug + psill * np.where(h < 1, 1.5 * h - 0.5 * h ** 3, 1.0)


def _exp(h, nug, psill, a):
    return nug + psill * (1 - np.exp(-np.asarray(h) / a))


def _gau(h, nug, psill, a):
    return nug + psill * (1 - np.exp(-(np.asarray(h) / a) ** 2))


def autocor_range(xy, z, nbins=15, max_pts=4000, seed=1):
    rng = np.random.default_rng(seed)
    if len(z) > max_pts:
        keep = rng.choice(len(z), max_pts, replace=False)
        xy, z = xy[keep], z[keep]
    d = pdist(xy)
    g = 0.5 * pdist(z[:, None], "sqeuclidean")
    cutoff = d.max() / 3                      # gstat default cutoff: 1/3 of the diagonal
    edges = np.linspace(0, cutoff, nbins + 1)
    idx = np.digitize(d, edges) - 1
    ok = (idx >= 0) & (idx < nbins)
    h = np.bincount(idx[ok], weights=d[ok], minlength=nbins)
    gm = np.bincount(idx[ok], weights=g[ok], minlength=nbins)
    n = np.bincount(idx[ok], minlength=nbins)
    good = n > 30
    h, gm, n = h[good] / n[good], gm[good] / n[good], n[good]
    best = None
    for name, f in (("Sph", _sph), ("Exp", _exp), ("Gau", _gau)):
        try:
            p, _ = curve_fit(f, h, gm, p0=[gm.min(), gm.max() - gm.min(), cutoff / 3],
                             bounds=([0, 0, 1e3], [np.inf, np.inf, 5 * cutoff]),
                             sigma=1 / np.sqrt(n), maxfev=20000)
            sse = np.sum(n * (f(h, *p) - gm) ** 2)
            if best is None or sse < best[0]:
                best = (sse, name, p)
        except Exception:
            continue
    sse, name, p = best
    return dict(range=float(p[2]), model=name, nugget=p[0], psill=p[1],
                variogram=pd.DataFrame({"dist": h, "gamma": gm, "np": n}))


# ── spatial blocks ────────────────────────────────────────────────────────────
def spatial_blocks(xy, y, grid, size, k=5, iterations=100, seed=42):
    bc = np.floor((xy[:, 0] - grid.x0) / size).astype(int)
    br = np.floor((grid.y0 - xy[:, 1]) / size).astype(int)
    block = br * 10_000 + bc
    ublocks, inv = np.unique(block, return_inverse=True)
    rng = np.random.default_rng(seed)
    best, best_score = None, -np.inf
    for _ in range(iterations):
        assign = rng.permutation(np.arange(len(ublocks)) % k)
        fold = assign[inv]
        # balance criterion: smallest per-fold count of the rarer class in test
        score = min(min(np.sum((fold == f) & (y == 0)), np.sum((fold == f) & (y == 1)))
                    for f in range(k))
        if score > best_score:
            best, best_score = fold, score
    folds = [(np.flatnonzero(best != f), np.flatnonzero(best == f)) for f in range(k)]
    return folds, best, ublocks


def plot_blocks(path, xy, y, fold, size, grid, edges_img, title):
    fig, ax = plt.subplots(figsize=(5.3, 6))
    xmin, xmax, ymin, ymax = grid.extent
    ax.imshow(np.where(edges_img, 0.0, np.nan), extent=(xmin, xmax, ymin, ymax), cmap="gray",
              interpolation="nearest")
    cmap = plt.get_cmap("Set1")
    for f in np.unique(fold):
        m = fold == f
        ax.scatter(xy[m, 0], xy[m, 1], s=4, color=cmap(f), label=f"Fold {f + 1}",
                   marker="o", alpha=0.8)
    xs = np.arange(grid.x0, xmax + size, size)
    ys = np.arange(grid.y0, ymin - size, -size)
    for x in xs:
        ax.axvline(x, color="0.8", lw=0.4, zorder=0)
    for yy in ys:
        ax.axhline(yy, color="0.8", lw=0.4, zorder=0)
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([]); ax.legend(fontsize=7, markerscale=2, loc="lower left")
    ax.set_title(title)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def run():
    config.ensure_dirs()
    base = raster.read(config.BASE_RASTER)
    edges = region_edges(np.where(np.isfinite(base.band()), raster.nuts2_index(), -1))
    comparison, info = [], {}
    for tech in config.TECHS:
        pres = presence_xy(raster.read(config.DERIVED / f"{tech}_hull_existing.tif")).assign(treat="X1")
        ab = pd.read_csv(config.OUT / f"absence_{tech}.csv").rename(columns={"id": "zone"})
        coords = pd.concat([pres, ab[["zone", "x", "y"]].assign(treat="X0")], ignore_index=True)
        dat = pd.read_csv(config.OUT / f"{tech}.csv").merge(coords, on=["zone", "treat"], how="inner")
        log(f"{tech}: training points with coords {len(dat)} / {len(pd.read_csv(config.OUT / f'{tech}.csv'))}")
        xy = dat[["x", "y"]].to_numpy()
        y = (dat["treat"] == "X1").astype(int).to_numpy()

        ac = autocor_range(xy, y.astype(float))
        size = max(50_000, np.ceil(ac["range"] / 10_000) * 10_000)
        log(f"{tech}: autocorrelation range {ac['range']:.0f} m ({ac['model']}) → block size {size:.0f} m")
        folds, fold_id, _ = spatial_blocks(xy, y, base.grid, size, k=5, seed=config.SEED)
        plot_blocks(config.FIG / f"spatial_blocks_{tech}.png", xy, y, fold_id, size, base.grid, edges,
                    f"{tech.capitalize()} — spatial blocks ({size / 1000:.0f} km, k = 5)")

        X = dat[config.MODEL_VARS]
        rnd = pd.read_csv(config.OUT / f"resamples_{tech}.csv")
        for key, label in (("xg", "GBM"), ("rf", "RF")):
            tr = train(key, X, y, folds, seed=config.SEED, n_jobs=config.n_jobs())
            joblib.dump(tr, config.OUT / f"mdl_{tech}{key}_spatialcv.joblib")
            comparison.append(pd.DataFrame({"technology": tech.capitalize(), "model": label,
                                            "cv_type": "Random (10-fold)", "ROC": rnd[f"{key}~ROC"]}))
            comparison.append(pd.DataFrame({"technology": tech.capitalize(), "model": label,
                                            "cv_type": "Spatial block (5-fold)", "ROC": tr.resample.ROC}))
        info[tech] = dict(range=ac["range"], block=size, model=ac["model"])
        joblib.dump(dict(folds=folds, fold_id=fold_id, xy=xy, block=size, autocor=ac),
                    config.OUT / f"spatial_folds_{tech}.joblib")

    comp = pd.concat(comparison, ignore_index=True)
    comp.to_csv(config.OUT / "spatial_cv_comparison.csv", index=False)
    summ = (comp.groupby(["technology", "model", "cv_type"])["ROC"]
            .agg(lambda v: f"{v.mean():.3f} (±{v.std():.3f})").unstack())
    print("\n" + "═" * 58 + "\n  Random CV  vs  Spatial CV — AUC-ROC comparison\n" + "═" * 58)
    print(summ.to_string())

    cols = {"Random (10-fold)": "#7FC97F", "Spatial block (5-fold)": "#F0A500"}
    fig, axes = plt.subplots(2, 2, figsize=(8, 6), sharey=True)
    rng = np.random.default_rng(0)
    for i, tech in enumerate(["Solar", "Wind"]):
        for j, model in enumerate(["GBM", "RF"]):
            ax = axes[i, j]
            d = comp[(comp.technology == tech) & (comp.model == model)]
            vals = [d[d.cv_type == c].ROC.to_numpy() for c in cols]
            bp = ax.boxplot(vals, patch_artist=True, widths=0.6)
            for p, c in zip(bp["boxes"], cols.values()):
                p.set_facecolor(c); p.set_alpha(0.7)
            for k, v in enumerate(vals, 1):
                ax.scatter(k + rng.uniform(-0.1, 0.1, len(v)), v, s=10, color="k", alpha=0.6)
            ax.set_xticks([1, 2], ["Random\n(10-fold)", "Spatial block\n(5-fold)"], fontsize=8)
            ax.set_title(f"{tech} · {model}", color="white", backgroundcolor="0.2", fontsize=10)
            ax.grid(alpha=0.3)
        axes[i, 0].set_ylabel("AUC-ROC")
    fig.suptitle("Random CV vs Spatial block CV\n"
                 f"Block sizes: Solar = {info['solar']['block'] / 1000:.0f} km, "
                 f"Wind = {info['wind']['block'] / 1000:.0f} km", fontsize=11)
    fig.tight_layout(); fig.savefig(config.FIG / "f_spatial_cv_comparison.png", dpi=300); plt.close(fig)
    pd.DataFrame(info).T.to_csv(config.OUT / "spatial_cv_info.csv")
    log("saved spatial CV results")


if __name__ == "__main__":
    run()
