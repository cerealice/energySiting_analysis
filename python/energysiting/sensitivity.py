"""Leakage sensitivity: refit GBM and RF without predictors that may "see" the plants.

ESA WorldCover (2020–21 imagery) maps large ground-mounted PV farms as built-up,
so the land-cover share "Developed" can partly encode the presences themselves.
Each scenario drops a set of predictors and re-runs GBM and RF on exactly the
same random 10-fold and spatial-block folds as the main models, so the AUC
change is attributable to the dropped predictors alone.

Scenarios (ES_SENSITIVITY, comma-separated; default "no_developed"):
  no_developed   lulc_developed
  no_lag         lag            (spatial lag of pre-2017 plants)
  no_both        lulc_developed + lag

Outputs: derived/py/sensitivity_auc.csv (one row per fold),
         derived/py/sensitivity_summary.csv, derived/py/sensitivity_imp.csv
         (GBM top predictors per scenario), fig/python/f_sensitivity.png.
"""
from __future__ import annotations

import os

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config, raster  # noqa: E402
from .common import log, presence_xy  # noqa: E402
from .learners import train, var_imp  # noqa: E402

SCENARIOS = {
    "no_developed": ["lulc_developed"],
    "no_lag": ["lag"],
    "no_both": ["lulc_developed", "lag"],
}
MODELS = (("xg", "GBM"), ("rf", "RF"))
CV = ("Random (10-fold)", "Spatial block (5-fold)")


def scenarios():
    names = [s.strip() for s in os.environ.get("ES_SENSITIVITY", "no_developed").split(",") if s.strip()]
    bad = [s for s in names if s not in SCENARIOS]
    if bad:
        raise SystemExit(f"ES_SENSITIVITY: unknown scenario(s) {bad}; choose from {list(SCENARIOS)}")
    return names


def _baseline(tech):
    """AUC per fold of the full models, from the modeling and spatial_cv steps."""
    rows = []
    rnd = pd.read_csv(config.OUT / f"resamples_{tech}.csv")
    sp = pd.read_csv(config.OUT / "spatial_cv_comparison.csv")
    for key, label in MODELS:
        rows.append(pd.DataFrame({"cv_type": CV[0], "model": label, "ROC": rnd[f"{key}~ROC"]}))
        d = sp[(sp.technology == tech.capitalize()) & (sp.model == label) & (sp.cv_type == CV[1])]
        rows.append(pd.DataFrame({"cv_type": CV[1], "model": label, "ROC": d.ROC.to_numpy()}))
    return pd.concat(rows, ignore_index=True).assign(scenario="all predictors")


def run():
    config.ensure_dirs()
    names = scenarios()
    auc, imps = [], []
    for tech in config.TECHS:
        dat = pd.read_csv(config.OUT / f"{tech}.csv")
        y = (dat["treat"] == "X1").astype(int).to_numpy()
        mv = config.model_vars(tech, dat.columns)
        auc.append(_baseline(tech).assign(technology=tech.capitalize()))

        # spatial folds index the coordinate-matched rows used by spatial_cv
        sp = joblib.load(config.OUT / f"spatial_folds_{tech}.joblib")
        pres = presence_xy(raster.read(config.DERIVED / f"{tech}_hull_existing.tif")).assign(treat="X1")
        ab = pd.read_csv(config.OUT / f"absence_{tech}.csv").rename(columns={"id": "zone"})
        coords = pd.concat([pres, ab[["zone", "x", "y"]].assign(treat="X0")], ignore_index=True)
        dsp = dat.merge(coords, on=["zone", "treat"], how="inner")
        ysp = (dsp["treat"] == "X1").astype(int).to_numpy()
        folds = {CV[0]: (dat, y, joblib.load(config.OUT / f"folds_{tech}.joblib")),
                 CV[1]: (dsp, ysp, sp["folds"])}

        for sc in names:
            keep = [v for v in mv if v not in SCENARIOS[sc]]
            log(f"{tech} · {sc}: {len(keep)} predictors (dropped {', '.join(SCENARIOS[sc])})")
            for cv, (d, yy, f) in folds.items():
                for key, label in MODELS:
                    tr = train(key, d[keep], yy, f, seed=config.SEED, n_jobs=config.n_jobs())
                    auc.append(pd.DataFrame({"technology": tech.capitalize(), "scenario": sc,
                                             "cv_type": cv, "model": label, "ROC": tr.resample.ROC}))
                    if key == "xg" and cv == CV[0]:
                        vi = var_imp(tr, d[keep], yy, seed=config.SEED).sort_values(ascending=False).head(10)
                        imps.append(pd.DataFrame({"technology": tech.capitalize(), "scenario": sc,
                                                  "variable": [config.VAR_LABELS.get(v, v) for v in vi.index],
                                                  "importance": vi.to_numpy().round(1)}))

    auc = pd.concat(auc, ignore_index=True)
    auc.to_csv(config.OUT / "sensitivity_auc.csv", index=False)
    if imps:
        pd.concat(imps, ignore_index=True).to_csv(config.OUT / "sensitivity_imp.csv", index=False)

    summ = auc.groupby(["technology", "model", "cv_type", "scenario"])["ROC"].mean().unstack()
    for sc in names:
        summ[f"Δ {sc}"] = summ[sc] - summ["all predictors"]
    summ = summ[["all predictors"] + names + [f"Δ {sc}" for sc in names]].round(3)
    summ.to_csv(config.OUT / "sensitivity_summary.csv")
    print("\n" + "═" * 70 + "\n  Leakage sensitivity — mean AUC-ROC\n" + "═" * 70)
    print(summ.to_string())
    _plot(auc, ["all predictors"] + names)
    log("saved sensitivity results")


def _plot(auc, order):
    colors = ["0.55", "#E66101", "#5E3C99", "#1B9E77"]
    fig, axes = plt.subplots(2, 4, figsize=(13, 6), sharey=True)
    rng = np.random.default_rng(0)
    for i, tech in enumerate(["Solar", "Wind"]):
        for j, (cv, (_, model)) in enumerate([(c, m) for c in CV for m in MODELS]):
            ax = axes[i, j]
            d = auc[(auc.technology == tech) & (auc.model == model) & (auc.cv_type == cv)]
            vals = [d[d.scenario == s].ROC.to_numpy() for s in order]
            bp = ax.boxplot(vals, patch_artist=True, widths=0.6, showfliers=False)
            for p, c in zip(bp["boxes"], colors):
                p.set_facecolor(c); p.set_alpha(0.6)
            for k, v in enumerate(vals, 1):
                ax.scatter(k + rng.uniform(-0.1, 0.1, len(v)), v, s=9, color="k", alpha=0.6, zorder=3)
            ax.set_xticks(range(1, len(order) + 1), [s.replace("_", " ") for s in order],
                          rotation=30, ha="right", fontsize=8)
            ax.set_title(f"{tech} · {model}\n{cv}", fontsize=9)
            ax.grid(alpha=0.3)
        axes[i, 0].set_ylabel("AUC-ROC")
    fig.suptitle("Leakage sensitivity: AUC with and without predictors that may see the plants", fontsize=11)
    fig.tight_layout(); fig.savefig(config.FIG / "f_sensitivity.png", dpi=200); plt.close(fig)


if __name__ == "__main__":
    run()
