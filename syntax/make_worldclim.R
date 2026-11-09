source("./syntax/function.R")
librarian::shelf("geodata")

# ── Make WorldClim BIO predictor rasters ──────────────────────────────────────
# Downloads WorldClim 2.1 bioclimatic variables (BIO1–BIO19) at 0.5 arcmin
# (~1 km — the finest available resolution), then snaps to the Italy base raster.
#
# BIO1  Annual Mean Temperature
# BIO2  Mean Diurnal Range
# BIO3  Isothermality
# BIO4  Temperature Seasonality
# BIO5  Max Temperature of Warmest Month
# BIO6  Min Temperature of Coldest Month
# BIO7  Annual Temperature Range
# BIO8  Mean Temperature of Wettest Quarter
# BIO9  Mean Temperature of Driest Quarter
# BIO10 Mean Temperature of Warmest Quarter
# BIO11 Mean Temperature of Coldest Quarter
# BIO12 Annual Precipitation
# BIO13 Precipitation of Wettest Month
# BIO14 Precipitation of Driest Month
# BIO15 Precipitation Seasonality (CV)
# BIO16 Precipitation of Wettest Quarter
# BIO17 Precipitation of Driest Quarter
# BIO18 Precipitation of Warmest Quarter
# BIO19 Precipitation of Coldest Quarter

base_ras <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path <- "./data/processed_data/variables"
dl_path  <- "./data/raw_downloads/worldclim"

snap_ll <- function(r) {
  r |>
    project(crs("EPSG:3035")) |>
    resample(base_ras, method = "bilinear") |>
    mask(base_ras)
}

# Check if all 19 layers already exist
existing <- file.exists(file.path(var_path, sprintf("wclim_bio%02d.tif", 1:19)))
if (all(existing)) {
  message("All WorldClim BIO layers already exist — nothing to do.")
  message("Delete wclim_bio*.tif files to force re-download.")
} else {
  message("Downloading WorldClim 2.1 BIO variables at 0.5 arcmin (~1 km)…")
  dir.create(dl_path, recursive = TRUE, showWarnings = FALSE)

  wc <- geodata::worldclim_global(var = "bio", res = 0.5, path = dl_path)
  message("Download complete. Processing ", nlyr(wc), " layers…")

  for (i in 1:nlyr(wc)) {
    out_path <- file.path(var_path, sprintf("wclim_bio%02d.tif", i))
    if (file.exists(out_path)) { message("Exists: wclim_bio", sprintf("%02d", i), ".tif"); next }
    r <- wc[[i]] |> snap_ll()
    writeRaster(r, out_path, overwrite = TRUE)
    message(sprintf("Saved:  wclim_bio%02d.tif", i))
  }
}

message("\nmake_worldclim.R complete — re-run stack.R to rebuild covStack.")
