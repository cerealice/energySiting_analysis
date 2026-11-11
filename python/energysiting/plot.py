"""Figures f1–f4 — plot.R (matplotlib).

Region outlines are traced from the NUTS-2 indicator rasters on the 1 km grid,
so no vector boundaries are needed at plotting time.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import colors as mcolors
from matplotlib.gridspec import GridSpec

from . import config, raster
from .common import presence_xy, region_edges

PAIRED = plt.get_cmap("Paired").colors
MODEL_ORDER = ["GBM", "GLM", "Lasso", "NN", "RF"]


class Basemap:
    def __init__(self):
        self.base = raster.read(config.BASE_RASTER)
        self.inside = np.isfinite(self.base.band())
        self.idx = np.where(self.inside, raster.nuts2_index(), -1)
        self.edges = region_edges(self.idx) & self.inside
        g = self.base.grid
        self.extent = (g.extent[0], g.extent[1], g.extent[2], g.extent[3])

    def draw(self, ax, fill="0.5", edge="0", edge_alpha=1.0):
        land = np.where(self.inside, 1.0, np.nan)
        ax.imshow(land, extent=self.extent, cmap=mcolors.ListedColormap([fill]), interpolation="nearest")
        self.outline(ax, edge, edge_alpha)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
        for s in ax.spines.values():
            s.set_visible(False)

    def outline(self, ax, color="0", alpha=1.0):
        e = np.where(self.edges, 1.0, np.nan)
        ax.imshow(e, extent=self.extent, cmap=mcolors.ListedColormap([color]), alpha=alpha,
                  interpolation="nearest")

    def choropleth(self, ax, values: dict, cmap, norm):
        img = np.full(self.idx.shape, np.nan)
        for k, rid in enumerate(config.NUTS2_IDS):
            name = config.NUTS2_NAME[rid]
            if name in values:
                img[self.idx == k] = values[name]
        ax.imshow(np.where(self.inside, 1.0, np.nan), extent=self.extent,
                  cmap=mcolors.ListedColormap(["white"]), interpolation="nearest")
        im = ax.imshow(img, extent=self.extent, cmap=cmap, norm=norm, interpolation="nearest")
        self.outline(ax)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
        for s in ax.spines.values():
            s.set_visible(False)
        return im


# ── f1 ────────────────────────────────────────────────────────────────────────
def f1(bm):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for ax, tech, title, field, scale, lab in (
            (axes[0, 0], "solar", "Existing solar", "Capacity (MW)", 1, "Capacity\n(MW)"),
            (axes[0, 1], "wind", "Existing wind", "p_cap", 1000, "Capacity\n(GW)")):
        pres = presence_xy(raster.read(config.DERIVED / f"{tech}_hull_existing.tif"))
        loc = pd.read_csv(config.DERIVED / f"{tech}_hull_existing.csv")
        pres = pres.merge(loc[["unique_id", field]], left_on="zone", right_on="unique_id")
        bm.draw(ax)
        sc = ax.scatter(pres.x, pres.y, c=pres[field] / scale, s=3, cmap="YlOrRd")
        fig.colorbar(sc, ax=ax, shrink=0.5, label=lab)
        ax.set_title(title, loc="left")
    for ax, tech in ((axes[1, 0], "solar"), (axes[1, 1], "wind")):
        ab = pd.read_csv(config.OUT / f"absence_{tech}.csv")
        bm.draw(ax)
        for it in sorted(ab.iteration.unique()):
            d = ab[ab.iteration == it]
            ax.scatter(d.x, d.y, s=1.5, color=PAIRED[(it - 1) % 10], label=str(it))
        ax.legend(title="Iteration", markerscale=4, fontsize=7, loc="center left", bbox_to_anchor=(1, 0.5))
        ax.set_title(f"Pseudo-absence - {tech}", loc="left")
    fig.tight_layout(); fig.savefig(config.FIG / "f1.png", dpi=300); plt.close(fig)


# ── f2 ────────────────────────────────────────────────────────────────────────
def aggregate_nuts(rst):
    g = rst.groupby(["var", "Group"])
    out = g.agg(pe=("pe", "mean"), se=("se", lambda s: np.sqrt(np.mean(s ** 2)))).reset_index()
    out["color"] = np.where(np.abs(out.pe) / out.se > 1.96, "Y", "N")
    return out


def _coef_panel(ax, d, errorbars, title):
    d = d.groupby("var", as_index=False).agg(pe=("pe", "mean"), se=("se", "mean")) if not errorbars else d
    order = d.groupby("var")["pe"].mean().sort_values()
    ypos = {v: i for i, v in enumerate(order.index)}
    ax.axvline(0, ls="--", lw=0.6, color="0.3")
    if errorbars:
        ax.errorbar(d.pe, d["var"].map(ypos), xerr=1.96 * d.se, fmt="none", ecolor="0.5", lw=0.8)
        ax.scatter(d.pe, d["var"].map(ypos), s=18, color="red", edgecolor="k", lw=0.5, zorder=3)
    else:
        raw = title[1]
        ax.scatter(raw.pe, raw["var"].map(ypos), s=18, color="red", edgecolor="k", lw=0.5, zorder=3)
    ax.set_yticks(range(len(order)), order.index, fontsize=7 if len(order) > 20 else 8)
    ax.set_xlabel("Odds ratio (log scale)", fontsize=9)
    ax.tick_params(axis="x", labelsize=7)
    ax.set_title(title[0], loc="left", fontsize=16)


def f2():
    imp = pd.read_csv(config.OUT / "imp.csv")
    fig = plt.figure(figsize=(13, 22))
    outer = GridSpec(4, 2, figure=fig, height_ratios=[2.6, 1, 2.6, 1], hspace=0.45, wspace=0.55)
    for row, (tech, t, letter) in enumerate((("Solar", "s", "A"), ("Wind", "w", "B"))):
        rst = aggregate_nuts(pd.read_csv(config.OUT / f"rst_{t}.csv"))
        rst = rst[~rst["var"].isin(config.LULC_SEP_LABELS) & (rst.color == "Y")]
        ax1 = fig.add_subplot(outer[2 * row, 0])
        all_g = rst.copy()
        _coef_panel(ax1, all_g, False, (letter, all_g))
        ax2 = fig.add_subplot(outer[2 * row, 1])
        g5 = rst[rst.Group == 5]
        if len(g5):
            _coef_panel(ax2, g5, True, ("", g5))
        ax3 = fig.add_subplot(outer[2 * row + 1, :])
        d = imp[imp.tech == tech]
        order = d.groupby("rowname")["Overall"].mean().sort_values(ascending=False).index
        x = np.arange(len(order))
        models = sorted(d.model.unique())
        w = 0.8 / len(models)
        for k, m in enumerate(models):
            v = d[d.model == m].set_index("rowname").reindex(order)["Overall"]
            ax3.bar(x + (k - len(models) / 2 + 0.5) * w, v, width=w, color=PAIRED[k * 2 + 1 if k < 5 else k], label=m)
        ax3.set_xticks(x, order, rotation=60, ha="right", fontsize=5.5)
        ax3.set_ylabel("Importance (%)"); ax3.set_xlim(-1, len(order))
        ax3.legend(fontsize=7, ncol=5, loc="upper right", frameon=False)
        ax3.set_title(f"{tech} — variable importance", loc="left", fontsize=10)
    fig.savefig(config.FIG / "f2.png", dpi=300, bbox_inches="tight"); plt.close(fig)


# ── f3 ────────────────────────────────────────────────────────────────────────
def f3(bm):
    res = raster.read(config.OUT / "results_masked.tif")
    rgn = pd.read_csv(config.OUT / "rgn_results.csv")
    fig = plt.figure(figsize=(12, 11))
    gs = GridSpec(5, 3, figure=fig, height_ratios=[1, 1, 1, 1, 0.12], width_ratios=[1, 1, 1.1],
                  hspace=0.25, wspace=0.05)
    cmap = plt.get_cmap("viridis")
    for i, name in enumerate(res.names):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        bm.draw(ax, fill="0.7", edge="white")
        im = ax.imshow(res.data[i], extent=bm.extent, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
        bm.outline(ax, "white")
        ax.set_title(name, fontsize=13, fontweight="bold")
    fig.text(0.02, 0.97, "A", fontsize=16)
    cax = fig.add_subplot(gs[4, :2])
    fig.colorbar(im, cax=cax, orientation="horizontal", label="Probability")
    cols = {"GBM": PAIRED[0], "GLM": PAIRED[1], "Lasso": PAIRED[2], "RF": PAIRED[3]}
    sub = GridSpec(2, 1, figure=fig, left=0.70, right=0.98, top=0.95, bottom=0.12, hspace=0.25)
    for k, tech in enumerate(["Solar", "Wind"]):
        ax = fig.add_subplot(sub[k])
        d = rgn[rgn.tech == tech]
        regs = config.NUTS1_LEVELS
        y = np.arange(len(regs))
        for j, m in enumerate(cols):
            v = d[d.model == m].set_index("region").reindex(regs)["mean"]
            ax.barh(y + (j - 1.5) * 0.18, v, height=0.18, color=cols[m], label=m)
        ax.set_yticks(y, regs); ax.set_xlim(0, max(0.4, np.nanmax(d["mean"]) * 1.1))
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_title(tech, color="white", backgroundcolor="0.2")
        if k == 1:
            ax.set_xlabel("Mean probability")
            ax.legend(fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.25), frameon=False)
    fig.text(0.66, 0.97, "B", fontsize=16)
    fig.savefig(config.FIG / "f3.png", dpi=300, bbox_inches="tight"); plt.close(fig)


# ── f4 ────────────────────────────────────────────────────────────────────────
def f4(bm):
    panels = []
    for tech, letter in (("solar", "A"), ("wind", "B")):
        d = pd.read_csv(config.OUT / f"re_{tech}.csv")
        panels.append((tech, letter, d))
    nmax = max(d.panel_label.nunique() for _, _, d in panels)
    fig = plt.figure(figsize=(4 * nmax, 16))
    gs = GridSpec(4, nmax, figure=fig, height_ratios=[1, 1.1, 1, 1.1], hspace=0.35, wspace=0.6)
    for row, (tech, letter, d) in enumerate(panels):
        labels = list(dict.fromkeys(d.sort_values("variable").panel_label))
        for j, lab in enumerate(labels):
            dd = d[d.panel_label == lab]
            var = dd.variable.iloc[0]
            flip = var in ("Transmission dist", "Environmental score")
            cmap = mcolors.LinearSegmentedColormap.from_list(
                "div", ["royalblue", "white", "darkorange"] if not flip else ["darkorange", "white", "royalblue"])
            lim = np.nanmax(np.abs(dd.R_effect)) or 1
            ax = fig.add_subplot(gs[2 * row, j])
            im = bm.choropleth(ax, dict(zip(dd.region, dd.R_effect)), cmap,
                               mcolors.TwoSlopeNorm(0, -lim, lim))
            fig.colorbar(im, ax=ax, shrink=0.6)
            ax.set_title(lab, fontsize=10)
            if j == 0:
                ax.text(-0.1, 1.05, letter, transform=ax.transAxes, fontsize=14)
            ax = fig.add_subplot(gs[2 * row + 1, j])
            dd = dd.sort_values("region", ascending=False)
            yy = np.arange(len(dd))
            ax.axvline(0, ls="--", lw=0.6, color="0.3")
            ax.errorbar(dd.R_effect, yy, xerr=dd.SE, fmt="o", color="0.1", ms=3, lw=1.2)
            ax.set_yticks(yy, [config.NUTS2[config.NUTS2_BY_NAME.get(r, 'ITC1')][1] if r in config.NUTS2_BY_NAME else r
                               for r in dd.region], fontsize=8)
            ax.set_xlabel("Odds ratio (log scale)", fontsize=9)
            ax.set_title(lab, color="white", backgroundcolor="0.2", fontsize=9)
    fig.savefig(config.FIG / "f4.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def run():
    config.ensure_dirs()
    bm = Basemap()
    f1(bm); f2(); f3(bm); f4(bm)
    print("Saved f1–f4 to", config.FIG)


if __name__ == "__main__":
    run()
