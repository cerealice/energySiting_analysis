source("./syntax/function.R")

# region_boundaries and projection are loaded from function.R
# region_boundaries: Italian NUTS-2 regions (21 units) as sf, CRS 3035

# Define the function
randomPts <- function(raster_mask, seeds, tech, location_csv){

  ### absent points
  Pts <- nrow(location_csv)

  region_proportions <- location_csv %>%
    group_by(state_code) %>%
    summarise(n = n()) %>%
    mutate(freq = n / sum(n)) %>%
    select(-n)

  region_proportions$count <- round(region_proportions$freq * Pts, 0)

  # All 21 Italian NUTS-2 regions — ensure every region gets at least some
  # absence points, even those with no observed projects.
  all_region_codes <- region_boundaries$NUTS_NAME

  for (reg in setdiff(all_region_codes, region_proportions$state_code)){
    region_proportions <- region_proportions %>%
      add_row(state_code = reg, freq = 0, count = 10)
  }

  # Radii for absence buffers: drawn from the distribution of presence-plant
  # radii (derived from capacity in tech.R). Extra points get the mean radius.
  radii <- location_csv$radius_m
  radii <- append(radii,
                  rep(mean(radii), (sum(region_proportions$count) - length(radii))))

  absence_locations <- data.frame()
  for (seed in 1:length(seeds)){

    set.seed(seeds[seed])
    for (reg in region_proportions$state_code){

      current_boundary <- region_boundaries[region_boundaries$NUTS_NAME == reg, ]
      raster_data      <- terra::crop(raster_mask, current_boundary, mask = TRUE)
      raster_data      <- mask(raster_data, current_boundary)
      cell_indices     <- which(raster_data[] == 1)

      n_needed <- region_proportions[region_proportions$state_code == reg, ]$count
      if (length(cell_indices) < n_needed) n_needed <- length(cell_indices)
      if (n_needed == 0) next

      coordinates <- raster::xyFromCell(raster_data,
                                        sample(cell_indices, n_needed)) %>%
        as.data.frame()

      absence_locations <- coordinates %>%
        mutate(iteration = seed) %>%
        rbind(absence_locations)
    }
  }

  absence_buff <- st_as_sf(absence_locations,
                           coords = c("x", "y"),
                           crs = projection) %>%
    mutate(id = seq_len(nrow(absence_locations))) %>%
    st_buffer(sample(radii, nrow(absence_locations), replace = TRUE))

  return(absence_buff)
}


# ── SOLAR ──────────────────────────────────────────────────────────────────────

solar_mask_rast    <- terra::rast("./derived/solar_hull_existing_mask.tif")
solar_suit         <- terra::rast("./data/processed_data/masks/solar_suitability_SL1.tif")
solar_location_csv <- read_csv("./derived/solar_hull_existing.csv")

# Remove existing solar sites from the eligible absence area
solar_absence_roi <- solar_suit %>%
  terra::mask(mask = solar_mask_rast, inverse = TRUE) %>%
  terra::project(projection) %>%
  raster()

writeRaster(x = solar_absence_roi,
            filename = "./derived/solar_absence_roi.tif",
            overwrite = TRUE)

solar_absence_roi <- raster("./derived/solar_absence_roi.tif")

s_ab_sf <- randomPts(raster_mask = solar_absence_roi,
                     seeds        = c(1:10),
                     tech         = "solar",
                     location_csv = solar_location_csv)


# ── WIND ───────────────────────────────────────────────────────────────────────

wind_mask_rast    <- terra::rast("./derived/wind_hull_existing_mask.tif")
wind_suit         <- terra::rast("./data/processed_data/masks/wind_suitability_SL1.tif")
wind_location_csv <- read_csv("./derived/wind_hull_existing.csv")

# Remove existing wind sites from the eligible absence area
wind_absence_roi <- wind_suit %>%
  terra::mask(mask = wind_mask_rast, inverse = TRUE) %>%
  terra::project(projection) %>%
  raster()

writeRaster(x = wind_absence_roi,
            filename = "./derived/wind_absence_roi.tif",
            overwrite = TRUE)

wind_absence_roi <- raster("./derived/wind_absence_roi.tif")

w_ab_sf <- randomPts(raster_mask = wind_absence_roi,
                     seeds        = c(1:10),
                     tech         = "wind",
                     location_csv = wind_location_csv)


save(s_ab_sf, solar_absence_roi,
     w_ab_sf, wind_absence_roi,
     file = "./derived/absence.RData")
load("./derived/absence.RData")
