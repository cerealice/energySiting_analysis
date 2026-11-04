source("./syntax/function.R")
librarian::shelf("htmlwidgets", "stars")

dir.create("./fig/new", showWarnings = FALSE, recursive = TRUE)

# ── Load and prep probability rasters ─────────────────────────────────────────
# Aggregate from 1 km to 5 km to keep the HTML file size manageable
# (5× factor = ~25× fewer cells; detail is preserved for a web map)
prep <- function(path, fact = 5) {
  terra::rast(path) |>
    terra::aggregate(fact = fact, fun = "mean", na.rm = TRUE) |>
    terra::project("EPSG:4326")           # leaflet requires WGS-84
}

pred_paths <- c(
  "GLM Solar"   = "./derived/pred_logReg_s.tif",
  "Lasso Solar" = "./derived/pred_lasso_s.tif",
  "RF Solar"    = "./derived/pred_randomForest_s.tif",
  "GBM Solar"   = "./derived/pred_xg_s.tif",
  "GLM Wind"    = "./derived/pred_logReg_w.tif",
  "Lasso Wind"  = "./derived/pred_lasso_w.tif",
  "RF Wind"     = "./derived/pred_randomForest_w.tif",
  "GBM Wind"    = "./derived/pred_xg_w.tif"
)

message("Loading and aggregating rasters …")
rasts <- lapply(pred_paths, prep)

# Ensemble means (average of all 4 models per technology)
solar_ens <- mean(terra::rast(rasts[1:4])); names(solar_ens) <- "Solar ensemble"
wind_ens  <- mean(terra::rast(rasts[5:8])); names(wind_ens)  <- "Wind ensemble"

# ── Build mapview layers ───────────────────────────────────────────────────────
# Shared settings: fixed 0–1 scale, transparent NAs, two basemaps
mv_opts <- mapviewOptions(
  basemaps        = c("CartoDB.Positron", "Esri.WorldImagery", "OpenStreetMap"),
  na.color        = "transparent",
  legend          = TRUE
)

make_layer <- function(r, name, pal) {
  mapview(
    r,
    layer.name    = name,
    col.regions   = pal,
    at            = seq(0, 1, by = 0.1),
    na.color      = "transparent",
    alpha.regions = 0.80
  )
}

solar_pal <- viridis::plasma(256)   # purple → yellow  (solar)
wind_pal  <- viridis::mako(256)     # dark → cyan/green (wind)

message("Building map layers …")

# Ensemble layers first (displayed by default when map opens)
mv <- make_layer(solar_ens, "Solar ensemble (mean)", solar_pal) +
      make_layer(wind_ens,  "Wind ensemble (mean)",  wind_pal)  +
      # Individual model layers (hidden by default; toggle in layer control)
      make_layer(rasts[["RF Solar"]],    "RF Solar",    solar_pal) +
      make_layer(rasts[["GBM Solar"]],   "GBM Solar",   solar_pal) +
      make_layer(rasts[["GLM Solar"]],   "GLM Solar",   solar_pal) +
      make_layer(rasts[["Lasso Solar"]], "Lasso Solar", solar_pal) +
      make_layer(rasts[["RF Wind"]],     "RF Wind",     wind_pal)  +
      make_layer(rasts[["GBM Wind"]],    "GBM Wind",    wind_pal)  +
      make_layer(rasts[["GLM Wind"]],    "GLM Wind",    wind_pal)  +
      make_layer(rasts[["Lasso Wind"]],  "Lasso Wind",  wind_pal)

# ── Save to self-contained HTML ────────────────────────────────────────────────
out <- normalizePath("./fig/new/probability_maps_interactive.html",
                     mustWork = FALSE)

htmlwidgets::saveWidget(
  widget        = mv@map,
  file          = out,
  selfcontained = TRUE,
  title         = "Italy Renewable Energy Siting — Probability Maps"
)

message("Saved: ", out)
message("Open in any browser to explore. Use the layer control (top-right) ",
        "to toggle individual models.")
