source("./syntax/function.R")

# ── Make WorldTensor predictor rasters ────────────────────────────────────────
# Reads NetCDF files downloaded by download_worldtensor.py, computes temporal
# means, and snaps everything to the 1-km Italy base raster.
#
# ERA5 climate : mean over 2000–2020 (21 years)
# LUH3 states  : year 2020
# NDVI          : mean over 2003–2020
#
# Output: data/processed_data/variables/era5_*.tif
#                                       luh3_*.tif
#                                       wt_ndvi_mean.tif

base_ras <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path <- "./data/processed_data/variables"
wt_dir   <- "./data/raw_downloads/worldtensor"

# Italy bounding box in WGS84 for fast crop before reprojection
italy_bb <- ext(6.5, 18.5, 36.0, 47.5)

snap_ll <- function(r) {
  r |>
    crop(italy_bb) |>
    project(crs("EPSG:3035")) |>
    resample(base_ras, method = "bilinear") |>
    mask(base_ras)
}

# Average all annual NetCDF files for a given domain/variable
mean_over_years <- function(domain, var, years) {
  paths   <- file.path(wt_dir, domain, var, paste0(years, ".nc"))
  present <- file.exists(paths)
  if (!any(present)) stop(sprintf("No files found for %s/%s", domain, var))
  if (!all(present))
    warning(sprintf("%d/%d files missing for %s/%s — averaging over available",
                    sum(!present), length(paths), domain, var))
  layers <- lapply(paths[present], rast)
  app(rast(layers), mean, na.rm = TRUE)
}

# Read a single-year NetCDF
read_year <- function(domain, var, year) {
  p <- file.path(wt_dir, domain, var, paste0(year, ".nc"))
  if (!file.exists(p)) stop(sprintf("File not found: %s", p))
  rast(p)
}

# Safe wrapper: skip variable and warn if source files are missing
# na_fill: if not NULL, NAs in the processed raster are replaced with this value
#   (use na_fill = 0 for LUH3 land-use fractions — 0 = "not present", not missing)
safe_write <- function(out_path, expr_fn, na_fill = NULL) {
  if (file.exists(out_path)) { message("Exists: ", basename(out_path)); return(invisible()) }
  tryCatch({
    r <- expr_fn() |> snap_ll()
    if (!is.null(na_fill)) r <- ifel(is.na(r), na_fill, r)
    writeRaster(r, out_path, overwrite = TRUE)
    message("Saved:  ", basename(out_path))
  }, error = function(e) {
    message("SKIP:   ", basename(out_path), " — ", conditionMessage(e))
  })
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ERA5 climate — mean 2000–2020
# ═══════════════════════════════════════════════════════════════════════════════

era5_vars <- c(
  # Temperature
  "t2m_mean", "t2m_max", "t2m_min", "t2m_std",
  "d2m_mean",
  # Precipitation & water cycle
  "tp_sum", "cp_sum", "sf_sum", "e_sum", "pev_sum", "ro_sum",
  # Wind (10m + 100m)
  "u10_mean", "v10_mean", "u100_mean", "v100_mean", "i10fg_mean",
  # Radiation
  "ssrd_sum", "ssr_sum", "cdir_sum", "ssrdc_sum",
  # Cloud & atmosphere
  "tcc_mean", "blh_mean", "sp_mean", "cape_mean"
)

message("\n── ERA5 (", length(era5_vars), " variables, 2000–2020) ─────────────────────")
for (var in era5_vars) {
  out <- file.path(var_path, paste0("era5_", var, ".tif"))
  safe_write(out, function(v = var) mean_over_years("climate", v, 2000:2020))
}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LUH3 land-use states — year 2020
# ═══════════════════════════════════════════════════════════════════════════════

luh3_vars <- c(
  "primf", "primn",          # primary forest / non-forest
  "secdf", "secdn",          # secondary forest / non-forest
  "pastr", "range", "urban", # managed land
  "c3ann", "c4ann",          # annual crops
  "c3per", "c4per",          # perennial crops
  "c3nfx"                    # nitrogen-fixing crops
)

message("\n── LUH3 states (", length(luh3_vars), " variables, year 2020) ───────────────")
for (var in luh3_vars) {
  out <- file.path(var_path, paste0("luh3_", var, ".tif"))
  # na_fill = 0: LUH3 fraction NA in Italy means the land type is absent → 0
  safe_write(out, function(v = var) read_year("land_use/states", v, 2020), na_fill = 0)
}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MODIS NDVI — mean 2003–2020
# ═══════════════════════════════════════════════════════════════════════════════

message("\n── NDVI (mean 2003–2020) ────────────────────────────────────────────────")
safe_write(
  file.path(var_path, "wt_ndvi_mean.tif"),
  function() mean_over_years("vegetation", "ndvi_mean", 2003:2020)
)

message("\nmake_worldtensor.R complete — re-run stack.R to rebuild covStack.")
