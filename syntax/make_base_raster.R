library(giscoR)
library(sf)
library(terra)

# Resolution in metres (EPSG:3035 is metric)
res_m     <- 1000   # 1 km — change to 500 for 500 m, etc.
italy_crs <- 3035
out_path  <- "./data/processed_data/masks/Italy_base_raster.tif"

# ── 1. Get Italy's national boundary ─────────────────────────────────────────
# Uses giscoR (Eurostat GISCO service) — same source as the regional boundaries
# in function.R, so resolution and geometry are consistent.

message("Fetching Italy boundary from Eurostat (giscoR)...")

italy_boundary <- giscoR::gisco_get_countries(
  country    = "IT",
  resolution = "03",   # 1:3 million — sufficient for a 1 km raster
  year       = "2020"
) |>
  st_transform(crs = italy_crs) |>
  st_geometry() |>
  st_union()

# Alternative using OpenStreetMap (Overpass API, relation 365331).
# Can time out on slow connections — use giscoR above instead.
# italy_boundary <- osmdata::opq_osm_id(type = "relation", id = "365331") |>
#   osmdata::osmdata_sf() |>
#   (\(x) x$osm_multipolygons)() |>
#   st_geometry() |>
#   st_union() |>
#   st_make_valid() |>
#   st_transform(crs = italy_crs)

message("Boundary fetched. Extent: ", paste(round(st_bbox(italy_boundary)), collapse = ", "))


# ── 2. Create raster template ─────────────────────────────────────────────────
# Snap the bounding box to a clean multiple of res_m so raster cells align
# neatly with the LAEA origin.

bbox <- st_bbox(italy_boundary)
xmin <- floor(bbox["xmin"]   / res_m) * res_m
xmax <- ceiling(bbox["xmax"] / res_m) * res_m
ymin <- floor(bbox["ymin"]   / res_m) * res_m
ymax <- ceiling(bbox["ymax"] / res_m) * res_m

template <- terra::rast(
  xmin = xmin, xmax = xmax,
  ymin = ymin, ymax = ymax,
  resolution = res_m,
  crs = paste0("EPSG:", italy_crs)
)

message("Raster template: ", nrow(template), " rows x ", ncol(template), " cols")


# ── 3. Rasterize boundary (1 = Italy, NA = outside) ──────────────────────────

italy_vect  <- terra::vect(italy_boundary)
base_raster <- terra::rasterize(italy_vect, template, field = 1)

message("Cells within Italy: ", sum(!is.na(values(base_raster))))


# ── 4. Save ───────────────────────────────────────────────────────────────────

terra::writeRaster(base_raster, out_path, overwrite = TRUE)
message("Saved: ", out_path)
