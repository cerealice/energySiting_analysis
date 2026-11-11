"""Regional summaries and random-slope analysis — data.R.

* masks the probability maps to the eligible area → results_masked.tif
* mean probability by NUTS-1 macro-region (rgn_results.csv)
* GLMM with NUTS-2 random slopes (glmm.LogitGLMM, replacing lme4::glmer):
    solar → slopes for pop, tx, env (fitted one at a time)
    wind  → joint (cf + tx + lag | region), falling back to one at a time
  each falling back to a random intercept, then to stratified per-region GLMs,
  exactly the cascade used in data.R.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import config, raster
from .common import log
from .glm import BinomialGLM
from .glmm import LogitGLMM

CORE = ["cf", "tx", "sub", "lag", "env", "slope", "pop", "gdp_pc",
        "unemploy", "inst_quality", "roads", "poverty"]
RV = {"solar": ["pop", "tx", "env"], "wind": ["cf", "tx", "lag"]}
RV_LABEL = {"pop": "Population density", "tx": "Transmission dist", "env": "Environmental score",
            "cf": "Capacity factor", "lag": "Spatial lag"}
MAP_MODELS = ["glm", "lasso", "rf", "xg"]          # order of results list in data.R


def masked_results(base):
    bands, names = [], []
    for tech, t in config.TECHS.items():
        roi = raster.read(config.OUT / f"{tech}_absence_roi.tif").band()
        for m in MAP_MODELS:
            p = raster.read(config.OUT / f"{config.PRED_FILES[m]}_{t}.tif").band()
            bands.append(np.where(np.isfinite(roi), p, np.nan))
            names.append(f"{config.MODEL_DISPLAY[m]} {tech.capitalize()}")
    arr = np.stack(bands)
    raster.write(config.OUT / "results_masked.tif", arr, base.grid, names)
    return arr, names


def regional_means(arr, names, nuts_idx):
    n1 = np.array([config.NUTS1_OF[i] for i in config.NUTS2_IDS] + [None], dtype=object)
    macro = n1[np.where(nuts_idx >= 0, nuts_idx, len(config.NUTS2_IDS))]
    rows = []
    for band, name in zip(arr, names):
        model, tech = name.split(" ")
        for reg in config.NUTS1_LEVELS:
            v = band[macro == reg]
            rows.append(dict(region=reg, mean=np.nanmean(v), model=model, tech=tech))
    return pd.DataFrame(rows)


def assign_nuts2(tech):
    dat = pd.read_csv(config.OUT / f"{tech}.csv")
    dat["treat"] = (dat["treat"] == "X1").astype(int)
    ab = pd.read_csv(config.OUT / f"absence_{tech}.csv")[["id", "nuts2"]]
    ab["region"] = ab["nuts2"].map(config.NUTS2_NAME)
    pres = pd.read_csv(config.DERIVED / f"{tech}_hull_existing.csv")[["unique_id", "state_code"]]
    a = dat[dat.treat == 0].merge(ab[["id", "region"]], left_on="zone", right_on="id", how="left")
    p = dat[dat.treat == 1].merge(pres.rename(columns={"state_code": "region"}),
                                  left_on="zone", right_on="unique_id", how="left")
    out = pd.concat([a.drop(columns="id"), p.drop(columns="unique_id")], ignore_index=True)
    return out.dropna(subset=["region"])


def _fit(da, core, rv):
    X = np.column_stack([np.ones(len(da)), da[core].to_numpy(float)])
    Z = np.column_stack([np.ones(len(da))] + [da[v].to_numpy(float) for v in rv])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return LogitGLMM().fit(X, Z, da["region"].to_numpy(), da["treat"].to_numpy())


def _stratified(da, core, rv):
    rows = []
    for reg, sub in da.groupby("region"):
        if len(sub) < 15 or sub.treat.nunique() < 2:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = BinomialGLM().fit(sub[core], sub["treat"])
        s = fit.summary()
        if rv in s.index:
            rows.append(dict(region=reg, variable=rv, R_effect=s.loc[rv, "Estimate"],
                             SE=s.loc[rv, "Std. Error"] * 1.96, model_type="stratified"))
    return pd.DataFrame(rows)


def random_effects(tech, da):
    core = [v for v in CORE if v in da.columns]
    rvs = RV[tech]
    if tech == "wind":
        fit = _fit(da, core, rvs)
        if not fit.singular_:
            log("  [RE] joint 3-slope GLMM converged for wind")
            return pd.concat([pd.DataFrame(dict(region=fit.levels_, variable=rv, R_effect=fit.b_[:, k + 1],
                                                SE=np.sqrt(fit.condvar_[:, k + 1, k + 1]) * 1.96,
                                                model_type="slope"))
                              for k, rv in enumerate(rvs)], ignore_index=True)
        log("  [RE] joint 3-slope GLMM singular for wind — fitting slopes individually")
    out = []
    for rv in rvs:
        fit = _fit(da, core, [rv])
        if not fit.singular_:
            out.append(pd.DataFrame(dict(region=fit.levels_, variable=rv, R_effect=fit.b_[:, 1],
                                         SE=np.sqrt(fit.condvar_[:, 1, 1]) * 1.96, model_type="slope")))
            continue
        log(f"  [RE] slope ({rv} | region) singular for {tech} — trying (1 | region)")
        fit = _fit(da, core, [])
        if not fit.singular_:
            out.append(pd.DataFrame(dict(region=fit.levels_, variable=rv, R_effect=fit.b_[:, 0],
                                         SE=np.sqrt(fit.condvar_[:, 0, 0]) * 1.96, model_type="intercept")))
            continue
        log(f"  [RE] GLMM singular for {tech}/{rv} — stratified per-region GLM")
        out.append(_stratified(da, core, rv))
    return pd.concat(out, ignore_index=True)


def panel_label(d):
    lab = d["variable"].map(RV_LABEL)
    d = d.assign(variable=lab)
    d["panel_label"] = np.select(
        [d.model_type == "intercept", d.model_type == "stratified"],
        [lab + "\n(intercept only)", lab + "\n(per-region GLM)"], default=lab)
    return d


def run():
    config.ensure_dirs()
    base = raster.read(config.BASE_RASTER)
    arr, names = masked_results(base)
    nuts_idx = np.where(np.isfinite(base.band()), raster.nuts2_index(), -1)
    rgn = regional_means(arr, names, nuts_idx)
    rgn.to_csv(config.OUT / "rgn_results.csv", index=False)
    print(rgn.pivot_table(index=["tech", "region"], columns="model", values="mean").round(3))
    for tech, t in config.TECHS.items():
        da = assign_nuts2(tech)
        da.to_csv(config.OUT / f"{t}_dat_nuts2.csv", index=False)
        d = panel_label(random_effects(tech, da))
        d.to_csv(config.OUT / f"re_{tech}.csv", index=False)
        log(f"{tech}: random effects — {d.groupby('panel_label').size().to_dict()}")


if __name__ == "__main__":
    run()
