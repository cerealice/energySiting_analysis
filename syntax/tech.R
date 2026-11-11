source("./syntax/function.R")

# Create output directory if it doesn't exist
dir.create("./derived", showWarnings = FALSE, recursive = TRUE)

# italy_crs and region_boundaries are loaded from function.R
italy_crs <- 3035

base_ras <- terra::rast("./data/processed_data/masks/Italy_base_raster.tif")

solar_path <- "./data/Global-Solar-Power-Tracker-February-2026.xlsx"
wind_path  <- "./data/Global-Wind-Power-Tracker-February-2026.xlsx"


# ── SOLAR ──────────────────────────────────────────────────────────────────────

solar_raw <- read_xlsx(solar_path, sheet = "Utility-Scale (1 MW+)") %>%
  filter(`Country/Area`    == "Italy",
         `Technology Type` %in% c("PV", "Assumed PV"),
         Status            == "operating",
         !is.na(Latitude), !is.na(Longitude))

solar_sf <- solar_raw %>%
  st_as_sf(coords = c("Longitude", "Latitude"), crs = 4326) %>%
  st_transform(crs = italy_crs)

# Assign Italian NUTS-2 region to each plant via spatial join
solar_sf <- solar_sf %>%
  st_join(region_boundaries %>% select(NUTS_NAME), join = st_within) %>%
  rename(state_code = NUTS_NAME)

# Mask: all operating GSPT plants buffered 500 m
solar_mask <- solar_sf %>%
  mutate(unique_id = row_number()) %>%
  st_buffer(dist = 500)

# Locations: plants commissioned >=2017, capacity >=1 MW.
solar_locations <- solar_sf %>%
  filter(`Start year`    >= 2017,
         `Capacity (MW)` >= 1,
         !is.na(state_code)) %>%
  mutate(unique_id = row_number(),
         area_m2   = `Capacity (MW)` * 10000,
         radius_m  = sqrt(area_m2 / pi))


# ── Unzip RSE shapefiles on first run ────────────────────────────────────────
rse_solar_shp <- "./data/raw_downloads/rse_atlante/fv_pot_comunale_2021/fv_pot_comunale_2021.shp"
rse_wind_shp  <- "./data/raw_downloads/rse_atlante/eo_pot_comunale_2019/eo_pot_comunale_2019.shp"

if (!file.exists(rse_solar_shp)) {
  message("Extracting RSE solar shapefile...")
  dir.create(dirname(rse_solar_shp), recursive = TRUE, showWarnings = FALSE)
  unzip("./data/raw_downloads/d__temp_fv_pot_comunale_2021.zip",
        exdir = dirname(rse_solar_shp))
}
if (!file.exists(rse_wind_shp)) {
  message("Extracting RSE wind shapefile...")
  dir.create(dirname(rse_wind_shp), recursive = TRUE, showWarnings = FALSE)
  unzip("./data/raw_downloads/d__temp_eo_pot_comunale_2019.zip",
        exdir = dirname(rse_wind_shp))
}


# ── SOLAR: Enrich with RSE Atlante Integrato (fv_pot_comunale_2021) ──────────
# RSE provides total installed ground-mounted PV capacity (MW) per municipality
# as of 2021. SOURCE FILTER (applied by RSE before publication): only plants
# with individual capacity > 100 kW are included — rooftop and small-scale
# systems are excluded at source. PV panels have 25–30 yr lifetimes, so 2021
# installations are still active in 2026.
# Threshold: >= 1 MW municipal total to match GSPT's per-plant minimum.

rse_solar_raw <- st_read(rse_solar_shp, quiet = TRUE) %>%
  filter(VALORE >= 1) %>%
  st_transform(italy_crs) %>%
  st_centroid() %>%
  st_join(region_boundaries %>% select(NUTS_NAME), join = st_within) %>%
  rename(state_code = NUTS_NAME) %>%
  filter(!is.na(state_code))

# Discard RSE centroids already covered by GSPT mask (within 500 m)
rse_solar_new <- rse_solar_raw %>%
  mutate(in_mask = lengths(st_is_within_distance(., solar_mask, dist = 500)) > 0) %>%
  filter(!in_mask) %>%
  mutate(
    `Capacity (MW)` = as.numeric(VALORE),
    `Start year`    = 2021L,
    area_m2         = as.numeric(VALORE) * 10000,
    radius_m        = sqrt(area_m2 / pi)
  )

message("RSE solar: ", nrow(rse_solar_raw), " comuni >= 1 MW; ",
        nrow(rse_solar_new), " new (not already in GSPT mask)")

# Merge RSE into mask (so absence sampling avoids these locations too)
solar_mask <- bind_rows(
  solar_mask,
  rse_solar_new %>%
    st_buffer(dist = 500) %>%
    mutate(unique_id = nrow(solar_mask) + row_number()) %>%
    select(unique_id)
)

# Merge RSE into locations (additional presence points)
solar_locations <- bind_rows(
  solar_locations,
  rse_solar_new %>%
    select(state_code, `Capacity (MW)`, `Start year`, area_m2, radius_m) %>%
    mutate(unique_id = nrow(solar_locations) + row_number())
)

message("Solar locations total: ", nrow(solar_locations), " (GSPT + RSE Atlante)")


# ── Rasterize solar ───────────────────────────────────────────────────────────

solar_mask_rast <- solar_mask %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)

solar_location_rast <- solar_locations %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)

writeRaster(x = solar_mask_rast,
            filename = "./derived/solar_hull_existing_mask.tif",
            overwrite = TRUE)

writeRaster(x = solar_location_rast,
            filename = "./derived/solar_hull_existing.tif",
            overwrite = TRUE)

write_csv(solar_locations %>% st_drop_geometry(),
          file = "./derived/solar_hull_existing.csv")


# ── WIND ───────────────────────────────────────────────────────────────────────

wind_raw <- read_xlsx(wind_path, sheet = "Data") %>%
  filter(`Country/Area`      == "Italy",
         `Installation Type` == "Onshore",
         Status              == "operating",
         !is.na(Latitude), !is.na(Longitude))

wind_sf <- wind_raw %>%
  st_as_sf(coords = c("Longitude", "Latitude"), crs = 4326) %>%
  st_transform(crs = italy_crs)

# Assign Italian NUTS-2 region via spatial join
wind_sf <- wind_sf %>%
  st_join(region_boundaries %>% select(NUTS_NAME), join = st_within) %>%
  rename(state_code = NUTS_NAME)

# Mask: all operating GWPT plants buffered 500 m.
wind_mask <- wind_sf %>%
  mutate(unique_id = row_number()) %>%
  st_buffer(dist = 500)

# Locations: plants commissioned >=2017, capacity >=10 MW.
wind_locations <- wind_sf %>%
  filter(`Start year`    >= 2017,
         `Capacity (MW)` >= 10,
         !is.na(state_code)) %>%
  mutate(unique_id = row_number(),
         p_cap     = `Capacity (MW)`,
         area_m2   = `Capacity (MW)` * 300000,
         radius_m  = sqrt(area_m2 / pi))


# ── WIND: Enrich with RSE Atlante Integrato (eo_pot_comunale_2019) ───────────
# RSE provides total installed wind capacity (MW) per municipality as of 2019.
# Sources: GSE incentivized-plant register, The Wind Power database, Sentinel-2
# satellite imagery, ISTAT administrative boundaries.
# No explicit minimum turbine size is stated (unlike the solar file), but all
# source databases are utility-scale focused; micro-wind is negligible in Italy.
# Wind turbines have 20–25 yr lifetimes — 2019 installations still active 2026.
# Threshold: >= 1 MW per comune to filter any residual micro-wind entries.

rse_wind_raw <- st_read(rse_wind_shp, quiet = TRUE) %>%
  filter(VALORE >= 1) %>%
  st_transform(italy_crs) %>%
  st_centroid() %>%
  st_join(region_boundaries %>% select(NUTS_NAME), join = st_within) %>%
  rename(state_code = NUTS_NAME) %>%
  filter(!is.na(state_code))

# Discard RSE centroids already covered by GWPT mask (within 500 m)
rse_wind_new <- rse_wind_raw %>%
  mutate(in_mask = lengths(st_is_within_distance(., wind_mask, dist = 500)) > 0) %>%
  filter(!in_mask) %>%
  mutate(
    `Capacity (MW)` = as.numeric(VALORE),
    p_cap           = as.numeric(VALORE),
    `Start year`    = 2019L,
    area_m2         = as.numeric(VALORE) * 300000,
    radius_m        = sqrt(area_m2 / pi)
  )

message("RSE wind: ", nrow(rse_wind_raw), " comuni >= 1 MW; ",
        nrow(rse_wind_new), " new (not already in GWPT mask)")

# Merge RSE into mask
wind_mask <- bind_rows(
  wind_mask,
  rse_wind_new %>%
    st_buffer(dist = 500) %>%
    mutate(unique_id = nrow(wind_mask) + row_number()) %>%
    select(unique_id)
)

# Merge RSE into locations
wind_locations <- bind_rows(
  wind_locations,
  rse_wind_new %>%
    select(state_code, `Capacity (MW)`, p_cap, `Start year`, area_m2, radius_m) %>%
    mutate(unique_id = nrow(wind_locations) + row_number())
)

message("Wind locations total: ", nrow(wind_locations), " (GWPT + RSE Atlante)")


# ── Rasterize wind ────────────────────────────────────────────────────────────

wind_mask_rast <- wind_mask %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)

wind_location_rast <- wind_locations %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)

writeRaster(x = wind_mask_rast,
            filename = "./derived/wind_hull_existing_mask.tif",
            overwrite = TRUE)

writeRaster(x = wind_location_rast,
            filename = "./derived/wind_hull_existing.tif",
            overwrite = TRUE)

write_csv(wind_locations %>% st_drop_geometry(),
          file = "./derived/wind_hull_existing.csv")


save(solar_locations, wind_locations,
     file = "./derived/location.RData")
