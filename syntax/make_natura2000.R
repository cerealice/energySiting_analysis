source("./syntax/function.R")

base_ras  <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path  <- "./data/processed_data/variables"
italy_crs <- 3035

snap <- function(r, method = "bilinear") {
  r |> project(base_ras) |> resample(base_ras, method = method) |> mask(base_ras)
}

# ── Environmental impact score: Natura 2000 proximity + slope ────────────────
# Source: EEA Natura 2000 end-2024 (already in EPSG:3035)
#   Shapefile: data/raw_downloads/eea_v_3035_.../SHP/Natura2000_end2024_epsg3035.shp
# Score = 0.7 × (proximity to Natura 2000) + 0.3 × (normalised slope)
#   where proximity = 1 - dist/max_dist  (closer site → higher score → more sensitive)
# Same score written for both solar and wind.

message("Building environmental impact score (Natura 2000 + slope)")

shp_path <- "./data/raw_downloads/eea_v_3035_100_k_natura2000_p_2024_v01_r00/SHP/Natura2000_end2024_epsg3035.shp"

natura_it <- st_read(shp_path, quiet = TRUE) %>%
  filter(startsWith(SITECODE, "IT")) %>%   # Italian sites only
  st_transform(italy_crs) %>%
  vect()

message("  Italian Natura 2000 sites: ", nrow(natura_it))

# Rasterize and compute distance (already in 3035, same CRS as base_ras)
natura_rast  <- rasterize(natura_it, base_ras, field = 1)
dist_natura  <- distance(natura_rast) |> snap()

# Normalise: proximity = 1 - dist/max  (high = close to protected area = sensitive)
max_dist     <- global(dist_natura, "max", na.rm = TRUE)$max
prox_natura  <- 1 - dist_natura / max_dist

# Slope (already built by make_variables_italy.R)
slope_r      <- rast(file.path(var_path, "slope.tif"))
max_slope    <- global(slope_r, "max", na.rm = TRUE)$max
slope_norm   <- slope_r / max_slope

# Combined score
env_score <- (prox_natura * 0.7 + slope_norm * 0.3) |> mask(base_ras)

writeRaster(env_score, file.path(var_path, "env_impactScore_solar.tif"), overwrite = TRUE)
writeRaster(env_score, file.path(var_path, "env_impactScore_wind.tif"),  overwrite = TRUE)
message("  saved: env_impactScore_solar.tif and env_impactScore_wind.tif")

message("Done. Run stack.R to rebuild the predictor stack with the real env score.")
