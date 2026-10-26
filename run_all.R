# ── run_all.R ─────────────────────────────────────────────────────────────────
# Full pipeline runner for the Italy renewable energy siting analysis.
# Open the project via energySiting.Rproj before running so the working
# directory is set to the project root.
#
# Usage:
#   source("run_all.R")              # run main analysis pipeline
#   source("run_all.R"); run_setup() # also re-run one-time data prep steps
# ─────────────────────────────────────────────────────────────────────────────

# ── Helper: source a script with informative error reporting ──────────────────
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
      cat(sprintf("  Traceback:\n"))
      calls <- sys.calls()
      for (i in seq_along(calls)) {
        cat(sprintf("    [%d] %s\n", i, deparse(calls[[i]])[1]))
      }
      stop(sprintf("Pipeline stopped: error in '%s'. See message above.", script),
           call. = FALSE)
    }
  )

  elapsed <- round((proc.time() - t0)[["elapsed"]])
  cat(sprintf("  [%s] Done in %ds\n", script, elapsed))
  invisible(NULL)
}


# ── ONE-TIME SETUP ─────────────────────────────────────────────────────────────
# These scripts only need to be re-run when the underlying source data changes.
# Uncomment and call run_setup() to rebuild from scratch.

run_setup <- function() {
  run_script("syntax/make_base_raster.R")    # Italy_base_raster.tif
  run_script("syntax/make_variables_italy.R") # predictor rasters
  run_script("syntax/make_socioeconomic.R")   # svi_pov, svi_unemp, svi_foreignborn
  run_script("syntax/make_natura2000.R")      # env_impactScore_solar/wind
  run_script("syntax/stack.R")               # covStack.tif, solar/wind covStacks
}


# ── MAIN ANALYSIS PIPELINE ────────────────────────────────────────────────────
# Run every time the presence data, covariates, or model code changes.

cat("═══════════════════════════════════════════════════════════\n")
cat("  Italy Renewable Energy Siting Analysis — full pipeline\n")
cat(sprintf("  Started: %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S")))
cat("═══════════════════════════════════════════════════════════\n")

t_total <- proc.time()

run_script("syntax/tech.R")      # presence locations (GSPT/GWPT + RSE Atlante)
run_script("syntax/absence.R")   # pseudo-absence sampling
run_script("syntax/zonal.R")     # covariate extraction
run_script("syntax/modeling.R")  # GLM, Lasso, RF, GBM models  [slow ~30–60 min]
run_script("syntax/data.R")      # regional summaries, GLMM
run_script("syntax/plot.R")      # figures f1–f4

elapsed_total <- round((proc.time() - t_total)[["elapsed"]])
cat(sprintf("\n═══════════════════════════════════════════════════════════\n"))
cat(sprintf("  Pipeline complete in %dm %ds\n",
            elapsed_total %/% 60, elapsed_total %% 60))
cat(sprintf("  Finished: %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S")))
cat("═══════════════════════════════════════════════════════════\n")
