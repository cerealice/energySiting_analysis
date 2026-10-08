source("./syntax/function.R")

# italy_crs and region_boundaries are loaded from function.R
italy_crs <- 3035

base_ras <- terra::rast("./data/processed_data/masks/Italy_base_raster.tif")

solar_path <- "../data/Global-Solar-Power-Tracker-February-2026.xlsx"
wind_path  <- "../data/Global-Wind-Power-Tracker-February-2026.xlsx"


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

# Mask: all operating plants buffered 500 m — used to exclude existing sites
# from absence-point sampling (equivalent to solar_mask in the US workflow).
solar_mask <- solar_sf %>%
  mutate(unique_id = row_number()) %>%
  st_buffer(dist = 500)

# Locations: plants commissioned >=2017, capacity >=1 MW.
# area_m2 is estimated at 10,000 m²/MW (~1 ha/MW: standard utility-scale solar
# density including access roads and setbacks). radius_m replaces st_area() on
# polygon footprints and is used in absence.R to size absence-point buffers.
solar_locations <- solar_sf %>%
  filter(`Start year`    >= 2017,
         `Capacity (MW)` >= 1,
         !is.na(state_code)) %>%
  mutate(unique_id = row_number(),
         area_m2   = `Capacity (MW)` * 10000,
         radius_m  = sqrt(area_m2 / pi))

# Rasterize mask
solar_mask_rast <- solar_mask %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)
# plot(solar_mask_rast)

# Rasterize locations
solar_location_rast <- solar_locations %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)

# Save
writeRaster(x = solar_mask_rast,
            filename = "./derived/solar_hull_existing_mask.tif",
            overwrite = TRUE)

writeRaster(x = solar_location_rast,
            filename = "./derived/solar_hull_existing.tif",
            overwrite = TRUE)

write_csv(solar_locations %>% st_drop_geometry(),
          file = "./derived/solar_hull_existing.csv")


# ── WIND ───────────────────────────────────────────────────────────────────────

# The GEM Wind Power Tracker is already at project level — no turbine
# aggregation or convex-hull step needed (unlike USWTDB which stored individual
# turbine points that had to be grouped by project name).

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

# Mask: all operating plants buffered 500 m.
wind_mask <- wind_sf %>%
  mutate(unique_id = row_number()) %>%
  st_buffer(dist = 500)

# Locations: plants commissioned >=2017, capacity >=10 MW.
# area_m2 estimated at 300,000 m²/MW (~3 MW/km²: typical onshore wind array
# density including turbine spacing). This approximates the convex-hull area
# computed from individual turbine points in the US workflow.
wind_locations <- wind_sf %>%
  filter(`Start year`    >= 2017,
         `Capacity (MW)` >= 10,
         !is.na(state_code)) %>%
  mutate(unique_id = row_number(),
         p_cap     = `Capacity (MW)`,
         area_m2   = `Capacity (MW)` * 300000,
         radius_m  = sqrt(area_m2 / pi))

# Rasterize mask
wind_mask_rast <- wind_mask %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)
# plot(wind_mask_rast)

# Rasterize locations
wind_location_rast <- wind_locations %>%
  terra::vect() %>%
  terra::rasterize(y = base_ras, field = "unique_id", touches = TRUE) %>%
  terra::mask(base_ras)

# Save
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
