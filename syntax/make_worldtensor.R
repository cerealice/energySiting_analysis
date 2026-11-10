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

# For rasters already in EPSG:3035 (derived from processed rasters): skip crop+project
snap_proj <- function(r) {
  r |>
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

# Std dev across annual NetCDF files (interannual variability)
std_over_years <- function(domain, var, years) {
  paths   <- file.path(wt_dir, domain, var, paste0(years, ".nc"))
  present <- file.exists(paths)
  if (!any(present)) stop(sprintf("No files found for %s/%s", domain, var))
  layers <- lapply(paths[present], rast)
  app(rast(layers), sd, na.rm = TRUE)
}

# Read a single-year NetCDF
read_year <- function(domain, var, year) {
  p <- file.path(wt_dir, domain, var, paste0(year, ".nc"))
  if (!file.exists(p)) stop(sprintf("File not found: %s", p))
  rast(p)
}

# Safe wrapper: skip variable and warn if source files are missing
# na_fill      : if not NULL, NAs replaced with this value
# already_proj : if TRUE, input is already in EPSG:3035 — use snap_proj not snap_ll
safe_write <- function(out_path, expr_fn, na_fill = NULL, already_proj = FALSE) {
  if (file.exists(out_path)) { message("Exists: ", basename(out_path)); return(invisible()) }
  snap <- if (already_proj) snap_proj else snap_ll
  tryCatch({
    r <- expr_fn() |> snap()
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



# ═══════════════════════════════════════════════════════════════════════════════
# 4. Derived ERA5 features (computed from processed rasters — no re-snap needed)
# ═══════════════════════════════════════════════════════════════════════════════
# These are physically meaningful composites that the raw u/v/radiation layers
# cannot express individually.  already_proj = TRUE skips the WGS84 crop+project
# step because inputs are already in EPSG:3035 at 1 km.

load_var <- function(name) rast(file.path(var_path, name))

message("\n── Derived ERA5 features ────────────────────────────────────────────────")

# Wind speed at 10m: scalar speed from U/V components
safe_write(file.path(var_path, "era5_ws10_mean.tif"), already_proj = TRUE,
  expr_fn = function() sqrt(load_var("era5_u10_mean.tif")^2 +
                             load_var("era5_v10_mean.tif")^2))

# Wind speed at 100m: hub-height resource metric — what turbine power curves use
safe_write(file.path(var_path, "era5_ws100_mean.tif"), already_proj = TRUE,
  expr_fn = function() sqrt(load_var("era5_u100_mean.tif")^2 +
                             load_var("era5_v100_mean.tif")^2))

# Wind power density at 100m (∝ ws100³): directly proportional to available energy
safe_write(file.path(var_path, "era5_wpd100.tif"), already_proj = TRUE,
  expr_fn = function() {
    ws <- sqrt(load_var("era5_u100_mean.tif")^2 + load_var("era5_v100_mean.tif")^2)
    ws^3
  })

# Solar clearness index: ssr / ssrd
# Fraction of downwelling radiation that reaches surface; normalises for latitude
safe_write(file.path(var_path, "era5_clearness.tif"), already_proj = TRUE,
  expr_fn = function() load_var("era5_ssr_sum.tif") / load_var("era5_ssrd_sum.tif"))

# Direct irradiance fraction under clear sky: cdir / ssrdc
# High = more direct beam (better for tracking/CPV); low = diffuse-dominated
safe_write(file.path(var_path, "era5_direct_frac.tif"), already_proj = TRUE,
  expr_fn = function() load_var("era5_cdir_sum.tif") / load_var("era5_ssrdc_sum.tif"))

# Interannual variability of solar radiation (sd of annual ssrd sums 2000–2020)
# High variability = unstable resource = harder to finance
message("\n── Interannual variability (ERA5, 2000–2020) ────────────────────────────")
safe_write(file.path(var_path, "era5_ssrd_iav.tif"),
  expr_fn = function() std_over_years("climate", "ssrd_sum", 2000:2020))

# Interannual variability of wind speed at 100m
# Computed year-by-year as sqrt(u100² + v100²) then sd across years
safe_write(file.path(var_path, "era5_ws100_iav.tif"),
  expr_fn = function() {
    years <- 2000:2020
    pu <- file.path(wt_dir, "climate", "u100_mean", paste0(years, ".nc"))
    pv <- file.path(wt_dir, "climate", "v100_mean", paste0(years, ".nc"))
    ok <- file.exists(pu) & file.exists(pv)
    layers <- mapply(function(u, v) sqrt(rast(u)^2 + rast(v)^2),
                     pu[ok], pv[ok], SIMPLIFY = FALSE)
    app(rast(layers), sd, na.rm = TRUE)
  })

message("\nmake_worldtensor.R complete — re-run stack.R to rebuild covStack.")
