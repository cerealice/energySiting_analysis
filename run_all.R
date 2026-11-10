# ── run_all.R ─────────────────────────────────────────────────────────────────
# Full pipeline runner for the Italy renewable energy siting analysis.
# Open the project via energySiting.Rproj before running so the working
# directory is set to the project root.
#
# Usage:
#   source("run_all.R")               # run main analysis pipeline
#   run_setup()                       # one-time data prep — skips steps whose
#                                     #   outputs already exist on disk
#   force_run_setup()                 # re-run ALL setup steps unconditionally
# ─────────────────────────────────────────────────────────────────────────────

VAR_PATH <- "./data/processed_data/variables"

# ── Helper: source a script with timing and error reporting ───────────────────
run_script <- function(path) {
  script <- basename(path)
  cat(sprintf("\n[%s] ── Running: %s\n", format(Sys.time(), "%H:%M:%S"), script))
  t0 <- proc.time()

  tryCatch(
    withCallingHandlers(
      source(path, echo = FALSE),
      warning = function(w) {
        cat(sprintf("  [%s] WARNING: %s\n", script, conditionMessage(w)))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) {
      cat(sprintf("\n  !! ERROR in %s !!\n", script))
      cat(sprintf("  Message : %s\n", conditionMessage(e)))
      cat("  Traceback:\n")
      calls <- sys.calls()
      for (i in seq_along(calls)) cat(sprintf("    [%d] %s\n", i, deparse(calls[[i]])[1]))
      stop(sprintf("Pipeline stopped: error in '%s'. See message above.", script),
           call. = FALSE)
    }
  )

  elapsed <- round((proc.time() - t0)[["elapsed"]])
  cat(sprintf("  [%s] Done in %ds\n", script, elapsed))
  invisible(NULL)
}


# ── Helper: run script only when any output file is missing ───────────────────
# outputs : character vector of file paths that the script is expected to produce
# force   : if TRUE, always run regardless of what exists on disk
conditional_run <- function(outputs, script, force = FALSE) {
  script_name <- basename(script)
  missing <- !file.exists(outputs)
  if (!force && !any(missing)) {
    cat(sprintf("\n[%s] ── SKIP: %s  (%d/%d outputs exist)\n",
                format(Sys.time(), "%H:%M:%S"), script_name,
                length(outputs), length(outputs)))
    return(invisible(NULL))
  }
  if (!force && any(missing)) {
    cat(sprintf("  Missing outputs (%d): %s%s\n",
                sum(missing),
                paste(basename(outputs[missing][seq_len(min(3, sum(missing)))]),
                      collapse = ", "),
                if (sum(missing) > 3) "…" else ""))
  }
  run_script(script)
}


# ── Helper: call the WorldTensor Python download script ───────────────────────
run_worldtensor_download <- function(force = FALSE) {
  script <- "syntax/download_worldtensor.py"
  wt_dir <- "./data/raw_downloads/worldtensor"

  # Probe a handful of files across domains; if all present, skip
  probe_files <- file.path(wt_dir, c(
    "climate/t2m_mean/2010.nc",
    "climate/ssrd_sum/2010.nc",
    "land_use/states/urban/2020.nc",
    "vegetation/ndvi_mean/2010.nc"
  ))

  if (!force && all(file.exists(probe_files))) {
    cat(sprintf("\n[%s] ── SKIP: %s  (probe files already on disk)\n",
                format(Sys.time(), "%H:%M:%S"), basename(script)))
    return(invisible(NULL))
  }

  cat(sprintf("\n[%s] ── Running: %s\n", format(Sys.time(), "%H:%M:%S"), basename(script)))
  t0 <- proc.time()

  # Try python, fall back to python3
  py <- if (nchar(Sys.which("python"))  > 0) "python"
        else if (nchar(Sys.which("python3")) > 0) "python3"
        else stop("Python not found on PATH — install Python and 'pip install requests'")

  ret <- system2(py, args = c(script, "--workers", "2"), stdout = "", stderr = "")
  if (ret != 0)
    warning(sprintf("%s returned exit code %d — some files may be missing", basename(script), ret))

  elapsed <- round((proc.time() - t0)[["elapsed"]])
  cat(sprintf("  [%s] Done in %ds\n", basename(script), elapsed))
  invisible(NULL)
}


# ── ONE-TIME SETUP ─────────────────────────────────────────────────────────────
# run_setup()       — skips any step whose output files already exist on disk.
# force_run_setup() — re-runs everything unconditionally.

run_setup <- function(force = FALSE) {

  cat(sprintf(
    "\n%s\n  run_setup(%s)\n%s\n",
    strrep("─", 59), if (force) "force = TRUE" else "skipping existing outputs",
    strrep("─", 59)
  ))

  # 1. Base raster
  conditional_run(
    "./data/processed_data/masks/Italy_base_raster.tif",
    "syntax/make_base_raster.R", force
  )

  # 2. Infrastructure / biophysical predictor rasters
  conditional_run(
    file.path(VAR_PATH, c("slope.tif", "pop_density.tif",
                          "transmission_110_qgis.tif", "roads_qgis.tif")),
    "syntax/make_variables_italy.R", force
  )

  # 3. Socioeconomic — ISTAT census
  conditional_run(
    file.path(VAR_PATH, c("svi_pov.tif", "svi_unemp.tif", "svi_foreignborn.tif")),
    "syntax/make_socioeconomic.R", force
  )

  # 4. Socioeconomic — Zenodo (DOI 10.5281/zenodo.11121790)
  conditional_run(
    file.path(VAR_PATH, c("zenodo_gdp_pc.tif", "zenodo_inst_quality.tif")),
    "syntax/make_zenodo_socioeconomic.R", force
  )

  # 5. Environmental impact score (Natura 2000)
  conditional_run(
    file.path(VAR_PATH, c("env_impactScore_solar.tif", "env_impactScore_wind.tif")),
    "syntax/make_natura2000.R", force
  )

  # 6. NUTS-2 binary indicator rasters (21 regions)
  nuts2_ids <- c("itc1","itc2","itc3","itc4",
                 "ith1","ith2","ith3","ith4","ith5",
                 "iti1","iti2","iti3","iti4",
                 "itf1","itf2","itf3","itf4","itf5","itf6",
                 "itg1","itg2")
  conditional_run(
    file.path(VAR_PATH, paste0("nuts2_", nuts2_ids, ".tif")),
    "syntax/make_nuts2_regions.R", force
  )

  # 7. WorldTensor NetCDF download (Python — idempotent, skips existing .nc files)
  run_worldtensor_download(force)

  # 8. WorldTensor → 1-km rasters (ERA5, LUH3, NDVI)
  wt_outputs <- file.path(VAR_PATH, c(
    # ERA5 (sample — make_worldtensor.R skips individual files that already exist)
    "era5_t2m_mean.tif", "era5_tp_sum.tif", "era5_ssrd_sum.tif",
    "era5_u100_mean.tif", "era5_tcc_mean.tif", "era5_blh_mean.tif",
    # LUH3
    "luh3_primf.tif", "luh3_urban.tif", "luh3_c3ann.tif",
    # NDVI
    "wt_ndvi_mean.tif",
    # Derived ERA5 features (section 4 of make_worldtensor.R)
    "era5_ws100_mean.tif", "era5_wpd100.tif",
    "era5_clearness.tif", "era5_direct_frac.tif",
    "era5_ssrd_iav.tif", "era5_ws100_iav.tif"
  ))
  conditional_run(wt_outputs, "syntax/make_worldtensor.R", force)

  # 9. WorldClim BIO1-BIO19 (auto-downloaded by geodata inside the script)
  conditional_run(
    file.path(VAR_PATH, sprintf("wclim_bio%02d.tif", 1:19)),
    "syntax/make_worldclim.R", force
  )

  # 10. Covariate stack (rebuild if layer count ≠ 102)
  stack_path <- "./derived/covStack.tif"
  stack_ok <- !force && tryCatch({
    terra::nlyr(terra::rast(stack_path)) == 102L
  }, error = function(e) FALSE)

  if (stack_ok) {
    cat(sprintf("\n[%s] ── SKIP: stack.R  (covStack.tif has 102 layers)\n",
                format(Sys.time(), "%H:%M:%S")))
  } else {
    run_script("syntax/stack.R")
  }

  cat(sprintf("\n%s\n  run_setup() complete.\n%s\n", strrep("─", 59), strrep("─", 59)))
}

force_run_setup <- function() run_setup(force = TRUE)

#run_setup()  # run one-time setup (skips existing outputs)

# ── MAIN ANALYSIS PIPELINE ────────────────────────────────────────────────────
# Run every time presence data, covariates, or model code changes.

cat("═══════════════════════════════════════════════════════════\n")
cat("  Italy Renewable Energy Siting Analysis — full pipeline\n")
cat(sprintf("  Started: %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S")))
cat("═══════════════════════════════════════════════════════════\n")

t_total <- proc.time()

conditional_run("./derived/location.RData", "syntax/tech.R")   # presence locations (GSPT/GWPT + RSE Atlante)
conditional_run("./derived/absence.RData",  "syntax/absence.R") # pseudo-absence sampling
run_script("syntax/zonal.R")        # covariate extraction
run_script("syntax/modeling.R")     # GLM, Lasso, RF, GBM, NN  [slow ~30–60 min]
run_script("syntax/performance.R")  # model comparison table + plots
run_script("syntax/spatial_cv.R")   # spatial block CV  [slow ~30–60 min]
run_script("syntax/data.R")         # regional summaries, GLMM
run_script("syntax/plot.R")         # figures f1–f4

elapsed_total <- round((proc.time() - t_total)[["elapsed"]])
cat(sprintf("\n═══════════════════════════════════════════════════════════\n"))
cat(sprintf("  Pipeline complete in %dm %ds\n",
            elapsed_total %/% 60, elapsed_total %% 60))
cat(sprintf("  Finished: %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S")))
cat("═══════════════════════════════════════════════════════════\n")
