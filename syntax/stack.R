source("./syntax/function.R")

processed_layer_path <- "./data/processed_data/variables"

# ── Release any open file handles to the output files ────────────────────────
# On Windows, SpatRaster / RasterStack objects keep an exclusive handle on
# their backing .tif.  Scan the global environment and drop anything that
# points at our output paths before we try to write to them.
.out <- normalizePath(
  c("./derived/covStack.tif", "./derived/solar_covStack.tif",
    "./derived/wind_covStack.tif", "./derived/future.tif"),
  mustWork = FALSE
)
for (.nm in ls(envir = .GlobalEnv)) {
  .obj <- get(.nm, envir = .GlobalEnv)
  if (inherits(.obj, c("SpatRaster", "RasterStack", "RasterBrick", "RasterLayer"))) {
    .src <- tryCatch(
      normalizePath(terra::sources(terra::rast(.obj)), mustWork = FALSE),
      error = function(e) character(0)
    )
    if (any(.src %in% .out)) {
      rm(list = .nm, envir = .GlobalEnv)
      message("Released handle: ", .nm)
    }
  }
}
rm(.nm, .obj, .src, .out)
gc()

# ── Helper: z-score scale a SpatRaster layer ─────────────────────────────────
terra_scale <- function(r) {
  m <- terra::global(r, "mean", na.rm = TRUE)[[1]]
  s <- terra::global(r, "sd",   na.rm = TRUE)[[1]]
  (r - m) / s
}

# ── Helper: load layers, scale the continuous ones, stack and write ───────────
# scale_up_to: layers 1..scale_up_to are z-scored; the rest are left as-is
build_stack <- function(paths, layer_names, scale_up_to, out_path) {
  layers <- vector("list", length(paths))
  for (i in seq_along(paths)) {
    r <- terra::rast(paths[[i]])
    names(r) <- layer_names[[i]]
    layers[[i]] <- if (i <= scale_up_to) terra_scale(r) else r
  }
  stk <- terra::rast(layers)
  terra::writeRaster(stk, out_path, overwrite = TRUE)
  message("Saved: ", out_path)
  invisible(stk)
}

# ── Shared predictor stack ────────────────────────────────────────────────────
# Sources:
#   Infrastructure  → TERNA (transmission, substations), OSM (roads)
#   Biophysical     → EU-DEM / SRTM (slope)
#   Demographics    → ISTAT / GHSL (population density)
#   Socioeconomic   → ISTAT census (unemployment, poverty, foreign-born %)
#   Land use        → Copernicus CORINE Land Cover (binary)
#   Policy          → GSE / MASE (FER incentive eligibility, binary)
#   Regions         → Italian NUTS-1 macro-regions (binary)

cov_paths <- c(
  # Infrastructure
  file.path(processed_layer_path, "transmission_110_qgis.tif"),
  file.path(processed_layer_path, "roads_qgis.tif"),
  file.path(processed_layer_path, "substations_110_qgis.tif"),
  # Biophysical
  file.path(processed_layer_path, "slope.tif"),
  # Demographics
  file.path(processed_layer_path, "pop_density.tif"),
  # Socioeconomic — ISTAT census
  file.path(processed_layer_path, "svi_unemp.tif"),
  file.path(processed_layer_path, "svi_foreignborn.tif"),
  file.path(processed_layer_path, "svi_pov.tif"),
  # Socioeconomic — Zenodo / Nature Scientific Data 2025 (DOI 10.5281/zenodo.11121790)
  file.path(processed_layer_path, "zenodo_gdp_pc.tif"),
  file.path(processed_layer_path, "zenodo_inst_quality.tif"),
  # Policy — fer_incentive is constant 1 across all of Italy (GSE FER scheme is
  # national, no regional variation). A constant predictor carries zero information
  # and is collinear with the intercept. Uncomment to restore if zone-specific
  # incentive data become available.
  # file.path(processed_layer_path, "fer_incentive.tif"),
  # Land use / land cover (binary — no scaling)
  file.path(processed_layer_path, "lulc_forest.tif"),
  file.path(processed_layer_path, "lulc_grassland.tif"),
  file.path(processed_layer_path, "lulc_shrubland.tif"),
  file.path(processed_layer_path, "lulc_riparian.tif"),
  file.path(processed_layer_path, "lulc_sparselyvegetated.tif"),
  file.path(processed_layer_path, "lulc_agricultural.tif"),
  file.path(processed_layer_path, "lulc_developed.tif"),
  file.path(processed_layer_path, "lulc_other.tif"),
  # NUTS-1 macro-regions (binary — no scaling)
  file.path(processed_layer_path, "region_nordovest.tif"),
  file.path(processed_layer_path, "region_nordest.tif"),
  file.path(processed_layer_path, "region_centro.tif"),
  file.path(processed_layer_path, "region_sud.tif"),
  file.path(processed_layer_path, "region_isole.tif")
)

cov_names <- c(
  "Transmission dist", "Road dist", "Substation dist",
  "Slope", "Population density",
  "Unemployment", "Foreign born", "Poverty",
  "GDP per capita", "Institutional quality",
  # "FER incentive",   # commented out — constant across Italy, see cov_paths above
  "Forest", "Grassland", "Shrubland", "Riparian",
  "Vegetated", "Agriculture", "Developed", "Other lands",
  "region_nordovest", "region_nordest", "region_centro",
  "region_sud", "region_isole"
)

# Layers 1–10 are continuous → z-scored; 11+ are binary → unscaled
build_stack(cov_paths, cov_names, scale_up_to = 10, out_path = "./derived/covStack.tif")


# ── Solar-specific stack ──────────────────────────────────────────────────────
build_stack(
  paths       = c(file.path(processed_layer_path, "env_impactScore_solar.tif"),
                  file.path(processed_layer_path, "solar_capacity.tif"),
                  file.path(processed_layer_path, "solar_lag.tif")),
  layer_names = c("Environmental score", "Capacity factor", "Spatial lag"),
  scale_up_to = 3,
  out_path    = "./derived/solar_covStack.tif"
)


# ── Wind-specific stack ───────────────────────────────────────────────────────
build_stack(
  paths       = c(file.path(processed_layer_path, "env_impactScore_wind.tif"),
                  file.path(processed_layer_path, "wind_capacity.tif"),
                  file.path(processed_layer_path, "wind_lag.tif")),
  layer_names = c("Environmental score", "Capacity factor", "Spatial lag"),
  scale_up_to = 3,
  out_path    = "./derived/wind_covStack.tif"
)


# ── Future infrastructure stack ───────────────────────────────────────────────
build_stack(
  paths       = c(file.path(processed_layer_path, "transmission_110_wPlanned.tif"),
                  file.path(processed_layer_path, "substations_110_wPlanned.tif")),
  layer_names = c("Transmission dist", "Substation dist"),
  scale_up_to = 2,
  out_path    = "./derived/future.tif"
)
