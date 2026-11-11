"""caret::train equivalents built on scikit-learn.

Each R model maps to a scikit-learn estimator and tuning grid:

=========  =====================================  ==========================================
caret      R grid (modeling.R)                    scikit-learn
=========  =====================================  ==========================================
glm        –                                      LogisticRegression(C=inf)  (unpenalised)
glmnet     alpha=1, lambda=10^seq(-3,3,100)       LogisticRegression(l1_ratio=1, C=1/(n·λ)),
                                                  inputs standardised (glmnet does this too)
gbm        n.trees{50,100} × depth{3,6} ×         GradientBoostingClassifier(n_estimators,
           shrinkage{.01,.1} × minobs{5,10}       max_leaf_nodes=depth+1, learning_rate,
                                                  min_samples_leaf, subsample=0.5)
rf         mtry = caret default (3 values)        RandomForestClassifier(500 trees,
                                                  max_features ∈ {2, p/2, p})
nnet       size{5,10,20} × decay{.001,.01,.1},    MLPClassifier(1 hidden layer, logistic,
           centre+scale                           lbfgs, alpha=2·decay, max_iter=100)
=========  =====================================  ==========================================

Resampling mirrors ``trainControl(method="cv", number=10, classProbs=TRUE,
summaryFunction=twoClassSummary)``: per-fold ROC / Sens / Spec, best tune chosen
by mean ROC, final model refit on all data, out-of-fold predictions saved at the
best tune (``savePredictions``). As in caret, the *first* class level (X0,
absence) is the "event" for Sens/Spec. All models share the same folds so that
model comparisons are paired.
"""
from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import make_scorer, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .glm import BinomialGLM


# ── estimators & grids ────────────────────────────────────────────────────────
def make_estimator(name, n_samples, n_features, seed):
    if name == "glm":
        est = Pipeline([("scale", StandardScaler()),
                        ("clf", LogisticRegression(C=np.inf, solver="lbfgs", max_iter=10000))])
        grid = [{}]
    elif name == "lasso":
        est = Pipeline([("scale", StandardScaler()),
                        ("clf", LogisticRegression(l1_ratio=1.0, solver="saga", max_iter=5000,
                                                   tol=1e-4, random_state=seed))])
        lambdas = 10 ** np.linspace(-3, 3, 100)
        # glmnet minimises  -loglik/n + λ‖β‖₁ ; sklearn minimises  C·Σloss + ‖β‖₁
        grid = [{"clf__C": 1.0 / (n_samples * lam), "_lambda": lam} for lam in lambdas]
    elif name == "xg":
        est = GradientBoostingClassifier(subsample=0.5, max_depth=None, random_state=seed)
        grid = [{"n_estimators": n, "max_leaf_nodes": d + 1, "learning_rate": s,
                 "min_samples_leaf": m, "_interaction.depth": d}
                for n, d, s, m in itertools.product([50, 100], [3, 6], [0.01, 0.1], [5, 10])]
    elif name == "rf":
        est = RandomForestClassifier(n_estimators=500, random_state=seed, n_jobs=1)
        p = n_features
        mtry = sorted(set(int(v) for v in np.floor(np.linspace(2, p, 3))))   # caret::var_seq
        grid = [{"max_features": m} for m in mtry]
    elif name == "nn":
        est = Pipeline([("scale", StandardScaler()),
                        ("clf", MLPClassifier(activation="logistic", solver="lbfgs",
                                              max_iter=100, random_state=seed))])
        grid = [{"clf__hidden_layer_sizes": (s,), "clf__alpha": 2 * d, "_size": s, "_decay": d}
                for s, d in itertools.product([5, 10, 20], [0.001, 0.01, 0.1])]
    else:
        raise ValueError(name)
    return est, grid


def _sk_params(p):
    return {k: v for k, v in p.items() if not k.startswith("_")}


def _fit_fold(est, params, X, y, tr, te):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        m = clone(est).set_params(**_sk_params(params)).fit(X[tr], y[tr])
    return m.predict_proba(X[te])[:, 1]


def two_class_summary(obs, p1):
    """caret::twoClassSummary with lev = c("X0","X1"): event = X0."""
    obs = np.asarray(obs)
    pred1 = p1 > 0.5                   # caret picks the level with max prob; ties → X0
    roc = roc_auc_score(obs, p1) if len(np.unique(obs)) == 2 else np.nan
    sens = np.mean(~pred1[obs == 0]) if np.any(obs == 0) else np.nan
    spec = np.mean(pred1[obs == 1]) if np.any(obs == 1) else np.nan
    return roc, sens, spec


@dataclass
class TrainResult:
    name: str
    best_params: dict
    model: object
    resample: pd.DataFrame          # Resample, ROC, Sens, Spec  (best tune)
    pred: pd.DataFrame              # rowIndex, obs, X0, X1, Resample (best tune)
    results: pd.DataFrame           # mean metrics for every tuning row
    features: list = field(default_factory=list)


def train(name, X: pd.DataFrame, y, folds, seed=42, n_jobs=1) -> TrainResult:
    Xv, yv = X.to_numpy(float), np.asarray(y, int)
    est, grid = make_estimator(name, len(Xv), Xv.shape[1], seed)
    jobs = [(gi, fi) for gi in range(len(grid)) for fi in range(len(folds))]
    preds = Parallel(n_jobs=n_jobs)(
        delayed(_fit_fold)(est, grid[gi], Xv, yv, folds[fi][0], folds[fi][1]) for gi, fi in jobs)
    per = {}
    for (gi, fi), p in zip(jobs, preds):
        per.setdefault(gi, {})[fi] = p
    rows = []
    for gi in range(len(grid)):
        m = [two_class_summary(yv[folds[fi][1]], per[gi][fi]) for fi in range(len(folds))]
        m = np.array(m)
        rows.append({**{k.lstrip("_"): (str(v) if isinstance(v, tuple) else v) for k, v in grid[gi].items()},
                     "ROC": np.nanmean(m[:, 0]), "Sens": np.nanmean(m[:, 1]), "Spec": np.nanmean(m[:, 2]),
                     "ROCSD": np.nanstd(m[:, 0], ddof=1)})
    results = pd.DataFrame(rows)
    best = int(np.nanargmax(results["ROC"].to_numpy()))
    # caret: for glmnet ties, the largest lambda wins (most regularised) – emulate
    if name == "lasso":
        tie = np.where(np.isclose(results["ROC"], results["ROC"].iloc[best]))[0]
        best = int(tie[np.argmax(results.loc[tie, "lambda"].to_numpy())])
    bp = grid[best]
    res, pr = [], []
    for fi, (tr, te) in enumerate(folds):
        p = per[best][fi]
        roc, sens, spec = two_class_summary(yv[te], p)
        res.append({"Resample": f"Fold{fi + 1:02d}", "ROC": roc, "Sens": sens, "Spec": spec})
        pr.append(pd.DataFrame({"rowIndex": te, "obs": np.where(yv[te] == 1, "X1", "X0"),
                                "X0": 1 - p, "X1": p, "Resample": f"Fold{fi + 1:02d}"}))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        final = clone(est).set_params(**_sk_params(bp)).fit(Xv, yv)
    return TrainResult(name, bp, final, pd.DataFrame(res),
                       pd.concat(pr, ignore_index=True), results, list(X.columns))


def stratified_folds(y, k=10, seed=42):
    """caret::createFolds(y, k) analogue (stratified on the outcome)."""
    skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
    return [(tr, te) for tr, te in skf.split(np.zeros(len(y)), y)]


# ── variable importance (caret::varImp, scale = TRUE) ─────────────────────────
def _scale100(v):
    v = np.asarray(v, float)
    rng = np.nanmax(v) - np.nanmin(v)
    return (v - np.nanmin(v)) / rng * 100 if rng > 0 else np.zeros_like(v)


def var_imp(tr: TrainResult, X: pd.DataFrame, y, seed=42) -> pd.Series:
    feats = tr.features
    m = tr.model
    if tr.name == "glm":
        # caret varImp.glm: |z| of each coefficient (aliased terms dropped)
        s = BinomialGLM().fit(X, y).summary().drop(index="(Intercept)", errors="ignore")
        raw = (s["Estimate"] / s["Std. Error"]).abs().reindex(feats)
    elif tr.name == "lasso":
        # varImp.glmnet: |β| at the selected λ, on the original covariate scale
        sc, clf = m.named_steps["scale"], m.named_steps["clf"]
        with np.errstate(divide="ignore", invalid="ignore"):
            raw = pd.Series(np.abs(clf.coef_[0] / sc.scale_), index=feats).fillna(0)
    elif tr.name == "xg":
        raw = pd.Series(m.feature_importances_, index=feats)     # ≈ gbm relative influence
    elif tr.name == "rf":
        # importance=TRUE → class-specific mean decrease in accuracy; R keeps the X1 column
        pi = permutation_importance(m, X.to_numpy(float), np.asarray(y),
                                    scoring=make_scorer(recall_score, pos_label=1),
                                    n_repeats=5, random_state=seed, n_jobs=1)
        raw = pd.Series(pi.importances_mean, index=feats)
    elif tr.name == "nn":
        # varImp.nnet: Garson / Gevrey weight-product importance
        clf = m.named_steps["clf"]
        w_ih = np.abs(clf.coefs_[0])            # (inputs, hidden)
        w_ho = np.abs(clf.coefs_[1][:, 0])      # (hidden,)
        contrib = w_ih * w_ho[None, :]
        contrib = contrib / contrib.sum(axis=0, keepdims=True)
        raw = pd.Series(contrib.sum(axis=1), index=feats)
    else:
        raise ValueError(tr.name)
    raw = raw.astype(float)
    return pd.Series(_scale100(raw.to_numpy()), index=raw.index)
