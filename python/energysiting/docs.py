"""Generate docs/pipeline.html — a self-documenting description of the current version.

Everything on the page is read from the code and the outputs at generation time:
pipeline steps and their descriptions (module docstrings), the predictor list for
each technology (config.model_vars), WorldTensor years (manifest.json), model
estimators and tuning grids (learners.make_estimator), recent commits, and — when
the pipeline has been run — presences, performance, spatial CV, importances,
regional means and figures.

    python -m energysiting.docs            # writes <ES_ROOT>/docs/pipeline.html
run_all.py calls it at the end of every run.
"""
from __future__ import annotations

import ast
import datetime as dt
import html
import importlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

OUT_HTML = config.ROOT / "docs" / "pipeline.html"
PKG = Path(__file__).resolve().parent
E = html.escape


# ── facts about each predictor ────────────────────────────────────────────────
def _wt_years():
    try:
        from .setup.worldtensor import load_manifest
        m = load_manifest()
        return {k: v["years"] for k, v in (m or {}).get("layers", {}).items()}
    except Exception:
        return {}


def describe(var: str, wt: dict) -> dict:
    """group, source, native resolution and period for one predictor."""
    def wtp(name):
        y = wt.get(name)
        return f"{y[0]}–{y[-1]} mean" if y else f"latest {config.WT_YEARS} years (mean)"
    if var in ("tx", "roads", "sub"):
        what = {"tx": "transmission lines ≥ 110 kV", "roads": "roads", "sub": "substations (nodes + areas)"}[var]
        return dict(group="Infrastructure", source=f"OpenStreetMap (Geofabrik) — distance to {what}",
                    res="1 km", period="current OSM; future scenario = same layer (no planned data)" if var != "roads" else "current OSM")
    if var == "slope":
        return dict(group="Terrain & population", source="SRTM 30″ DEM (geodata) → slope in degrees", res="1 km", period="static")
    if var == "pop":
        return dict(group="Terrain & population", source="GPWv4 population density (geodata)", res="1 km", period="2020")
    socio = {"unemploy": ("ISTAT Labour Force Survey unemployment rate", "NUTS-3", "latest year"),
             "foreignborn": ("ISTAT census, share born abroad", "municipality", "latest year"),
             "poverty": ("MEF IRPEF mean taxable income (poverty proxy)", "municipality", "2022 incomes"),
             "gdp_pc": ("GDP per capita, Zenodo 10.5281/zenodo.11121790", "NUTS-3", "latest year"),
             "inst_quality": ("Institutional quality index, Zenodo 10.5281/zenodo.11121790", "NUTS-3", "latest year")}
    if var in socio:
        s, r, p = socio[var]
        return dict(group="Socioeconomic", source=s, res=r, period=p)
    if var.startswith("chelsa_"):
        return dict(group="Climate — CHELSA", source="CHELSA v2.1 bioclimatic variable", res="1 km (30″)", period="1981–2010 normals")
    if var.startswith("era5land_"):
        yrs = config.CLIMATE_YEARS
        return dict(group="Climate — ERA5-Land", source="ERA5-Land monthly means (Copernicus CDS)",
                    res="0.1° (~9 km)", period=f"{yrs[0]}–{yrs[-1]} mean")
    if var == "gwa_ws100":
        return dict(group="Wind & solar resource", source="Global Wind Atlas v3 mean wind speed at 100 m",
                    res="250 m (averaged to 1 km)", period="2008–2017 (ERA5 downscaled)")
    if var == "cerra_ws100_iav":
        yrs = config.CLIMATE_YEARS
        return dict(group="Wind & solar resource", source="CERRA 100 m wind speed: SD of annual means",
                    res="5.5 km", period=f"{yrs[0]}–{yrs[-1]}")
    if var.startswith("wclim_"):
        return dict(group="Climate — WorldClim", source="WorldClim 2.1 bioclimatic variable", res="1 km (30″)", period="1970–2000 normals")
    if var in config.WIND_ERA5_DERIVED:
        return dict(group="Climate — ERA5 derived", source="computed from WorldTensor ERA5 annual-mean U/V (speed of the mean vector)",
                    res="0.25°", period=wtp("era5_u100_mean"))
    if var.startswith("era5_"):
        return dict(group="Climate — ERA5", source="ERA5 via WorldTensor", res="0.25° (~25 km)", period=wtp(var))
    if var.startswith("luh3_"):
        return dict(group="Land use — LUH3", source="LUH3 land-use state fraction via WorldTensor", res="0.25°", period=wtp(var))
    if var == "wt_ndvi_mean":
        return dict(group="Land use — LUH3", source="MODIS NDVI via WorldTensor", res="0.25°", period=wtp(var))
    if var.startswith("aq_"):
        return dict(group="Air quality", source="CAMS EAC4 reanalysis via WorldTensor", res="0.25°", period=wtp(var))
    if var in ("wt_population_density", "wt_ntl_harmonized"):
        src = "GPWv4/UN WPP population density" if "population" in var else "Harmonised nighttime lights (DMSP+VIIRS)"
        return dict(group="Human systems", source=f"{src} via WorldTensor", res="0.25°", period=wtp(var))
    if var in ("wt_elevation_mean", "wt_slope_mean"):
        return dict(group="Terrain & population", source="GMTED2010 via WorldTensor", res="0.25°", period="static")
    if var.startswith("lulc_"):
        return dict(group="Land cover", source="ESA WorldCover fraction (geodata)", res="1 km", period="2021")
    if var.startswith("nuts2_"):
        rid = var.split("_")[1].upper()
        return dict(group="Regions", source=f"NUTS-2 indicator: {config.NUTS2[rid][1]} (reference: Sardegna)",
                    res="1 km", period="NUTS 2016")
    if var == "env":
        return dict(group="Technology", source="0.7 × proximity to Natura 2000 + 0.3 × normalised slope", res="1 km", period="Natura 2000 end-2024")
    if var == "cf":
        return dict(group="Technology", source="Resource: Global Solar Atlas PVOUT (solar) / Global Wind Atlas "
                    "capacity factor, IEC class II at 100 m (wind)", res="~250 m–1 km (averaged to 1 km)",
                    period="long-term (GWA 2008–2017)")
    if var == "lag":
        return dict(group="Technology", source="Share of cells within 50 km with a tracker plant operating before 2017 (0/1)",
                    res="1 km", period="< 2017")
    return dict(group="Other", source="", res="", period="")


GROUP_ORDER = ["Infrastructure", "Terrain & population", "Socioeconomic", "Climate — CHELSA",
               "Climate — WorldClim", "Climate — ERA5-Land", "Climate — ERA5", "Wind & solar resource", "Climate — ERA5 derived", "Land use — LUH3", "Air quality",
               "Human systems", "Land cover", "Regions", "Technology", "Other"]


# ── helpers ───────────────────────────────────────────────────────────────────
def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except Exception:
        return ""


def _doc(module: str) -> str:
    p = PKG / (module.replace("energysiting.", "").replace(".", "/") + ".py")
    try:
        return ast.get_docstring(ast.parse(p.read_text())) or ""
    except Exception:
        return ""


def _csv(name):
    p = config.OUT / name
    return pd.read_csv(p) if p.exists() else None


def _table(df: pd.DataFrame, cls="", index=False, floatfmt="{:.3f}") -> str:
    if df is None or df.empty:
        return "<p class='muted'>Not available.</p>"
    d = df.copy()
    if index:
        d = d.reset_index()
    head = "".join(f"<th>{E(str(c))}</th>" for c in d.columns)
    rows = []
    for _, r in d.iterrows():
        cells = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                cells.append(f"<td class='num'>{'' if np.isnan(v) else floatfmt.format(v)}</td>")
            elif isinstance(v, (int, np.integer)):
                cells.append(f"<td class='num'>{v:,}</td>")
            else:
                cells.append(f"<td>{E(str(v))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class='tw'><table class='{cls}'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def _pre(text: str) -> str:
    return f"<pre class='doc'>{E(text)}</pre>" if text else ""


# ── sections ──────────────────────────────────────────────────────────────────
def sec_steps():
    ra = importlib.import_module("run_all") if "run_all" in globals() else None
    try:
        import sys
        sys.path.insert(0, str(PKG.parent))
        ra = importlib.import_module("run_all")
        setup = [s for s, _ in ra.SETUP]
        main = [s for s, *_ in ra.MAIN]
    except Exception:
        setup, main = [], []
    out = ["<p>Run with <code>bash python/run_all.sh</code> on the cluster or "
           "<code>python python/run_all.py [--setup]</code>. Setup steps build the input layers "
           "(skipped when their outputs are current); analysis steps run every time.</p>"]
    for title, steps in (("Setup (input layers)", setup), ("Analysis", main)):
        out.append(f"<h3>{title}</h3><ol class='steps'>")
        for s in steps:
            mod = "energysiting.tech" if s == "tech" else (
                f"energysiting.setup.{s}" if title.startswith("Setup") else f"energysiting.{s}")
            d = _doc(mod)
            first, _, rest = d.partition("\n\n")
            first = " ".join(first.split())
            out.append(f"<li><details><summary><b>{E(s)}</b> — {E(first)}</summary>{_pre(rest.strip())}</details></li>")
        out.append("</ol>")
    return "".join(out)


def sec_presences():
    out = [_pre(_doc("energysiting.tech"))]
    for tech in config.TECHS:
        p = config.DERIVED / f"{tech}_hull_existing.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p)
        src = d["location_source"] if "location_source" in d else pd.Series(["R / RSE"] * len(d))
        t = (d.assign(source=src).groupby("source")
             .agg(presences=("unique_id", "size"), capacity_MW=("Capacity (MW)", "sum")).reset_index())
        out.append(f"<h3>{tech.capitalize()}: {len(d):,} presences</h3>" + _table(t, floatfmt="{:,.0f}"))
        cov = config.OUT / f"{tech}_presence_coverage.csv"
        if cov.exists():
            c = pd.read_csv(cov)
            out.append("<details><summary>Capacity by region vs RSE totals (OSM completeness)</summary>"
                       + _table(c, floatfmt="{:,.2f}") + "</details>")
    return "".join(out)


def sec_predictors():
    wt = _wt_years()
    sv, wv = config.model_vars("solar"), config.model_vars("wind")
    allv = list(dict.fromkeys(sv + wv))
    rows = []
    for v in allv:
        d = describe(v, wt)
        rows.append(dict(group=d["group"], variable=v, label=config.VAR_LABELS.get(v, config.IMP_LABELS.get(v, v)),
                         source=d["source"], resolution=d["res"], period=d["period"],
                         solar="✓" if v in sv else "", wind="✓" if v in wv else ""))
    df = pd.DataFrame(rows)
    df["g"] = df["group"].map({g: i for i, g in enumerate(GROUP_ORDER)})
    df = df.sort_values(["g"], kind="stable").drop(columns="g")
    counts = df.groupby("group", sort=False).agg(n=("variable", "size"),
                                                  solar=("solar", lambda s: (s == "✓").sum()),
                                                  wind=("wind", lambda s: (s == "✓").sum()))
    counts = counts.reindex([g for g in GROUP_ORDER if g in counts.index])
    toggles = {k: os.environ.get(k, "(default)") for k in
               ("ES_PRESENCE_SOURCE", "ES_WT_EXTRA", "ES_WIND_ERA5_DERIVED", "ES_DROP_VARS", "ES_WT_YEARS")}
    out = [f"<p><b>{len(sv)}</b> predictors for solar, <b>{len(wv)}</b> for wind. Continuous layers are "
           "z-scored over Italy; land cover and regions are 0/1 or fractions. At each presence/absence zone the "
           "layer mean is taken; missing LUH3 → 0, other missing values → training median.</p>",
           "<div class='cards'>" + "".join(
               f"<div class='card'><div class='k'>{E(g)}</div><div class='v'>{r.solar} / {r.wind}</div>"
               f"<div class='muted small'>solar / wind</div></div>" for g, r in counts.iterrows()) + "</div>",
           "<p class='small muted'>Toggles at generation time: " +
           ", ".join(f"<code>{k}={E(v)}</code>" for k, v in toggles.items()) + "</p>",
           "<input id='flt' placeholder='Filter variables…' oninput='filt(this.value)'>",
           _grouped(df)]
    return "".join(out)


def _grouped(df):
    cols = ["variable", "label", "source", "resolution", "period", "solar", "wind"]
    head = "".join(f"<th>{c}</th>" for c in cols)
    rows = []
    for g, d in df.groupby("group", sort=False):
        rows.append(f"<tr class='grp'><td colspan='{len(cols)}'>{E(g)} <span class='muted'>({len(d)})</span></td></tr>")
        for r in d.itertuples():
            rows.append("<tr>" + "".join(f"<td>{E(str(getattr(r, c)))}</td>" for c in cols) + "</tr>")
    return f"<div class='tw'><table class='vars'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def sec_models():
    from .learners import make_estimator
    rows = []
    for name in config.MODEL_NAMES:
        est, grid = make_estimator(name, 1000, 100, config.SEED)
        keys = sorted({k for g in grid for k in g if not k.startswith("_") or k in ("_lambda",)})
        parts = []
        for k in keys:
            vals = sorted({(str(g[k]) if isinstance(g.get(k), tuple) else g.get(k)) for g in grid if k in g},
                          key=lambda x: (str(type(x)), x))
            if k == "_lambda":
                parts.append(f"λ: {len(vals)} values {min(vals):.0e}–{max(vals):.0e} (C = 1/(n·λ))")
            elif k == "clf__C":
                continue
            else:
                parts.append(f"{k.replace('clf__', '')}: {', '.join(str(v) for v in vals)}")
        rows.append(dict(model=config.MODEL_DISPLAY[name], caret=dict(glm="glm", lasso="glmnet", xg="gbm",
                                                                      rf="rf", nn="nnet")[name],
                         estimator=repr(est).replace("\n", " ").replace("  ", ""),
                         tuning="; ".join(parts) or "—", combos=len(grid)))
    d = pd.DataFrame(rows)
    return (_pre(_doc("energysiting.learners")) + _table(d) +
            "<h3>Validation</h3><ul>"
            "<li><b>10-fold stratified CV</b>, same folds for every model; best tuning = highest mean ROC; "
            "final model refit on all training rows.</li>"
            "<li><b>Training set</b>: all presences + one of 10 background groups (the one with the 5th-lowest "
            "GLM AIC), as in R.</li>"
            "<li><b>Spatial block CV</b>: block size from the variogram range of the response (≥ 50 km), "
            "5 folds, GBM and RF re-fitted.</li>"
            "<li><b>Regional heterogeneity</b>: logistic GLMM with NUTS-2 random slopes "
            "(solar: population density, transmission distance, environmental score; wind: capacity factor, "
            "transmission distance, spatial lag).</li>"
            "<li><b>Maps</b>: future-infrastructure scenario, masked to the eligible area; values are relative "
            "suitability (training is balanced 1:1), not absolute probabilities.</li></ul>")


def sec_results():
    perf = _csv("performance_summary.csv")
    if perf is None:
        return "<p class='muted'>No results yet — run the pipeline (results are read from derived/py).</p>"
    perf = perf.assign(model=perf["model"].replace({"XG": "GBM", "LASSO": "Lasso"}))
    roc = perf[perf.metric == "ROC"].pivot(index="model", columns="technology", values="mean")
    sd = perf[perf.metric == "ROC"].pivot(index="model", columns="technology", values="std")
    t = pd.DataFrame({f"{c} AUC": roc[c] for c in roc.columns} | {f"{c} ± SD": sd[c] for c in sd.columns})
    out = ["<h3>10-fold cross-validation (AUC-ROC)</h3>", _table(t, index=True)]
    sp = _csv("spatial_cv_comparison.csv")
    if sp is not None:
        s = sp.groupby(["technology", "model", "cv_type"])["ROC"].mean().unstack()
        out += ["<h3>Random vs spatial-block CV (mean AUC)</h3>", _table(s, index=True)]
        info = _csv("spatial_cv_info.csv")
        if info is not None:
            out.append("<p class='small muted'>Block size: " + ", ".join(
                f"{r.iloc[0]} {float(r['block']) / 1000:.0f} km" for _, r in info.iterrows()) + "</p>")
    sens = _csv("sensitivity_summary.csv")
    if sens is not None:
        out += ["<h3>Leakage sensitivity (mean AUC; Δ = change when the predictors are dropped)</h3>",
                "<p class='small muted'>GBM and RF refitted on the same folds without predictors that may "
                "see the plants (WorldCover &ldquo;Developed&rdquo; maps PV farms as built-up). A large drop means "
                "the full model leaned on them.</p>", _table(sens)]
    nne = _csv("nn_emb_summary.csv")
    if nne is not None:
        out += ["<h3>Neural network + geospatial embeddings (mean AUC; Δ vs the NN without embeddings)</h3>",
                "<p class='small muted'>One embedding product at a time (16 principal components) added to the "
                "main predictors; same random and spatial-block folds. The other models never see embeddings.</p>",
                _table(nne)]
    thr = _csv("threshold_metrics.csv")
    if thr is not None:
        out += ["<details><summary>Precision / recall / F1 / PR-AUC</summary>", _table(thr), "</details>"]
    imp = _csv("imp.csv")
    if imp is not None:
        top = (imp[imp.model.isin(["RF", "GBM"])].groupby(["tech", "rowname"])["Overall"].mean()
               .reset_index().sort_values("Overall", ascending=False))
        cols = []
        for tech in ("Solar", "Wind"):
            d = top[top.tech == tech].head(15)
            bars = "".join(f"<div class='bar'><span>{E(r.rowname)}</span><i style='width:{r.Overall:.0f}%'></i>"
                           f"<b>{r.Overall:.0f}</b></div>" for r in d.itertuples())
            cols.append(f"<div><h4>{tech}</h4>{bars}</div>")
        out += ["<h3>Top predictors (mean of RF and GBM importance, 0–100)</h3>",
                "<div class='two'>" + "".join(cols) + "</div>"]
    rgn = _csv("rgn_results.csv")
    if rgn is not None:
        out += ["<h3>Mean relative suitability by macro-region</h3>",
                _table(rgn.pivot_table(index=["tech", "region"], columns="model", values="mean"), index=True)]
    return "".join(out)


def sec_figures():
    figs = [("f3.png", "Suitability maps and regional means"), ("f_performance_roc.png", "AUC by model"),
            ("f_spatial_cv_comparison.png", "Random vs spatial CV"),
            ("f_sensitivity.png", "Leakage sensitivity"), ("f_nn_embeddings.png", "NN + embeddings"), ("f_varimp.png", "Variable importance"),
            ("f2.png", "GLM coefficients and importance"), ("f4.png", "Regional random effects"),
            ("f1.png", "Presences and pseudo-absences"), ("f_roc_curves.png", "ROC curves"),
            ("f_pr_curves.png", "Precision–recall curves")]
    have = [(f, c) for f, c in figs if (config.FIG / f).exists()]
    if not have:
        return "<p class='muted'>No figures yet.</p>"
    rel = os.path.relpath(config.FIG, OUT_HTML.parent)
    return "<div class='figs'>" + "".join(
        f"<figure><a href='{E(rel)}/{f}'><img loading='lazy' src='{E(rel)}/{f}' alt='{E(c)}'></a>"
        f"<figcaption>{E(c)}</figcaption></figure>" for f, c in have) + "</div>"


def sec_sources():
    rows = [("GEM Global Solar / Wind Power Tracker (Feb 2026)", "tracker plants, start year, capacity", "data/ (git)"),
            ("OpenStreetMap Italy (Geofabrik)", "plant footprints, turbines, roads, lines, substations", "download"),
            ("RSE Atlante (2021 solar, 2019 wind)", "municipal installed capacity (coverage check / R mode)", "data/ (git)"),
            ("Eurostat GISCO", "country, NUTS, municipality boundaries", "download"),
            ("geodata.ucdavis.edu", "SRTM DEM, GPWv4 population, ESA WorldCover", "download"),
            ("CHELSA v2.1 (WSL)", "bioclimatic normals 1981–2010", "download (Italy window)"),
            ("Global Solar Atlas / Global Wind Atlas (World Bank)", "PVOUT; wind speed and capacity factor at 100 m", "download"),
            ("Copernicus CDS: ERA5-Land, CERRA", "radiation, pressure (9 km); 100 m wind variability (5.5 km)", "CDS API (account)"),
            ("ISTAT, MEF", "unemployment, foreign-born share, taxable income", "data/ (git)"),
            ("Zenodo 10.5281/zenodo.11121790", "GDP per capita, institutional quality", "data/ (git)"),
            ("WorldTensor, Zenodo 10.5281/zenodo.19047618", "ERA5, LUH3, NDVI, CAMS, population, NTL, GMTED", "download (manifest.json)"),
            ("EEA Natura 2000 end-2024", "protected areas (environmental score)", "manual download")]
    return _table(pd.DataFrame(rows, columns=["source", "used for", "how obtained"]))


def sec_changes():
    log = _git("log", "-25", "--date=short", "--format=%h|%ad|%s", "--", "python")
    if not log:
        return "<p class='muted'>Git history not available.</p>"
    rows = [l.split("|", 2) for l in log.splitlines()]
    return _table(pd.DataFrame(rows, columns=["commit", "date", "change"]))


def sec_r_diff():
    readme = (PKG.parent / "README.md")
    if not readme.exists():
        return ""
    txt = readme.read_text()
    i = txt.find("## Deliberate differences from the R code")
    if i < 0:
        return ""
    body = txt[i:].split("\n## ", 2)
    section = body[0].split("\n", 1)[1] if body else ""
    items = [s.strip().lstrip("*").strip().replace("\n  ", " ") for s in section.split("\n* ") if s.strip()]
    return "<ul>" + "".join(f"<li>{E(it)}</li>" for it in items) + "</ul>"


CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--muted:#6b6f76;--card:#ffffff;--line:#e3e1dc;--acc:#2f6f5e;--acc2:#e8a838;--code:#f2f0eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15171a;--fg:#e6e6e3;--muted:#9aa0a6;--card:#1d2024;--line:#2e3237;--acc:#6cc4a8;--acc2:#e8a838;--code:#24282d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:28px 16px 18px;border-bottom:1px solid var(--line)}header h1{margin:0 0 4px;font-size:24px}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:5}
nav .wrap{white-space:nowrap;overflow-x:auto;scrollbar-width:thin}nav a{display:inline-block;padding:10px 10px;color:var(--muted);text-decoration:none;font-size:14px}nav a:hover{color:var(--acc)}
section{padding:22px 0;border-bottom:1px solid var(--line)}h2{font-size:20px;margin:0 0 10px}h3{font-size:16px;margin:18px 0 8px}h4{margin:6px 0}
.muted{color:var(--muted)}.small{font-size:13px}code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:13px}
pre.doc{white-space:pre-wrap;background:var(--code);padding:10px 12px;border-radius:6px;font-size:13px;margin:6px 0 12px}
.tw{overflow-x:auto;margin:8px 0 14px}table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--card)}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{position:sticky;top:0;background:var(--card);font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}table.vars td:nth-child(6),table.vars td:nth-child(7){text-align:center;color:var(--acc)}tr.grp td{background:var(--code);font-weight:600;padding-top:9px}table.vars td:nth-child(1){font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}.card .k{font-size:12.5px;color:var(--muted)}.card .v{font-size:20px;font-weight:600}
#flt{width:100%;max-width:360px;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);margin:6px 0}
ol.steps{padding-left:22px}ol.steps li{margin:4px 0}details summary{cursor:pointer}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}@media(max-width:760px){.two{grid-template-columns:1fr}}
.bar{display:grid;grid-template-columns:minmax(120px,42%) 1fr 34px;align-items:center;gap:8px;font-size:13px;margin:3px 0}
.bar i{display:block;height:10px;background:var(--acc);border-radius:3px}.bar b{font-weight:500;color:var(--muted);text-align:right}
.figs{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
figure img{width:100%;height:auto;display:block}figcaption{font-size:13px;color:var(--muted);margin-top:6px}
"""
JS = """function filt(q){q=q.toLowerCase();document.querySelectorAll('table.vars tbody tr:not(.grp)').forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q)?'':'none'})}"""


def build() -> Path:
    commit = _git("rev-parse", "--short", "HEAD") or "unknown"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    dirty = " (with uncommitted changes)" if _git("status", "--porcelain", "--", "python") else ""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    ran = (config.OUT / "performance_summary.csv")
    ran_txt = (f"results from the run of {dt.datetime.fromtimestamp(ran.stat().st_mtime):%Y-%m-%d %H:%M}"
               if ran.exists() else "no results yet")
    sections = [("overview", "Overview", f"""
<p>Presence / pseudo-absence models of where utility-scale <b>solar</b> and <b>wind</b> plants are sited in Italy,
on a 1 km EPSG:3035 grid. Five scikit-learn models (GLM, Lasso, GBM, RF, NN) are compared with random and
spatial-block cross-validation; the best ones map relative suitability under a future-infrastructure scenario,
and a GLMM measures how key effects vary across NUTS-2 regions. This Python version re-implements the R
pipeline in <code>syntax/</code> with the changes listed under <a href='#rdiff'>Differences from R</a>.</p>"""),
                ("steps", "Pipeline steps", sec_steps()),
                ("presences", "Presences", sec_presences()),
                ("predictors", "Predictors", sec_predictors()),
                ("models", "Models & validation", sec_models()),
                ("results", "Results", sec_results()),
                ("figures", "Figures", sec_figures()),
                ("sources", "Data sources", sec_sources()),
                ("rdiff", "Differences from R", sec_r_diff()),
                ("changes", "Recent changes", sec_changes())]
    nav = "".join(f"<a href='#{k}'>{t}</a>" for k, t, _ in sections)
    body = "".join(f"<section id='{k}'><div class='wrap'><h2>{t}</h2>{c}</div></section>" for k, t, c in sections)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Italy Siting Pipeline</title>
<style>{CSS}</style></head><body>
<header><div class="wrap"><h1>Italy renewable siting — Python pipeline</h1>
<div class="muted">Branch <code>{E(branch)}</code> · commit <code>{E(commit)}</code>{E(dirty)} · generated {now} · {E(ran_txt)}</div>
</div></header><nav><div class="wrap">{nav}</div></nav>{body}
<footer class="wrap small muted" style="padding:18px 16px">Generated by <code>python -m energysiting.docs</code> from the code and outputs; regenerated at the end of every run.</footer>
<script>{JS}</script></body></html>"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(page, encoding="utf-8")
    return OUT_HTML


def run():
    p = build()
    print(f"Wrote {p}")


if __name__ == "__main__":
    run()
