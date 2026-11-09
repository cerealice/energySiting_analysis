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
# Italian stack: 24 shared predictors (land_acquisition and 6 US regions removed;
# fer replaces rps; foreignborn replaces minority; 5 Italian regions added;
# gdp_pc and inst_quality added from Zenodo DOI 10.5281/zenodo.11121790).
names(coeff_stack) <- c(
  # ── Continuous (1–66) ───────────────────────────────────────────────────────
  "tx", "roads", "sub",                   # infrastructure
  "slope", "pop",                          # biophysical / demographics
  "unemploy", "foreignborn", "poverty",   # socioeconomic (ISTAT)
  "gdp_pc", "inst_quality",               # socioeconomic (Zenodo)
  # WorldClim 2.1 BIO1-BIO19
  "wclim_bio01", "wclim_bio02", "wclim_bio03", "wclim_bio04", "wclim_bio05",
  "wclim_bio06", "wclim_bio07", "wclim_bio08", "wclim_bio09", "wclim_bio10",
  "wclim_bio11", "wclim_bio12", "wclim_bio13", "wclim_bio14", "wclim_bio15",
  "wclim_bio16", "wclim_bio17", "wclim_bio18", "wclim_bio19",
  # ERA5 annual means 2000-2020
  "era5_t2m_mean", "era5_t2m_max", "era5_t2m_min", "era5_t2m_std",
  "era5_d2m_mean",
  "era5_tp_sum", "era5_cp_sum", "era5_sf_sum",
  "era5_e_sum", "era5_pev_sum", "era5_ro_sum",
  "era5_u10_mean", "era5_v10_mean", "era5_u100_mean", "era5_v100_mean", "era5_i10fg_mean",
  "era5_ssrd_sum", "era5_ssr_sum", "era5_cdir_sum", "era5_ssrdc_sum",
  "era5_tcc_mean", "era5_blh_mean", "era5_sp_mean", "era5_cape_mean",
  # LUH3 land-use states 2020
  "luh3_primf", "luh3_primn", "luh3_secdf", "luh3_secdn",
  "luh3_pastr", "luh3_range", "luh3_urban",
  "luh3_c3ann", "luh3_c4ann", "luh3_c3per", "luh3_c4per", "luh3_c3nfx",
  # MODIS NDVI mean 2003-2020
  "wt_ndvi_mean",
  # ── Binary (67–95) ──────────────────────────────────────────────────────────
  "lulc_forest", "lulc_grassland", "lulc_shrubland",
  "lulc_riparian", "lulc_sparse", "lulc_agriculture",
  "lulc_developed", "lulc_other",                                # CORINE land cover
  "nuts2_itc1", "nuts2_itc2", "nuts2_itc3", "nuts2_itc4",        # Nord-Ovest
  "nuts2_ith1", "nuts2_ith2", "nuts2_ith3", "nuts2_ith4", "nuts2_ith5",  # Nord-Est
  "nuts2_iti1", "nuts2_iti2", "nuts2_iti3", "nuts2_iti4",        # Centro
  "nuts2_itf1", "nuts2_itf2", "nuts2_itf3", "nuts2_itf4", "nuts2_itf5", "nuts2_itf6",  # Sud
  "nuts2_itg1", "nuts2_itg2"                                     # Isole (itg2 = reference)
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
