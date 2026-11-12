# Python / scikit-learn port of the Italy siting pipeline

This folder (branch `python-sklearn`) re-implements every step of the R pipeline
in `syntax/` with Python, using **scikit-learn** for all machine-learning models.
The R code is left untouched next to it so the two can be compared.

| R script | Python module | Notes |
|---|---|---|
| `function.R` | `energysiting/config.py` | paths, CRS, `region_model` → `MODEL_VARS` (96 predictors), labels, NUTS lookups |
| `make_base_raster.R` | `setup/make_base_raster.py` | GISCO country boundary → 1 km EPSG:3035 grid |
| `make_variables_italy.R` | `setup/make_variables_italy.py` | slope, population, OSM roads/grid distances, capacity proxies, land cover, spatial lag |
| `make_socioeconomic.R` | `setup/make_socioeconomic.py` | MEF income, ISTAT unemployment, foreign-born share |
| `make_zenodo_socioeconomic.R` | `setup/make_zenodo_socioeconomic.py` | GDP pc, institutional quality |
| `make_natura2000.R` | `setup/make_natura2000.py` | 0.7 × Natura-2000 proximity + 0.3 × slope |
| `make_nuts2_regions.R` | `setup/make_nuts2_regions.py` | 21 NUTS-2 indicator rasters |
| `make_worldtensor.R` | `setup/make_worldtensor.py` | ERA5 / LUH3 / NDVI from WorldTensor NetCDFs |
| `make_worldclim.R` | `setup/make_worldclim.py` | WorldClim BIO1–19 |
| `stack.R` | `setup/stack.py` | 102-layer z-scored stack + tech + future stacks |
| `tech.R` | `tech.py` | GEM trackers + RSE Atlante → presence rasters |
| `absence.R` | `absence.py` | pseudo-absences by NUTS-2, 10 seeds |
| `zonal.R` | `zonal.py` | zone means of the 105 layers |
| `modeling.R` | `modeling.py` + `learners.py` + `glm.py` | 10-group GLMs, 5 learners × 10-fold CV, maps |
| `performance.R` | `performance.py` | ROC/Sens/Spec table, Wilcoxon, PR/ROC curves |
| `spatial_cv.R` | `spatial_cv.py` | variogram range, spatial blocks, GBM/RF re-fit |
| `data.R` | `data.py` + `glmm.py` | masked maps, NUTS-1 means, random-slope GLMM |
| `plot.R` | `plot.py` | figures f1–f4 |
| `run_all.R`, `run_hpc.sh` | `run_all.py`, `run_all.sh` | runner (same skip-if-exists logic); cluster script |
| – | `setup/fetch.py` | downloads every raw input up front (for offline compute nodes) |

## Model mapping (caret → scikit-learn)

| caret | R tuning | scikit-learn |
|---|---|---|
| `glm` | – | `LogisticRegression(C=inf)` (+ `glm.BinomialGLM`, an R-style IRLS for SEs, p-values, AIC) |
| `glmnet` (α = 1) | λ ∈ 10^seq(−3, 3, 100) | `LogisticRegression(l1_ratio=1, C=1/(n·λ))` on standardised inputs |
| `gbm` | trees {50,100} × depth {3,6} × shrinkage {.01,.1} × minobs {5,10} | `GradientBoostingClassifier(max_leaf_nodes=depth+1, subsample=0.5, …)` |
| `rf` | mtry = caret default | `RandomForestClassifier(500 trees, max_features ∈ {2, 49, 96})` |
| `nnet` | size {5,10,20} × decay {.001,.01,.1} | `MLPClassifier(1 logistic hidden layer, lbfgs, alpha = 2·decay)` |
| `lme4::glmer` | (slope \| NUTS-2) | `glmm.LogitGLMM` (numpy; no mixed models in scikit-learn) |
| `blockCV` | autocorrelation range, random blocks | `spatial_cv.autocor_range` + `spatial_blocks` |

Resampling follows `trainControl(method = "cv", number = 10, classProbs = TRUE,
summaryFunction = twoClassSummary)`: best tune by mean ROC, Sens/Spec with X0
(absence) as the event class as in caret. All learners share the same
stratified folds, so the model comparison is paired.

## Running

### On a cluster (LSF or SLURM) — full rebuild from raw data

```bash
git checkout python-sklearn
bash python/run_all.sh check      # what is still missing (Natura 2000 is manual)
bash python/run_all.sh            # login node: create env + download inputs + submit job
```

`run_all.sh` creates a venv (or a conda env with `CONDA_ENV=energysiting`),
downloads everything the setup needs (~17 GB; resumable) with
`python -m energysiting.setup.fetch`, then submits itself with `bsub` or
`sbatch`. The job runs `python python/run_all.py --force-setup`, i.e. it
rebuilds the base raster, every covariate layer, the 102-layer stack, the
presence/absence data, all models and figures — fully offline. Edit the
`#BSUB` / `#SBATCH` lines (queue, project, walltime) and, if needed, set
`PY_MODULE` (e.g. `python/3.11`). Sub-commands: `prepare`, `submit`, `check`, `local`.

The only manual input is EEA Natura 2000 end-2024 (EPSG:3035), unzipped to
`data/raw_downloads/eea_v_3035_100_k_natura2000_p_2024_v01_r00/SHP/Natura2000_end2024_epsg3035.shp`.

### Directly

```bash
pip install -r python/requirements.txt
python python/run_all.py --setup      # build missing inputs, then the analysis
python python/run_all.py              # analysis only, re-using derived/*covStack.tif
python python/run_all.py --from modeling
```

Shared inputs (`derived/covStack.tif`, `*_covStack.tif`, `future.tif`,
`*_hull_existing*`, `data/processed_data/`) use the same file names as the R
pipeline; everything the Python analysis produces goes to `derived/py/` and
`fig/python/`.

The analysis steps need only numpy/pandas/scipy/scikit-learn/matplotlib/tifffile:
if `rasterio` is missing, GeoTIFFs (including terra's LZW-compressed ones) are
read by a pure-Python fallback in `energysiting/raster.py`. The setup steps and
`tech.py` require the geospatial stack (rasterio, geopandas, pyogrio with GDAL's
OSM driver, xarray + netCDF4).

## Deliberate differences from the R code

* **Prediction maps are no longer empty.** `luh3_c4per` is NA in every cell of
  `covStack.tif`, so `raster::predict(..., na.rm = TRUE)` dropped every cell and
  all `pred_*.tif` / `results_masked.tif` written by R are entirely NA (f3 shows
  grey maps and empty bars). The Python port imputes prediction cells exactly
  like the training data (`impute_dat`: LUH3 → 0, others → training median).
* `tech` runs before `make_variables_italy` in the setup: the spatial-lag
  layers are computed from the presence rasters, which R's `run_setup()` builds
  only later (it works in R only when `derived/` already exists).
* **Wind model: +4 derived ERA5 wind features** (`era5_ws10_mean`, `era5_ws100_mean`,
  `era5_wpd100`, `era5_ws100_iav`), which R builds into the stack but leaves out of
  `region_model` → 100 predictors for wind, 96 for solar. Set
  `ES_WIND_ERA5_DERIVED=0` to get R's formula back. Paired test on the same data
  and folds (Nov 2026): 10-fold AUC GBM 0.850 → 0.850, RF 0.837 → 0.834; spatial-block
  GBM 0.811 → 0.807 — no measurable gain, because WorldTensor only has annual-mean
  U/V, so these are speeds of the mean wind *vector* and largely duplicate
  `era5_u100_mean`. `ES_DROP_VARS=lag,...` drops predictors for sensitivity runs.
* Random number streams differ from R, so pseudo-absences, folds and stochastic
  learners are not bit-identical; presence covariates match R to 1e-14.
* RF importance: permutation importance (presence-class recall) instead of
  randomForest's OOB class-specific mean decrease in accuracy; GBM importance
  is scikit-learn's impurity-based importance (≈ gbm relative influence).
* `pairwise.wilcox.test` is reproduced as unpaired Mann–Whitney tests with Holm
  adjustment (the R default).
* Spatial-CV comparison uses the fold ROC of the best tune only. In R,
  `returnResamp = "all"` keeps every GBM tuning row, so the R spatial GBM box
  pools 16 × 5 = 80 values.

## Reproduction check (run on the existing `derived/` stacks, Nov 2026)

| | R (fig/original) | Python (fig/python) |
|---|---|---|
| Presence-zone covariates | – | identical to R (max abs diff 5e-14) |
| Pseudo-absences | 12 610 solar / 3 660 wind | 12 610 / 3 660 |
| Solar AUC, 10-fold (GBM / RF / Lasso / GLM / NN) | ≈ .78 / .755 / .735 / .74 / .71 (medians) | .763 / .740 / .739 / .733 / .723 (means) |
| Wind AUC, 10-fold (GBM / RF / Lasso / GLM / NN) | ≈ .85 / .83 / .755 / .74 / .745 | .850 / .837 / .762 / .758 / .756 |
| Spatial-block AUC solar GBM / RF | ≈ .765 / .76 | .750 / .741 |
| Spatial-block AUC wind GBM / RF | ≈ .81 / .78 | .811 / .777 |
| Block size solar / wind | 50 / 60 km | 50 / 80 km |

Model ranking (GBM > RF > linear models > NN) and the spatial-CV optimism gap
for wind are reproduced.
