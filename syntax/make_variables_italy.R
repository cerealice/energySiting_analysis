source("./syntax/function.R")
librarian::shelf("geodata", "osmextract")

base_ras   <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path   <- "./data/processed_data/variables"
cache_path <- "./data/raw_downloads"
dir.create(var_path,   showWarnings = FALSE, recursive = TRUE)
dir.create(cache_path, showWarnings = FALSE, recursive = TRUE)

italy_crs <- 3035

# Reproject + resample + mask every incoming raster to the base grid
snap <- function(r, method = "bilinear") {
  r |> project(base_ras) |> resample(base_ras, method = method) |> mask(base_ras)
}

save_var <- function(r, filename) {
  writeRaster(r, file.path(var_path, filename), overwrite = TRUE)
  message("  saved: ", filename)
}


# ── 1. Slope ──────────────────────────────────────────────────────────────────
# Source: SRTM 3 arc-second DEM via geodata (no registration needed)
message("1. Slope")
dem   <- geodata::elevation_3s(country = "ITA", path = cache_path)
slope <- terrain(snap(dem), "slope", unit = "degrees")
save_var(slope, "slope.tif")


# ── 2. Population density ─────────────────────────────────────────────────────
# Source: WorldPop 2020, 1 arc-minute (~2 km) resampled to 1 km
message("2. Population density")
pop <- geodata::population(year = 2020, res = 1, path = cache_path)
save_var(snap(pop), "pop_density.tif")


# ── 3. Distance to roads (OSM) ────────────────────────────────────────────────
# Source: OpenStreetMap via osmextract (~1.5 GB download, cached after first run)
message("3. Roads distance (OSM) — large download on first run")
roads_sf <- osmextract::oe_get(
  "Italy",
  layer              = "lines",
  query              = "SELECT geometry FROM lines WHERE highway IS NOT NULL",
  download_directory = cache_path,
  quiet              = TRUE
)
roads_rast <- rasterize(vect(roads_sf) |> project(crs(base_ras)), base_ras, field = 1)
save_var(distance(roads_rast) |> snap(), "roads_qgis.tif")


# ── 4. Solar capacity factor (WorldClim solar radiation proxy) ────────────────
# Source: WorldClim 2.1 monthly solar radiation (kJ/m²/day), 0.5 arc-min
# Note: replace with PVGIS data for production analysis —
#   downloadable NetCDF from https://re.jrc.ec.europa.eu/pvgis5/
message("4. Solar capacity factor (WorldClim srad proxy)")
srad <- geodata::worldclim_global(var = "srad", res = 0.5, path = cache_path)
save_var(snap(mean(srad)), "solar_capacity.tif")


# ── 5. Wind capacity factor (WorldClim wind speed proxy) ─────────────────────
# Source: WorldClim 2.1 monthly wind speed (m/s at 10 m), 0.5 arc-min
# Note: replace with ERA5 via ecmwfr for production analysis —
#   free CDS account at https://cds.climate.copernicus.eu
message("5. Wind capacity factor (WorldClim wind proxy)")
wind <- geodata::worldclim_global(var = "wind", res = 0.5, path = cache_path)
save_var(snap(mean(wind)), "wind_capacity.tif")


# ── 6. Land use / land cover (ESA WorldCover 2021) ───────────────────────────
# Source: ESA 10m global land cover via geodata (fractional cover per class)
# Mapping to analysis classes:
#   trees → forest  |  shrubs → shrubland  |  grassland → grassland
#   cropland → agricultural  |  built → developed  |  bare → sparsely vegetated
#   water → riparian (closest proxy)  |  1 - sum(all above) → other
message("6. Land use / land cover (ESA WorldCover)")
lulc_map <- list(
  lulc_forest            = "trees",
  lulc_shrubland         = "shrubs",
  lulc_grassland         = "grassland",
  lulc_agricultural      = "cropland",
  lulc_developed         = "built",
  lulc_sparselyvegetated = "bare",
  lulc_riparian          = "water"
)
for (out_name in names(lulc_map)) {
  lc <- geodata::landcover(var = lulc_map[[out_name]], path = cache_path)
  save_var(snap(lc), paste0(out_name, ".tif"))
}
# other = residual (clamped 0–1)
all_lc <- rast(file.path(var_path, paste0(names(lulc_map), ".tif")))
save_var(clamp(1 - sum(all_lc, na.rm = TRUE), 0, 1) |> mask(base_ras), "lulc_other.tif")


# ── 7. Italian NUTS-1 macro-region dummies ────────────────────────────────────
# Source: Eurostat GISCO via giscoR (no download needed)
message("7. NUTS-1 region dummies")
nuts1 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "1",
                                 year = "2021", resolution = "03") |>
  st_transform(crs = italy_crs)

region_ids <- c(
  region_nordovest = "ITC",   # Piemonte, Valle d'Aosta, Liguria, Lombardia
  region_nordest   = "ITH",   # Trentino-AA, Veneto, Friuli-VG, Emilia-Romagna
  region_centro    = "ITI",   # Toscana, Umbria, Marche, Lazio
  region_sud       = "ITF",   # Abruzzo, Molise, Campania, Puglia, Basilicata, Calabria
  region_isole     = "ITG"    # Sicilia, Sardegna
)
for (out_name in names(region_ids)) {
  poly <- nuts1[nuts1$NUTS_ID == region_ids[[out_name]], ]
  r    <- rasterize(vect(poly), base_ras, field = 1)
  r[is.na(r) & !is.na(base_ras)] <- 0
  save_var(r, paste0(out_name, ".tif"))
}


# ── 8. Spatial lag of existing development ────────────────────────────────────
# Focal mean within a 50 km radius — captures neighbourhood clustering.
# Requires tech.R outputs in derived/.
message("8. Spatial lag")
w <- focalMat(base_ras, d = 50000, type = "circle")

for (tech in c("solar", "wind")) {
  exist      <- rast(paste0("./derived/", tech, "_hull_existing.tif"))
  exist[is.na(exist)] <- 0
  lag        <- focal(exist, w = w, fun = "mean", na.rm = TRUE) |> mask(base_ras)
  save_var(lag, paste0(tech, "_lag.tif"))
}


# ── 9. FER incentive zone ─────────────────────────────────────────────────────
# Italy's FER incentive scheme (GSE) operates nationally rather than by region,
# so all suitable Italian land is treated as incentive-eligible.
# Replace with zone-specific data from GSE/MASE when available:
#   https://www.gse.it/servizi-per-te/fer-x
message("9. FER incentive (national binary placeholder)")
fer <- base_ras
values(fer)[!is.na(values(fer))] <- 1
save_var(fer, "fer_incentive.tif")


# ── 10. Environmental impact score ───────────────────────────────────────────
# Composite of slope (steeper = more sensitive) and proximity to Natura 2000
# sites. The Natura 2000 component requires a manual download (see below).
# This step produces a slope-only score; rerun after adding Natura 2000 data.
message("10. Environmental impact score (slope-only until Natura 2000 added)")
slope_r    <- rast(file.path(var_path, "slope.tif"))
slope_norm <- slope_r / global(slope_r, "max", na.rm = TRUE)$max
env_score  <- slope_norm |> mask(base_ras)
save_var(env_score, "env_impactScore_solar.tif")
save_var(env_score, "env_impactScore_wind.tif")


# ══ MANUAL DOWNLOADS REQUIRED ════════════════════════════════════════════════
message("
================================================================
  3 variable groups still require manual downloads
================================================================

── A. TRANSMISSION LINES & SUBSTATIONS (TERNA) ─────────────────
   Download GIS data (shapefile / GeoJSON) from:
   https://www.terna.it/it/sistema-elettrico/rete/piano-sviluppo-rete

   Save to: data/raw_downloads/terna_lines.shp (and terna_substations.shp)
   Then run:

     lines      <- st_read('data/raw_downloads/terna_lines.shp') |>
                     filter(VOLTAGE >= 110) |>
                     st_transform(italy_crs) |> vect()
     lines_rast <- rasterize(lines, base_ras, field = 1)
     writeRaster(distance(lines_rast) |> snap(),
                 'data/processed_data/variables/transmission_110_qgis.tif')
     # Repeat for:
     #   substations → substations_110_qgis.tif
     #   planned lines → transmission_110_wPlanned.tif
     #   planned substations → substations_110_wPlanned.tif

── B. SOCIOECONOMIC INDICATORS (ISTAT) ─────────────────────────
   Download municipality-level census indicators (unemployment, poverty,
   foreign-born %) from the ISTAT permanent census data explorer:
   https://esploradati.istat.it/databrowser/

   Join to municipality boundaries via giscoR, then rasterize:

     comuni <- giscoR::gisco_get_communes(country = 'IT', year = '2020') |>
                 st_transform(italy_crs)
     comuni <- comuni |> left_join(istat_data, by = c('COMM_ID' = 'municipality_code'))
     writeRaster(rasterize(vect(comuni), base_ras, field = 'unemployment_rate') |> snap(),
                 'data/processed_data/variables/svi_unemp.tif')
     # Repeat for svi_pov.tif and svi_foreignborn.tif

── C. NATURA 2000 (for full environmental impact score) ─────────
   Download the European Natura 2000 shapefile from EEA:
   https://www.eea.europa.eu/data-and-maps/data/natura-14

   Filter to Italy (SITECODE starts with 'IT'), then add to env score:

     natura <- st_read('data/raw_downloads/Natura2000_end2021.shp') |>
                 filter(startsWith(SITECODE, 'IT')) |>
                 st_transform(italy_crs) |> vect()
     natura_rast  <- rasterize(natura, base_ras, field = 1)
     dist_natura  <- distance(natura_rast) |> snap()
     # Invert: closer to Natura 2000 = higher sensitivity
     dist_norm    <- 1 - dist_natura / global(dist_natura, 'max', na.rm=TRUE)$max
     slope_norm   <- rast('data/processed_data/variables/slope.tif') /
                       global(rast('data/processed_data/variables/slope.tif'),
                              'max', na.rm=TRUE)$max
     env_score    <- (dist_norm * 0.7 + slope_norm * 0.3) |> mask(base_ras)
     writeRaster(env_score, 'data/processed_data/variables/env_impactScore_solar.tif')
     writeRaster(env_score, 'data/processed_data/variables/env_impactScore_wind.tif')

================================================================
")
