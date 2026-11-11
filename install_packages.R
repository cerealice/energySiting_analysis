# ── install_packages.R ────────────────────────────────────────────────────────
# Run this ONCE from a login node (or any node with internet access) before
# submitting the main pipeline job.
#
# Usage:
#   R --no-save --no-restore -f install_packages.R
#
# Sets R_LIBS_USER so packages land in a user-writable directory.
# ─────────────────────────────────────────────────────────────────────────────

repo <- "https://cloud.r-project.org"

# User library — same path set in run_hpc.sh
lib <- Sys.getenv("R_LIBS_USER")
if (nchar(lib) == 0L) {
  lib <- file.path(Sys.getenv("HOME"), "R",
                   paste(R.version$platform, R.version$major,
                         sub("\\..*", "", R.version$minor), sep = "/"),
                   "library")
}
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
message("Installing to: ", lib)
.libPaths(c(lib, .libPaths()))

install_if_missing <- function(pkgs) {
  missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]
  if (length(missing) == 0L) {
    message("All packages already installed.")
    return(invisible(NULL))
  }
  message("Installing: ", paste(missing, collapse = ", "))
  install.packages(missing, lib = lib, repos = repo)
}

# ── Core pipeline packages ────────────────────────────────────────────────────
install_if_missing(c(
  "librarian",
  # Spatial
  "raster", "sf", "terra", "tidyterra", "giscoR", "fasterize",
  # Data wrangling
  "tidyverse", "dplyr", "readxl", "foreign", "here",
  # Modelling
  "caret", "glmnet", "randomForest", "xgboost",
  "lme4", "lmerTest", "recipes",
  # Parallel
  "foreach", "doParallel",
  # Figures
  "ggpubr", "ggstance", "ggnewscale", "cowplot", "patchwork",
  "gridExtra", "rasterVis", "RColorBrewer", "viridis", "mapview",
  # Utilities
  "tictoc", "stargazer",
  # Setup scripts only
  "geodata", "osmextract"
))

message("\nDone. You can now submit run_hpc.sh.")
