source("./syntax/function.R")

# ── Binary NUTS-2 indicator rasters for Italy ─────────────────────────────────
# Output: one .tif per NUTS-2 region in data/processed_data/variables/
# Naming convention: nuts2_<lowercase_id>.tif   (e.g. nuts2_itc1.tif)
# Reference class (omitted from model formula): nuts2_itg2 (Sardegna)
# Run ONCE; rerun only if the base raster or boundaries change.

base_ras <- rast("./data/processed_data/masks/Italy_base_raster.tif")
italy_crs <- 3035
var_path  <- "./data/processed_data/variables"

nuts2 <- giscoR::gisco_get_nuts(
  country    = "IT",
  nuts_level = "2",
  year       = "2016",
  resolution = "03"
) %>%
  st_transform(italy_crs)

message(sprintf("Found %d NUTS-2 regions: %s",
                nrow(nuts2),
                paste(sort(nuts2$NUTS_ID), collapse = ", ")))

for (i in seq_len(nrow(nuts2))) {
  id    <- nuts2$NUTS_ID[i]
  fname <- file.path(var_path, paste0("nuts2_", tolower(id), ".tif"))
  nuts2[i, ] %>%
    vect() %>%
    rasterize(base_ras, background = 0L) %>%
    mask(base_ras) %>%
    writeRaster(fname, overwrite = TRUE)
  message("Saved: ", fname)
}

message("\nAll ", nrow(nuts2), " NUTS-2 indicator rasters written.")
message("Next steps: re-run stack.R → zonal.R → modeling.R")
