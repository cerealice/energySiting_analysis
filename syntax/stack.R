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
#                   → Zenodo DOI 10.5281/zenodo.11121790 (gdp_pc, inst_quality)
#   Climate         → WorldClim 2.1 BIO1-BIO19 at 0.5 arcmin (make_worldclim.R)
#                   → ERA5 annual means 2000-2020 (download_worldtensor.py +
#                     make_worldtensor.R; WorldTensor DOI 10.5281/zenodo.19047618)
#   Land use        → LUH3 states year 2020 (WorldTensor; make_worldtensor.R)
#                   → MODIS NDVI mean 2003-2020 (WorldTensor; make_worldtensor.R)
#                   → Copernicus CORINE Land Cover / binary classes
#   Regions         → Italian NUTS-2 regions (make_nuts2_regions.R)
#
# Layer ordering: ALL continuous variables first (z-scored by build_stack),
# then binary indicators (unscaled). scale_up_to tracks the boundary.
# Continuous: 10 existing + 19 WorldClim + 24 ERA5 + 12 LUH3 + 1 NDVI = 66
# Binary    : 8 LULC + 21 NUTS-2 = 29
# Total     : 95

cov_paths <- c(
  # ── Continuous (layers 1–66, z-scored) ────────────────────────────────────

  # Infrastructure (1–3)
  file.path(processed_layer_path, "transmission_110_qgis.tif"),
  file.path(processed_layer_path, "roads_qgis.tif"),
  file.path(processed_layer_path, "substations_110_qgis.tif"),
  # Biophysical / demographics (4–5)
  file.path(processed_layer_path, "slope.tif"),
  file.path(processed_layer_path, "pop_density.tif"),
  # Socioeconomic — ISTAT census (6–8)
  file.path(processed_layer_path, "svi_unemp.tif"),
  file.path(processed_layer_path, "svi_foreignborn.tif"),
  file.path(processed_layer_path, "svi_pov.tif"),
  # Socioeconomic — Zenodo (9–10)
  file.path(processed_layer_path, "zenodo_gdp_pc.tif"),
  file.path(processed_layer_path, "zenodo_inst_quality.tif"),

  # WorldClim 2.1 BIO variables at ~1 km (11–29)
  file.path(processed_layer_path, "wclim_bio01.tif"),  # Annual Mean Temperature
  file.path(processed_layer_path, "wclim_bio02.tif"),  # Mean Diurnal Range
  file.path(processed_layer_path, "wclim_bio03.tif"),  # Isothermality
  file.path(processed_layer_path, "wclim_bio04.tif"),  # Temperature Seasonality
  file.path(processed_layer_path, "wclim_bio05.tif"),  # Max Temp Warmest Month
  file.path(processed_layer_path, "wclim_bio06.tif"),  # Min Temp Coldest Month
  file.path(processed_layer_path, "wclim_bio07.tif"),  # Annual Temperature Range
  file.path(processed_layer_path, "wclim_bio08.tif"),  # Mean Temp Wettest Quarter
  file.path(processed_layer_path, "wclim_bio09.tif"),  # Mean Temp Driest Quarter
  file.path(processed_layer_path, "wclim_bio10.tif"),  # Mean Temp Warmest Quarter
  file.path(processed_layer_path, "wclim_bio11.tif"),  # Mean Temp Coldest Quarter
  file.path(processed_layer_path, "wclim_bio12.tif"),  # Annual Precipitation
  file.path(processed_layer_path, "wclim_bio13.tif"),  # Precip Wettest Month
  file.path(processed_layer_path, "wclim_bio14.tif"),  # Precip Driest Month
  file.path(processed_layer_path, "wclim_bio15.tif"),  # Precip Seasonality (CV)
  file.path(processed_layer_path, "wclim_bio16.tif"),  # Precip Wettest Quarter
  file.path(processed_layer_path, "wclim_bio17.tif"),  # Precip Driest Quarter
  file.path(processed_layer_path, "wclim_bio18.tif"),  # Precip Warmest Quarter
  file.path(processed_layer_path, "wclim_bio19.tif"),  # Precip Coldest Quarter

  # ERA5 annual means 2000-2020 — downscaled from 0.25° (30–53)
  file.path(processed_layer_path, "era5_t2m_mean.tif"),   # 2m temp (mean)
  file.path(processed_layer_path, "era5_t2m_max.tif"),    # 2m temp (max)
  file.path(processed_layer_path, "era5_t2m_min.tif"),    # 2m temp (min)
  file.path(processed_layer_path, "era5_t2m_std.tif"),    # 2m temp (SD)
  file.path(processed_layer_path, "era5_d2m_mean.tif"),   # dewpoint temp
  file.path(processed_layer_path, "era5_tp_sum.tif"),     # total precipitation
  file.path(processed_layer_path, "era5_cp_sum.tif"),     # convective precip
  file.path(processed_layer_path, "era5_sf_sum.tif"),     # snowfall
  file.path(processed_layer_path, "era5_e_sum.tif"),      # evaporation
  file.path(processed_layer_path, "era5_pev_sum.tif"),    # potential evaporation
  file.path(processed_layer_path, "era5_ro_sum.tif"),     # runoff
  file.path(processed_layer_path, "era5_u10_mean.tif"),   # wind U 10m
  file.path(processed_layer_path, "era5_v10_mean.tif"),   # wind V 10m
  file.path(processed_layer_path, "era5_u100_mean.tif"),  # wind U 100m
  file.path(processed_layer_path, "era5_v100_mean.tif"),  # wind V 100m
  file.path(processed_layer_path, "era5_i10fg_mean.tif"), # wind gust 10m
  file.path(processed_layer_path, "era5_ssrd_sum.tif"),   # solar radiation down
  file.path(processed_layer_path, "era5_ssr_sum.tif"),    # net solar radiation
  file.path(processed_layer_path, "era5_cdir_sum.tif"),   # clear-sky direct solar
  file.path(processed_layer_path, "era5_ssrdc_sum.tif"),  # clear-sky solar down
  file.path(processed_layer_path, "era5_tcc_mean.tif"),   # total cloud cover
  file.path(processed_layer_path, "era5_blh_mean.tif"),   # boundary layer height
  file.path(processed_layer_path, "era5_sp_mean.tif"),    # surface pressure
  file.path(processed_layer_path, "era5_cape_mean.tif"),  # CAPE

  # LUH3 land-use states year 2020 — downscaled from 0.25° (54–65)
  file.path(processed_layer_path, "luh3_primf.tif"),   # primary forest
  file.path(processed_layer_path, "luh3_primn.tif"),   # primary non-forest
  file.path(processed_layer_path, "luh3_secdf.tif"),   # secondary forest
  file.path(processed_layer_path, "luh3_secdn.tif"),   # secondary non-forest
  file.path(processed_layer_path, "luh3_pastr.tif"),   # managed pasture
  file.path(processed_layer_path, "luh3_range.tif"),   # rangeland
  file.path(processed_layer_path, "luh3_urban.tif"),   # urban
  file.path(processed_layer_path, "luh3_c3ann.tif"),   # C3 annual crops
  file.path(processed_layer_path, "luh3_c4ann.tif"),   # C4 annual crops
  file.path(processed_layer_path, "luh3_c3per.tif"),   # C3 perennial crops
  file.path(processed_layer_path, "luh3_c4per.tif"),   # C4 perennial crops
  file.path(processed_layer_path, "luh3_c3nfx.tif"),   # N-fixing crops

  # MODIS NDVI mean 2003-2020 (66)
  file.path(processed_layer_path, "wt_ndvi_mean.tif"),

  # ── Binary (layers 67–95, unscaled) ───────────────────────────────────────

  # CORINE land cover (67–74)
  file.path(processed_layer_path, "lulc_forest.tif"),
  file.path(processed_layer_path, "lulc_grassland.tif"),
  file.path(processed_layer_path, "lulc_shrubland.tif"),
  file.path(processed_layer_path, "lulc_riparian.tif"),
  file.path(processed_layer_path, "lulc_sparselyvegetated.tif"),
  file.path(processed_layer_path, "lulc_agricultural.tif"),
  file.path(processed_layer_path, "lulc_developed.tif"),
  file.path(processed_layer_path, "lulc_other.tif"),

  # NUTS-2 regions (75–95; reference = nuts2_itg2 / Sardegna)
  file.path(processed_layer_path, "nuts2_itc1.tif"),   # Piemonte
  file.path(processed_layer_path, "nuts2_itc2.tif"),   # Valle d'Aosta
  file.path(processed_layer_path, "nuts2_itc3.tif"),   # Liguria
  file.path(processed_layer_path, "nuts2_itc4.tif"),   # Lombardia
  file.path(processed_layer_path, "nuts2_ith1.tif"),   # PA Bolzano
  file.path(processed_layer_path, "nuts2_ith2.tif"),   # PA Trento
  file.path(processed_layer_path, "nuts2_ith3.tif"),   # Veneto
  file.path(processed_layer_path, "nuts2_ith4.tif"),   # Friuli-VG
  file.path(processed_layer_path, "nuts2_ith5.tif"),   # Emilia-Romagna
  file.path(processed_layer_path, "nuts2_iti1.tif"),   # Toscana
  file.path(processed_layer_path, "nuts2_iti2.tif"),   # Umbria
  file.path(processed_layer_path, "nuts2_iti3.tif"),   # Marche
  file.path(processed_layer_path, "nuts2_iti4.tif"),   # Lazio
  file.path(processed_layer_path, "nuts2_itf1.tif"),   # Abruzzo
  file.path(processed_layer_path, "nuts2_itf2.tif"),   # Molise
  file.path(processed_layer_path, "nuts2_itf3.tif"),   # Campania
  file.path(processed_layer_path, "nuts2_itf4.tif"),   # Puglia
  file.path(processed_layer_path, "nuts2_itf5.tif"),   # Basilicata
  file.path(processed_layer_path, "nuts2_itf6.tif"),   # Calabria
  file.path(processed_layer_path, "nuts2_itg1.tif"),   # Sicilia
  file.path(processed_layer_path, "nuts2_itg2.tif")    # Sardegna (reference)
)

cov_names <- c(
  # Existing continuous (1–10)
  "tx", "roads", "sub", "slope", "pop",
  "unemploy", "foreignborn", "poverty", "gdp_pc", "inst_quality",
  # WorldClim BIO (11–29)
  "wclim_bio01", "wclim_bio02", "wclim_bio03", "wclim_bio04", "wclim_bio05",
  "wclim_bio06", "wclim_bio07", "wclim_bio08", "wclim_bio09", "wclim_bio10",
  "wclim_bio11", "wclim_bio12", "wclim_bio13", "wclim_bio14", "wclim_bio15",
  "wclim_bio16", "wclim_bio17", "wclim_bio18", "wclim_bio19",
  # ERA5 (30–53)
  "era5_t2m_mean", "era5_t2m_max", "era5_t2m_min", "era5_t2m_std",
  "era5_d2m_mean",
  "era5_tp_sum", "era5_cp_sum", "era5_sf_sum",
  "era5_e_sum", "era5_pev_sum", "era5_ro_sum",
  "era5_u10_mean", "era5_v10_mean", "era5_u100_mean", "era5_v100_mean", "era5_i10fg_mean",
  "era5_ssrd_sum", "era5_ssr_sum", "era5_cdir_sum", "era5_ssrdc_sum",
  "era5_tcc_mean", "era5_blh_mean", "era5_sp_mean", "era5_cape_mean",
  # LUH3 (54–65)
  "luh3_primf", "luh3_primn", "luh3_secdf", "luh3_secdn",
  "luh3_pastr", "luh3_range", "luh3_urban",
  "luh3_c3ann", "luh3_c4ann", "luh3_c3per", "luh3_c4per", "luh3_c3nfx",
  # NDVI (66)
  "wt_ndvi_mean",
  # CORINE LULC binary (67–74)
  "lulc_forest", "lulc_grassland", "lulc_shrubland", "lulc_riparian",
  "lulc_sparse", "lulc_agriculture", "lulc_developed", "lulc_other",
  # NUTS-2 binary (75–95)
  "nuts2_itc1", "nuts2_itc2", "nuts2_itc3", "nuts2_itc4",
  "nuts2_ith1", "nuts2_ith2", "nuts2_ith3", "nuts2_ith4", "nuts2_ith5",
  "nuts2_iti1", "nuts2_iti2", "nuts2_iti3", "nuts2_iti4",
  "nuts2_itf1", "nuts2_itf2", "nuts2_itf3", "nuts2_itf4", "nuts2_itf5", "nuts2_itf6",
  "nuts2_itg1", "nuts2_itg2"
)

# Layers 1–66 are continuous → z-scored; 67–95 are binary → unscaled
build_stack(cov_paths, cov_names, scale_up_to = 66, out_path = "./derived/covStack.tif")


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
