source("./syntax/function.R")

processed_layer_path <- "./data/processed_data/variables"

# ── Shared predictor layers ───────────────────────────────────────────────────
# Italian equivalents of the US predictor rasters. All files must be placed in
# data/processed_data/variables/ aligned to Italy_base_raster.tif (EPSG:3035,
# 1 km resolution) before running this script.
#
# Sources:
#   Infrastructure  → TERNA (transmission, substations)
#                     OpenStreetMap (roads)
#   Biophysical     → EU-DEM / SRTM (slope)
#   Demographics    → ISTAT / GHSL (population density)
#   Socioeconomic   → ISTAT census (unemployment, poverty, foreign-born %)
#   Land use        → Copernicus CORINE Land Cover
#   Policy          → GSE / MASE (FER incentive eligibility by region)
#   Regions         → Italian NUTS-1 macro-regions (5 units):
#                       Nord-Ovest, Nord-Est, Centro, Sud, Isole

cov.filePaths <- c(
  # Infrastructure
  file.path(processed_layer_path, "transmission_110_qgis.tif"),   # dist. to 110+ kV lines (TERNA)
  file.path(processed_layer_path, "roads_qgis.tif"),              # dist. to roads (OSM)
  file.path(processed_layer_path, "substations_110_qgis.tif"),    # dist. to substations (TERNA)
  # Biophysical
  file.path(processed_layer_path, "slope.tif"),                   # terrain slope (EU-DEM)
  # Demographics
  file.path(processed_layer_path, "pop_density.tif"),             # population density (ISTAT/GHSL)
  # Policy
  file.path(processed_layer_path, "fer_incentive.tif"),           # FER incentive zone binary (GSE/MASE)
  # Socioeconomic (ISTAT census indicators)
  file.path(processed_layer_path, "svi_unemp.tif"),               # unemployment rate
  file.path(processed_layer_path, "svi_foreignborn.tif"),         # foreign-born % (replaces minority)
  file.path(processed_layer_path, "svi_pov.tif"),                 # poverty rate
  # Land use / land cover (Copernicus CORINE)
  file.path(processed_layer_path, "lulc_forest.tif"),
  file.path(processed_layer_path, "lulc_grassland.tif"),
  file.path(processed_layer_path, "lulc_shrubland.tif"),
  file.path(processed_layer_path, "lulc_riparian.tif"),
  file.path(processed_layer_path, "lulc_sparselyvegetated.tif"),
  file.path(processed_layer_path, "lulc_agricultural.tif"),
  file.path(processed_layer_path, "lulc_developed.tif"),
  file.path(processed_layer_path, "lulc_other.tif"),
  # Italian NUTS-1 macro-regions (binary rasters, 1 = in region)
  file.path(processed_layer_path, "region_nordovest.tif"),        # Piemonte, VdA, Liguria, Lombardia
  file.path(processed_layer_path, "region_nordest.tif"),          # Trentino-AA, Veneto, FVG, Emilia-R
  file.path(processed_layer_path, "region_centro.tif"),           # Toscana, Umbria, Marche, Lazio
  file.path(processed_layer_path, "region_sud.tif"),              # Abruzzo, Molise, Campania, Puglia, Basilicata, Calabria
  file.path(processed_layer_path, "region_isole.tif")             # Sicilia, Sardegna
)

cov.names <- c(
  "Transmission dist",
  "Road dist",
  "Substation dist",
  "Slope",
  "Population density",
  "FER incentive",
  "Unemployment",
  "Foreign born",
  "Poverty",
  "Forest",
  "Grassland",
  "Shrubland",
  "Riparian",
  "Vegetated",
  "Agriculture",
  "Developed",
  "Other lands",
  "region_nordovest",
  "region_nordest",
  "region_centro",
  "region_sud",
  "region_isole"
)

# Layers 1:9 are continuous → z-score scaled; 10:end are binary → no scaling
raster_list <- list()
for (i in 1:length(cov.names)) {
  if (i < 10) {
    raster_list[[cov.names[[i]]]] <- raster(cov.filePaths[[i]]) %>%
      raster::scale()
  } else {
    raster_list[[cov.names[[i]]]] <- raster(cov.filePaths[[i]])
  }
}

coeff_stack <- stack(raster_list)
raster::writeRaster(coeff_stack, "./derived/covStack.tif", overwrite = TRUE)


# ── Solar-specific layers ─────────────────────────────────────────────────────
# solar_capacity.tif  → PVGIS capacity factor grid (JRC)
# env_impactScore_solar.tif → composite environmental sensitivity for solar
# solar_lag.tif       → spatial lag of existing solar development

cov.tech  <- c(file.path(processed_layer_path, "env_impactScore_solar.tif"),
               file.path(processed_layer_path, "solar_capacity.tif"),
               file.path(processed_layer_path, "solar_lag.tif"))
cov.names <- c("Environmental score", "Capacity factor", "Spatial lag")

raster_list <- list()
for (i in 1:length(cov.names)) {
  raster_list[[cov.names[[i]]]] <- raster(cov.tech[[i]]) %>% raster::scale()
}

solar_stack <- stack(raster_list)
raster::writeRaster(solar_stack, "./derived/solar_covStack.tif", overwrite = TRUE)


# ── Wind-specific layers ──────────────────────────────────────────────────────
# wind_capacity.tif   → PVGIS / Copernicus CDS wind capacity factor grid
# env_impactScore_wind.tif → composite environmental sensitivity for wind
# wind_lag.tif        → spatial lag of existing wind development

cov.tech  <- c(file.path(processed_layer_path, "env_impactScore_wind.tif"),
               file.path(processed_layer_path, "wind_capacity.tif"),
               file.path(processed_layer_path, "wind_lag.tif"))
cov.names <- c("Environmental score", "Capacity factor", "Spatial lag")

raster_list <- list()
for (i in 1:length(cov.names)) {
  raster_list[[cov.names[[i]]]] <- raster(cov.tech[[i]]) %>% raster::scale()
}

wind_stack <- stack(raster_list)
raster::writeRaster(wind_stack, "./derived/wind_covStack.tif", overwrite = TRUE)


# ── Future infrastructure layers ──────────────────────────────────────────────
# Planned transmission and substations from TERNA's development plan

cov.tech  <- c(file.path(processed_layer_path, "transmission_110_wPlanned.tif"),
               file.path(processed_layer_path, "substations_110_wPlanned.tif"))
cov.names <- c("Transmission dist", "Substation dist")

raster_list <- list()
for (i in 1:length(cov.names)) {
  raster_list[[cov.names[[i]]]] <- raster(cov.tech[[i]]) %>% raster::scale()
}

future_stack <- stack(raster_list)
raster::writeRaster(future_stack, "./derived/future.tif", overwrite = TRUE)
