if (!requireNamespace("librarian", quietly = TRUE))
  stop("Package 'librarian' is not installed. Run install_packages.R from a node with internet access first.")
library(librarian)

librarian::shelf("raster", "sf", "tidyverse", "terra", "here", "tictoc", "foreach", "doParallel", "foreign", "dplyr",
                 "readxl", "giscoR",
                 "recipes", "stargazer", "caret", "ggpubr", "tidyterra", "gridExtra", "rasterVis", "RColorBrewer", "grid",
                 "lme4", "lmerTest", "ggstance", "cowplot", "mapview","viridis","patchwork")
sf_use_s2(FALSE)
library(ggnewscale)
ggsave <- function(..., bg = 'white') ggplot2::ggsave(..., bg = bg)

# Italian CRS: ETRS89 / LAEA Europe (equal-area; European equivalent of EPSG:5070)
projection <- raster::crs("+init=epsg:3035")

# Italian NUTS-2 regional boundaries via Eurostat (no shapefile download needed)
region_boundaries <- giscoR::gisco_get_nuts(
  year       = "2021",
  resolution = "03",
  spatialtype = "RG",
  country    = "IT",
  nuts_level = "2"
) %>%
  st_transform(crs = 3035) %>%
  select(NUTS_ID, NUTS_NAME, geometry)


# ── Shared model formula ───────────────────────────────────────────────────────
# Single definition sourced by modeling.R, spatial_cv.R, and any future script.
# lulc_other  omitted → reference land-cover class (Other lands baseline)
# nuts2_itg2  omitted → reference NUTS-2 region   (Sardegna baseline)
region_model <- treat ~
  # Infrastructure & demographics
  tx + roads + sub + slope + pop +
  # Socioeconomic
  unemploy + foreignborn + poverty + gdp_pc + inst_quality +
  # WorldClim BIO1-BIO19
  wclim_bio01 + wclim_bio02 + wclim_bio03 + wclim_bio04 + wclim_bio05 +
  wclim_bio06 + wclim_bio07 + wclim_bio08 + wclim_bio09 + wclim_bio10 +
  wclim_bio11 + wclim_bio12 + wclim_bio13 + wclim_bio14 + wclim_bio15 +
  wclim_bio16 + wclim_bio17 + wclim_bio18 + wclim_bio19 +
  # ERA5 climate (annual means 2000-2020)
  era5_t2m_mean + era5_t2m_max + era5_t2m_min + era5_t2m_std +
  era5_d2m_mean +
  era5_tp_sum + era5_cp_sum + era5_sf_sum +
  era5_e_sum + era5_pev_sum + era5_ro_sum +
  era5_u10_mean + era5_v10_mean + era5_u100_mean + era5_v100_mean + era5_i10fg_mean +
  era5_ssrd_sum + era5_ssr_sum + era5_cdir_sum + era5_ssrdc_sum +
  era5_tcc_mean + era5_blh_mean + era5_sp_mean + era5_cape_mean +
  # LUH3 land-use states 2020
  luh3_primf + luh3_primn + luh3_secdf + luh3_secdn +
  luh3_pastr + luh3_range + luh3_urban +
  luh3_c3ann + luh3_c4ann + luh3_c3per + luh3_c4per + luh3_c3nfx +
  # MODIS NDVI
  wt_ndvi_mean +
  # CORINE land cover (lulc_other omitted — reference)
  lulc_forest + lulc_grassland + lulc_shrubland + lulc_riparian +
  lulc_sparse + lulc_agriculture + lulc_developed +
  # NUTS-2 regions (nuts2_itg2 omitted — reference: Sardegna)
  nuts2_itc1 + nuts2_itc2 + nuts2_itc3 + nuts2_itc4 +
  nuts2_ith1 + nuts2_ith2 + nuts2_ith3 + nuts2_ith4 + nuts2_ith5 +
  nuts2_iti1 + nuts2_iti2 + nuts2_iti3 + nuts2_iti4 +
  nuts2_itf1 + nuts2_itf2 + nuts2_itf3 + nuts2_itf4 + nuts2_itf5 + nuts2_itf6 +
  nuts2_itg1 +
  # Technology-specific
  env + cf + lag
