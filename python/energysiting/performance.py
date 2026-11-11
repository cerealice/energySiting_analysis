"""Model comparison tables and plots — performance.R."""
from __future__ import annotations

import itertools

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from . import config
from .common import log

SET2 = ["#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854"]
SET1 = {"GLM": "#E41A1C", "Lasso": "#377EB8", "RF": "#4DAF4A", "GBM": "#984EA3", "NN": "#FF7F00"}
TECH_COL = {"Solar": "#E8A838", "Wind": "#4A90D9"}


def load_resamples(tech):
    return pd.read_csv(config.OUT / f"resamples_{tech}.csv")


def fmt_resamps(r, tech):
    long = r.melt(id_vars="Resample", var_name="key", value_name="value")
    long[["model", "metric"]] = long["key"].str.split("~", expand=True)
    s = long.groupby(["model", "metric"])["value"].agg(["mean", "std"]).reset_index()
    s["label"] = s.apply(lambda d: f"{d['mean']:.3f} (±{d['std']:.3f})", axis=1)
    s["technology"] = tech
    s["model"] = s["model"].str.upper()
    return s


def holm(p):
    p = np.asarray(p, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj


def pairwise_wilcox(r):
    """pairwise.wilcox.test(..., p.adjust = 'holm') — unpaired rank-sum, lower triangle."""
    roc = r[[c for c in r.columns if c.endswith("~ROC")]]
    roc.columns = [c.replace("~ROC", "") for c in roc.columns]
    names = list(roc.columns)
    pairs = list(itertools.combinations(range(len(names)), 2))
    raw = [mannwhitneyu(roc.iloc[:, i], roc.iloc[:, j], alternative="two-sided").pvalue for i, j in pairs]
    adj = holm(raw)
    tab = pd.DataFrame(np.nan, index=names[1:], columns=names[:-1])
    for (i, j), p in zip(pairs, adj):
        tab.loc[names[j], names[i]] = p
    return tab.round(3)


# ── threshold-dependent metrics on pooled out-of-fold predictions ─────────────
def metrics_at_threshold(pd_, th):
    pc = pd_["X1"].to_numpy() >= th
    obs = pd_["obs"].to_numpy() == "X1"
    TP, FP = np.sum(pc & obs), np.sum(pc & ~obs)
    FN, TN = np.sum(~pc & obs), np.sum(~pc & ~obs)
    prec = TP / (TP + FP) if TP + FP else np.nan
    rec = TP / (TP + FN) if TP + FN else np.nan
    f1 = 2 * prec * rec / (prec + rec) if np.isfinite(prec) and np.isfinite(rec) and prec + rec else np.nan
    return dict(Precision=prec, Recall=rec, F1=f1, TP=TP, FP=FP, FN=FN, TN=TN)


def optimal_threshold(pd_, grid=np.round(np.arange(0.05, 0.951, 0.01), 2)):
    f1 = [metrics_at_threshold(pd_, t)["F1"] for t in grid]
    return float(grid[int(np.nanargmax(f1))])


def curve_points(pd_, grid=np.round(np.arange(0, 1.0001, 0.005), 3)):
    rows = []
    for t in grid:
        m = metrics_at_threshold(pd_, t)
        fpr = m["FP"] / (m["FP"] + m["TN"]) if m["FP"] + m["TN"] else np.nan
        rows.append(dict(threshold=t, Recall=m["Recall"], FPR=fpr, Precision=m["Precision"]))
    return pd.DataFrame(rows)


def pr_auc(pd_):
    c = curve_points(pd_).dropna(subset=["Precision", "Recall"]).sort_values("Recall", kind="stable")
    r, p = c["Recall"].to_numpy(), c["Precision"].to_numpy()
    return float(np.sum(np.diff(r) * (p[:-1] + p[1:]) / 2))


def run():
    config.ensure_dirs()
    res = {t.capitalize(): load_resamples(t) for t in config.TECHS}
    summ = pd.concat([fmt_resamps(r, t) for t, r in res.items()], ignore_index=True)
    summ.to_csv(config.OUT / "performance_summary.csv", index=False)

    print("\n" + "═" * 58 + "\n  Model performance — 10-fold CV (mean ± SD)\n" + "═" * 58)
    tbl = summ[summ.metric == "ROC"].sort_values(["technology", "mean"], ascending=[True, False])
    print(tbl[["technology", "model", "mean", "std"]].to_string(index=False))
    print("\n── Full table (ROC / Sens / Spec) ──")
    print(summ.pivot_table(index=["technology", "model"], columns="metric", values="label", aggfunc="first"))
    for tech in res:
        best = tbl[tbl.technology == tech].iloc[0]["model"]
        print(f"Best model — {tech:5s}: {best}")
    for tech, r in res.items():
        print(f"\n── Pairwise Wilcoxon on ROC ({tech.lower()}, Holm) ──")
        print(pairwise_wilcox(r))

    # 4a. box-plot of fold ROC
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, (tech, r) in zip(axes, res.items()):
        roc = r[[c for c in r.columns if c.endswith("~ROC")]]
        roc.columns = [c.replace("~ROC", "").upper() for c in roc.columns]
        order = roc.median().sort_values().index
        bp = ax.boxplot([roc[m] for m in order], vert=False, patch_artist=True, widths=0.6)
        for patch, m in zip(bp["boxes"], order):
            patch.set_facecolor(SET2[sorted(roc.columns).index(m) % 5]); patch.set_alpha(0.7)
        rng = np.random.default_rng(1)
        for k, m in enumerate(order, 1):
            ax.scatter(roc[m], k + rng.uniform(-0.1, 0.1, len(roc)), s=8, color="k", alpha=0.5)
        ax.set_yticks(range(1, len(order) + 1), order)
        ax.set_xlabel("AUC-ROC (10-fold CV)"); ax.set_title(tech, loc="left")
        ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(config.FIG / "f_performance_roc.png", dpi=300); plt.close(fig)

    # 4b. variable importance, mean of RF + GBM, top 12
    imp = pd.read_csv(config.OUT / "imp.csv")
    top = (imp[imp.model.isin(["RF", "GBM"])].groupby(["tech", "rowname"])["Overall"].mean()
           .reset_index())
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, tech in zip(axes, ["Solar", "Wind"]):
        d = top[top.tech == tech].nlargest(12, "Overall").sort_values("Overall")
        ax.barh(d.rowname, d.Overall, color=TECH_COL[tech], alpha=0.85)
        ax.set_title(tech, color="white", backgroundcolor="0.2")
        ax.set_xlabel("Variable importance (mean RF + GBM)")
    fig.suptitle("Top 12 predictors — RF & GBM average")
    fig.tight_layout(); fig.savefig(config.FIG / "f_varimp.png", dpi=300); plt.close(fig)

    # 7. precision / recall / F1 / PR-AUC
    rows, curves = [], []
    for tech in res:
        cv = pd.read_csv(config.OUT / f"cvpred_{tech.lower()}.csv")
        for key in config.MODEL_NAMES:
            d = cv[cv.model == key]
            name = config.MODEL_DISPLAY[key]
            opt = optimal_threshold(d)
            m05, mop, pra = metrics_at_threshold(d, 0.5), metrics_at_threshold(d, opt), pr_auc(d)
            for ttype, th, m in (("fixed_0.5", 0.5, m05), ("optimal_F1", opt, mop)):
                rows.append(dict(technology=tech, model=name, threshold_type=ttype, threshold=th,
                                 Precision=m["Precision"], Recall=m["Recall"], F1=m["F1"], PR_AUC=pra))
            curves.append(curve_points(d).assign(model=name, technology=tech))
    thr = pd.DataFrame(rows)
    thr.to_csv(config.OUT / "threshold_metrics.csv", index=False)
    print("\n" + "═" * 58 + "\n  Precision / Recall / F1 / PR-AUC — 10-fold CV (pooled)\n" + "═" * 58)
    print(thr.round(3).to_string(index=False))
    curves = pd.concat(curves, ignore_index=True)

    for kind, (xc, yc, xl, yl, title, fname) in {
        "roc": ("FPR", "Recall", "False positive rate (1 − Specificity)", "True positive rate (Recall)",
                "ROC curves — 10-fold CV (pooled folds)", "f_roc_curves.png"),
        "pr": ("Recall", "Precision", "Recall (True positive rate)", "Precision (Positive predictive value)",
               "Precision–Recall curves — 10-fold CV (pooled folds)", "f_pr_curves.png")}.items():
        fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharey=True)
        for ax, tech in zip(axes, ["Solar", "Wind"]):
            for name, d in curves[curves.technology == tech].groupby("model"):
                d = d.dropna(subset=[xc, yc])
                ax.plot(d[xc], d[yc], lw=1.2, color=SET1[name], label=name)
            if kind == "roc":
                ax.plot([0, 1], [0, 1], "--", color="0.6")
            ax.set_title(tech, color="white", backgroundcolor="0.2")
            ax.set_xlabel(xl); ax.grid(alpha=0.3)
        axes[0].set_ylabel(yl); axes[1].legend(title="Model")
        fig.suptitle(title); fig.tight_layout()
        fig.savefig(config.FIG / fname, dpi=300); plt.close(fig)
    log("saved performance figures to " + str(config.FIG))


if __name__ == "__main__":
    run()
