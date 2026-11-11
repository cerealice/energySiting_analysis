"""Presence / pseudo-absence models + suitability maps — modeling.R.

Per technology:
  1. split the background zones into 10 groups; fit a binomial GLM on each
     group + all presences → coefficient table (rst) and AIC;
  2. keep the group with the 5th-smallest AIC (the "median" draw) as the
     training set (derived/py/<tech>.csv);
  3. 10-fold CV of GLM, Lasso, GBM, RF and NN (scikit-learn, see learners.py);
  4. variable importance, and probability maps for the future-infrastructure
     scenario (derived/py/pred_*_<s|w>.tif).

Outputs mirror model_results.RData as CSV + joblib files in derived/py/.
"""
from __future__ import annotations

import warnings

import joblib
import numpy as np
import pandas as pd

from . import config, raster
from .common import impute_dat, load_stacks, log, prediction_frame
from .glm import BinomialGLM
from .learners import stratified_folds, train, var_imp


def make_groups(n):
    """rep(1:10, each = floor(n/10)) followed by n %% 10 tens."""
    each = n // 10
    return np.concatenate([np.repeat(np.arange(1, 11), each), np.repeat(10, n % 10)])


def glm_groups(bg: pd.DataFrame, ex: pd.DataFrame):
    rst, aic = [], []
    for g in range(1, 11):
        dat = impute_dat(pd.concat([bg[bg.group == g].drop(columns="group"), ex], ignore_index=True))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = BinomialGLM().fit(dat[config.MODEL_VARS], dat["treat"])
        s = fit.summary().drop(index="(Intercept)")
        rst.append(pd.DataFrame({
            "var_id": s.index, "var": [config.COEF_LABELS.get(v, v) for v in s.index],
            "pe": s["Estimate"].to_numpy(), "se": s["Std. Error"].to_numpy(),
            "color": np.where(s["Pr(>|z|)"] < 0.05, "Y", "N"), "Group": g}))
        aic.append(fit.aic_)
    return pd.concat(rst, ignore_index=True), np.array(aic)


def run_tech(tech, stacks, base):
    t = config.TECHS[tech]
    ex = pd.read_csv(config.OUT / f"existing_cov_{tech}.csv")
    bg = pd.read_csv(config.OUT / f"bg_cov_{tech}.csv")
    bg["group"] = make_groups(len(bg))

    rst, aic = glm_groups(bg, ex)
    best_group = int(np.argsort(aic, kind="stable")[4]) + 1          # which(aic == sort(aic)[5])
    log(f"{tech}: GLM AIC by group {np.round(aic, 1).tolist()} → using group {best_group}")

    dat = impute_dat(pd.concat([bg[bg.group == best_group].drop(columns="group"), ex],
                               ignore_index=True))
    out = dat.copy()
    out["treat"] = np.where(out["treat"] == 1, "X1", "X0")
    out.to_csv(config.OUT / f"{tech}.csv", index=False)

    X, y = dat[config.MODEL_VARS], dat["treat"].astype(int).to_numpy()
    medians = dat[config.MODEL_VARS].median()
    folds = stratified_folds(y, 10, config.SEED)
    joblib.dump(folds, config.OUT / f"folds_{tech}.joblib")

    cov, fut, tech_stacks = stacks
    base_mask = np.isfinite(base.band())
    grid_df, (rr, cc) = prediction_frame(cov, fut, tech_stacks[tech], base_mask)
    # NOTE: luh3_c4per is NA everywhere in covStack, so R's raster::predict (na.rm)
    # dropped every cell and wrote empty maps. We impute exactly as for training.
    grid_df = impute_dat(grid_df, medians)[config.MODEL_VARS]

    def write_map(model_key, p):
        arr = np.full(base.grid.shape, np.nan, np.float32)
        arr[rr, cc] = p
        raster.write(config.OUT / f"{config.PRED_FILES[model_key]}_{t}.tif", arr, base.grid, ["layer"])

    # Logistic-regression map from the R-style GLM (glm1_<tech> in modeling.R)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        glm1 = BinomialGLM().fit(X, y)
    write_map("glm", glm1.predict_proba1(grid_df))

    resamples, imps, preds, tunes = [], [], [], []
    for name in config.MODEL_NAMES:
        log(f"{tech}: training {config.MODEL_DISPLAY[name]} (10-fold CV)")
        tr = train(name, X, y, folds, seed=config.SEED, n_jobs=config.n_jobs())
        log(f"   best {tr.best_params if name != 'lasso' else {'lambda': round(tr.best_params['_lambda'], 5)}}"
            f"  ROC={tr.resample.ROC.mean():.3f}")
        joblib.dump(tr, config.OUT / f"mdl_{tech}{name}.joblib")
        r = tr.resample.set_index("Resample")
        r.columns = [f"{name}~{c}" for c in r.columns]
        resamples.append(r)
        imp = var_imp(tr, X, y, seed=config.SEED)
        imps.append(pd.DataFrame({"var_id": imp.index,
                                  "rowname": [config.IMP_LABELS.get(v, v) for v in imp.index],
                                  "Overall": imp.to_numpy(), "model": config.MODEL_DISPLAY[name],
                                  "tech": tech.capitalize()}))
        preds.append(tr.pred.assign(model=name))
        tunes.append(tr.results.assign(model=name))
        if name != "glm":     # R predicts maps for lasso, xg, rf, nn (glm map comes from glm1)
            write_map(name, tr.model.predict_proba(grid_df.to_numpy(float))[:, 1])

    pd.concat(resamples, axis=1).reset_index().to_csv(config.OUT / f"resamples_{tech}.csv", index=False)
    pd.concat(preds, ignore_index=True).to_csv(config.OUT / f"cvpred_{tech}.csv", index=False)
    pd.concat(tunes, ignore_index=True).to_csv(config.OUT / f"tuning_{tech}.csv", index=False)
    rst.to_csv(config.OUT / f"rst_{t}.csv", index=False)
    return pd.concat(imps, ignore_index=True)


def run():
    config.ensure_dirs()
    stacks = load_stacks()
    base = raster.read(config.BASE_RASTER)
    imp = pd.concat([run_tech(tech, stacks, base) for tech in ("solar", "wind")], ignore_index=True)
    imp.to_csv(config.OUT / "imp.csv", index=False)
    log("saved model results to " + str(config.OUT))


if __name__ == "__main__":
    run()
