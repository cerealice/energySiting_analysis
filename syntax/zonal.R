source("./syntax/function.R")
librarian::shelf("fasterize")

base_ras <- terra::rast("./data/processed_data/masks/Italy_base_raster.tif")
load("./derived/absence.RData") # w_ab_sf, wind_absence_roi, s_ab_sf, solar_absence_roi

solar_stack  <- stack("./derived/solar_covStack.tif")
wind_stack   <- stack("./derived/wind_covStack.tif")
coeff_stack  <- stack("./derived/covStack.tif")
coeff_future <- stack("./derived/future.tif")

solar_location_rast <- rast("./derived/solar_hull_existing.tif")
wind_location_rast  <- rast("./derived/wind_hull_existing.tif")


# ── Name layers to match modeling.R formulas ──────────────────────────────────
# Italian stack: 22 shared predictors (land_acquisition and 6 US regions removed;
# fer replaces rps; foreignborn replaces minority; 5 Italian regions added).
names(coeff_stack) <- c(
  "tx", "roads", "sub",                                          # infrastructure
  "slope", "pop", "fer",                                         # biophysical / policy
  "unemploy", "foreignborn", "poverty",                          # socioeconomic
  "lulc_forest", "lulc_grassland", "lulc_shrubland",
  "lulc_riparian", "lulc_sparse", "lulc_agriculture",
  "lulc_developed", "lulc_other",                                # land cover
  "region_nordovest", "region_nordest", "region_centro",
  "region_sud", "region_isole"                                   # Italian NUTS-1 regions
)

names(coeff_future) <- c("tx", "sub")
names(solar_stack)  <- names(wind_stack) <- c("env", "cf", "lag")

# future stack = shared predictors minus current tx/sub, plus planned tx/sub
# col 1 = tx, col 3 = sub  (differs from US where sub was col 4)
future_stack <- stack(list(coeff_stack[[c(-1, -3)]], coeff_future))

wind_IV    <- stack(list(coeff_stack, wind_stack))
solar_IV   <- stack(list(coeff_stack, solar_stack))
wind_future  <- stack(list(future_stack, wind_stack))
solar_future <- stack(list(future_stack, solar_stack))


# ── Solar zonal statistics ────────────────────────────────────────────────────
s_ex <- raster(solar_location_rast)
s_ab <- fasterize::fasterize(sf = s_ab_sf,
                              raster = raster(base_ras),
                              field = "id")

solar.cov.bg       <- as.data.frame(zonal(x = solar_IV, z = s_ab, fun = "mean", na.rm = TRUE)) %>%
  mutate(treat = 0)
solar.cov.existing <- as.data.frame(zonal(x = solar_IV, z = s_ex, fun = "mean", na.rm = TRUE)) %>%
  mutate(treat = 1)

write.csv(solar.cov.bg,       "./derived/bg_cov_solar.csv",       row.names = FALSE)
write.csv(solar.cov.existing, "./derived/existing_cov_solar.csv", row.names = FALSE)


# ── Wind zonal statistics ─────────────────────────────────────────────────────
w_ex <- raster(wind_location_rast)
w_ab <- fasterize::fasterize(sf = w_ab_sf,
                              raster = raster(base_ras),
                              field = "id")

wind.cov.bg       <- as.data.frame(zonal(x = wind_IV, z = w_ab, fun = "mean", na.rm = TRUE)) %>%
  mutate(treat = 0)
wind.cov.existing <- as.data.frame(zonal(x = wind_IV, z = w_ex, fun = "mean", na.rm = TRUE)) %>%
  mutate(treat = 1)

write.csv(wind.cov.bg,       "./derived/bg_cov_wind.csv",       row.names = FALSE)
write.csv(wind.cov.existing, "./derived/existing_cov_wind.csv", row.names = FALSE)
