"""Neural network + geospatial embeddings (the other four models stay without them).

For every embedding product in derived/embStack.tif (setup/make_embeddings.py),
the NN (same architecture and tuning grid as in modeling.py) is refitted with
the main predictors + that product's principal components, on exactly the same
random 10-fold and spatial-block folds. The NN without embeddings on the same
folds is the reference, so the AUC difference is the value of the embeddings.

ES_EMB_ONLY=1 adds "embeddings only" fits (no other predictors): if those
score near the full model, the embeddings carry the presences themselves.
Comparing terranova2016 vs terranova2024 (and tessera2017 vs tessera2024) tests
for leakage: most modelled plants were built after 2016/2017.

Outputs: derived/py/nn_emb_auc.csv (per fold), nn_emb_summary.csv,
         pred_nn_emb_<product>_<s|w>.tif (future-infrastructure maps),
         fig/python/f_nn_embeddings.png
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config, raster  # noqa: E402
from .common import impute_dat, load_stacks, log, prediction_frame  # noqa: E402
from .learners import train  # noqa: E402
from .sensitivity import CV, cv_sets  # noqa: E402


def products(columns):
    keys = []
    for c in columns:
        if c.startswith("emb_"):
            k = c[4:].rsplit("_", 1)[0]
            if k not in keys:
                keys.append(k)
    return keys


def run():
    config.ensure_dirs()
    from .setup import make_embeddings
    emb = make_embeddings.load()
    if emb is None:
        log("no embedding stack (derived/embStack.tif) — skipping; build it with --setup")
        return
    only = os.environ.get("ES_EMB_ONLY", "0") == "1"
    cov, fut, tech_stacks = load_stacks()
    base = raster.read(config.BASE_RASTER)
    base_mask = np.isfinite(base.band())
    rows = []
    for tech in config.TECHS:
        t = config.TECHS[tech]
        dat = pd.read_csv(config.OUT / f"{tech}.csv")
        keys = products(dat.columns)
        if not keys:
            log(f"{tech}: no emb_* columns in {tech}.csv — rerun from zonal after building embStack")
            continue
        mv = config.model_vars(tech, dat.columns)
        sets = cv_sets(tech, dat)
        rnd = pd.read_csv(config.OUT / f"resamples_{tech}.csv")
        rows.append(pd.DataFrame({"technology": tech.capitalize(), "predictors": "main (no embeddings)",
                                  "cv_type": CV[0], "ROC": rnd["nn~ROC"]}))
        d, yy, f = sets[CV[1]]
        tr = train("nn", d[mv], yy, f, seed=config.SEED, n_jobs=config.n_jobs())
        rows.append(pd.DataFrame({"technology": tech.capitalize(), "predictors": "main (no embeddings)",
                                  "cv_type": CV[1], "ROC": tr.resample.ROC}))

        grid_df, (rr, cc) = prediction_frame(cov, fut, tech_stacks[tech], base_mask, mv)
        for k in keys:
            ecols = [c for c in dat.columns if c.startswith(f"emb_{k}_")]
            variants = [(f"main + {k}", mv + ecols)] + ([(f"{k} only", ecols)] if only else [])
            for label, cols in variants:
                log(f"{tech} · NN {label}: {len(cols)} predictors")
                for cv, (d, yy, f) in sets.items():
                    tr = train("nn", d[cols], yy, f, seed=config.SEED, n_jobs=config.n_jobs())
                    rows.append(pd.DataFrame({"technology": tech.capitalize(), "predictors": label,
                                              "cv_type": cv, "ROC": tr.resample.ROC}))
                    if cv == CV[0] and label.startswith("main"):
                        g = grid_df.copy()
                        for c in ecols:
                            g[c] = emb[c][rr, cc]
                        g = impute_dat(g, dat[cols].median())[cols]
                        arr = np.full(base.grid.shape, np.nan, np.float32)
                        arr[rr, cc] = tr.model.predict_proba(g.to_numpy(float))[:, 1]
                        raster.write(config.OUT / f"pred_nn_emb_{k}_{t}.tif", arr, base.grid, ["layer"])

    if not rows:
        return
    auc = pd.concat(rows, ignore_index=True)
    auc.to_csv(config.OUT / "nn_emb_auc.csv", index=False)
    summ = (auc.groupby(["technology", "predictors", "cv_type"], sort=False)["ROC"].mean()
            .unstack("cv_type").reset_index())
    ref = summ[summ.predictors == "main (no embeddings)"].set_index("technology")
    for c in CV:
        summ[f"Δ {c}"] = summ[c] - summ.technology.map(ref[c])
    summ = summ.round(3).set_index(["technology", "predictors"])
    summ.to_csv(config.OUT / "nn_emb_summary.csv")
    print("\n" + "═" * 70 + "\n  Neural network with geospatial embeddings — mean AUC-ROC\n" + "═" * 70)
    print(summ.to_string())
    _plot(auc)
    log("saved NN + embeddings results")


def _plot(auc):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharey=True)
    rng = np.random.default_rng(0)
    for i, tech in enumerate(["Solar", "Wind"]):
        for j, cv in enumerate(CV):
            ax = axes[i, j]
            d = auc[(auc.technology == tech) & (auc.cv_type == cv)]
            order = list(dict.fromkeys(d.predictors))
            vals = [d[d.predictors == p].ROC.to_numpy() for p in order]
            if not any(len(v) for v in vals):
                ax.set_visible(False); continue
            bp = ax.boxplot(vals, patch_artist=True, widths=0.6, showfliers=False)
            for k, p in enumerate(bp["boxes"]):
                p.set_facecolor("0.6" if k == 0 else "#E66101" if "only" in order[k] else "#5E3C99")
                p.set_alpha(0.6)
            for k, v in enumerate(vals, 1):
                ax.scatter(k + rng.uniform(-0.1, 0.1, len(v)), v, s=9, color="k", alpha=0.6, zorder=3)
            ax.set_xticks(range(1, len(order) + 1), order, rotation=35, ha="right", fontsize=8)
            ax.set_title(f"{tech} · NN · {cv}", fontsize=10)
            ax.grid(alpha=0.3)
        axes[i, 0].set_ylabel("AUC-ROC")
    fig.suptitle("Neural network with and without geospatial embeddings", fontsize=11)
    fig.tight_layout(); fig.savefig(config.FIG / "f_nn_embeddings.png", dpi=200); plt.close(fig)


if __name__ == "__main__":
    run()
