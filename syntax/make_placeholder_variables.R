message("=============================================================")
message("  PLACEHOLDER VARIABLES — for pipeline testing only")
message("  Replace each file with real Italian data before analysis.")
message("=============================================================")

library(terra)

base_ras  <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path  <- "./data/processed_data/variables"
dir.create(var_path, showWarnings = FALSE, recursive = TRUE)

# Helper: continuous placeholder — random normal values, masked to Italy
make_continuous <- function(name) {
  r <- base_ras
  values(r) <- ifelse(!is.na(values(base_ras)), rnorm(ncell(base_ras)), NA)
  writeRaster(r, file.path(var_path, name), overwrite = TRUE)
  message("  [placeholder] ", name)
}

# Helper: binary placeholder — random 0/1, masked to Italy
make_binary <- function(name) {
  r <- base_ras
  values(r) <- ifelse(!is.na(values(base_ras)), rbinom(ncell(base_ras), 1, 0.5), NA)
  writeRaster(r, file.path(var_path, name), overwrite = TRUE)
  message("  [placeholder] ", name)
}

# Helper: region placeholder — 1 inside a rough bbox slice, NA elsewhere
# (approximates the spatial structure of region dummies)
make_region <- function(name, xmin_frac, xmax_frac, ymin_frac, ymax_frac) {
  ext_it <- ext(base_ras)
  xrange <- ext_it$xmax - ext_it$xmin
  yrange <- ext_it$ymax - ext_it$ymin
  region_ext <- ext(
    ext_it$xmin + xmin_frac * xrange,
    ext_it$xmin + xmax_frac * xrange,
    ext_it$ymin + ymin_frac * yrange,
    ext_it$ymin + ymax_frac * yrange
  )
  r      <- base_ras * 0          # all zeros, Italy mask preserved
  r_crop <- crop(base_ras, region_ext)
  r      <- merge(r_crop, r)      # 1 in region slice, 0 elsewhere
  r      <- mask(r, base_ras)
  writeRaster(r, file.path(var_path, name), overwrite = TRUE)
  message("  [placeholder] ", name)
}

set.seed(42)

message("\nInfrastructure:")
make_continuous("transmission_110_qgis.tif")
make_continuous("roads_qgis.tif")
make_continuous("substations_110_qgis.tif")
make_continuous("transmission_110_wPlanned.tif")
make_continuous("substations_110_wPlanned.tif")

message("\nBiophysical / resource:")
make_continuous("slope.tif")
make_continuous("solar_capacity.tif")
make_continuous("wind_capacity.tif")
make_continuous("env_impactScore_solar.tif")
make_continuous("env_impactScore_wind.tif")
make_continuous("solar_lag.tif")
make_continuous("wind_lag.tif")

message("\nDemographics / socioeconomic:")
make_continuous("pop_density.tif")
make_continuous("svi_unemp.tif")
make_continuous("svi_foreignborn.tif")
make_continuous("svi_pov.tif")

message("\nPolicy:")
make_binary("fer_incentive.tif")

message("\nLand use / land cover:")
make_binary("lulc_forest.tif")
make_binary("lulc_grassland.tif")
make_binary("lulc_shrubland.tif")
make_binary("lulc_riparian.tif")
make_binary("lulc_sparselyvegetated.tif")
make_binary("lulc_agricultural.tif")
make_binary("lulc_developed.tif")
make_binary("lulc_other.tif")

message("\nItalian NUTS-1 macro-regions (approximate bounding slices):")
# Italy in LAEA roughly spans N–S: nord (top 40%), centro (mid 30%), sud+isole (bottom 30%)
make_region("region_nordovest.tif", 0.0, 0.5, 0.6, 1.0)
make_region("region_nordest.tif",   0.5, 1.0, 0.6, 1.0)
make_region("region_centro.tif",    0.1, 0.9, 0.35, 0.6)
make_region("region_sud.tif",       0.1, 0.9, 0.1, 0.35)
make_region("region_isole.tif",     0.0, 0.6, 0.0, 0.2)

message("\nDone. Run stack.R next.")
message("Replace placeholder files with real Italian data before final analysis.")
