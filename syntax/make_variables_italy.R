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


# ── 3b. Distance to transmission lines & substations (OSM) ───────────────────
# TERNA does not publish GIS downloads. OSM has comprehensive tagging of the
# Italian power grid (power=line, power=substation) — same cached PBF used above.
message("3b. Transmission lines & substations distance (OSM)")

# Transmission lines ≥ 110 kV
tx_sf <- osmextract::oe_get(
  "Italy",
  layer              = "lines",
  query              = "SELECT geometry, voltage FROM lines WHERE power = 'line'",
  download_directory = cache_path,
  quiet              = TRUE
) |> filter(!is.na(voltage))
# voltage field is a string in OSM (e.g. "132000", "220000;380000")
tx_sf <- tx_sf |>
  mutate(v = as.numeric(gsub(";.*", "", voltage))) |>
  filter(v >= 110000)
tx_rast <- rasterize(vect(tx_sf) |> project(crs(base_ras)), base_ras, field = 1)
save_var(distance(tx_rast) |> snap(), "transmission_110_qgis.tif")
# Planned lines not available in OSM — copy current as placeholder until
# TERNA's Grid Development Plan data becomes available
save_var(distance(tx_rast) |> snap(), "transmission_110_wPlanned.tif")

# Substations — OSM stores them as both points and multipolygons
subs_pts  <- osmextract::oe_get(
  "Italy", layer = "points",
  query = "SELECT geometry FROM points WHERE power = 'substation'",
  download_directory = cache_path, quiet = TRUE
)
subs_poly <- osmextract::oe_get(
  "Italy", layer = "multipolygons",
  query = "SELECT geometry FROM multipolygons WHERE power = 'substation'",
  download_directory = cache_path, quiet = TRUE
)
subs_sf    <- bind_rows(
  st_centroid(subs_poly) |> select(geometry),
  subs_pts |> select(geometry)
)
subs_rast  <- rasterize(vect(subs_sf) |> project(crs(base_ras)), base_ras, field = 1)
save_var(distance(subs_rast) |> snap(), "substations_110_qgis.tif")
save_var(distance(subs_rast) |> snap(), "substations_110_wPlanned.tif")


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
  2 variable groups still require manual downloads
================================================================

── A. SOCIOECONOMIC INDICATORS (ISTAT) ─────────────────────────

  FOREIGN-BORN % — 2021 permanent census, municipality level:
    1. Go to: https://esploradati.istat.it/databrowser/
    2. Navigate: Censimento Permanente Popolazione > Popolazione per
       cittadinanza > Comuni
    3. Download as CSV; the column for non-Italian citizens gives foreign-born %.
    4. Save to: data/raw_downloads/istat_foreignborn.csv

  UNEMPLOYMENT RATE — Labour Force Survey (Rilevazione Forze Lavoro):
    Note: LFS data is only available at provincial level, not municipality.
    1. Go to: http://dati.istat.it/ > Mercato del lavoro > Occupati e disoccupati
    2. Select: provinces (province), unemployment rate (tasso di disoccupazione)
    3. Download as CSV.
    4. Save to: data/raw_downloads/istat_unemp.csv
    5. Join to provinces via giscoR::gisco_get_nuts(nuts_level='3', country='IT')

  POVERTY PROXY — municipal taxable income (MEF):
    Unemployment is unavailable at municipality level; use mean taxable income
    as poverty proxy (lower income = higher poverty).
    1. Go to: https://www1.finanze.gov.it/finanze/analisi_stat/public/index.php
    2. Download > Dichiarazioni > Persone fisiche > Comuni
    3. Save to: data/raw_downloads/mef_income.csv

  After downloading, rasterize with:
    comuni <- giscoR::gisco_get_communes(country = 'IT', year = '2020') |>
                st_transform(italy_crs)
    comuni <- comuni |> left_join(istat_data, by = c('COMM_ID' = 'PRO_COM_T'))
    writeRaster(rasterize(vect(comuni), base_ras, field = 'foreignborn_pct') |> snap(),
                'data/processed_data/variables/svi_foreignborn.tif')
    # Repeat for svi_unemp.tif (joined at province level) and svi_pov.tif

── B. NATURA 2000 (for full environmental impact score) ─────────

  Direct download (no login required):
    Shapefile: https://cmshare.eea.europa.eu/s/HHGPnNsjqq5BdEa/download
    GeoPackage: https://www.eea.europa.eu/data-and-maps/data/natura-13/natura-2000-spatial-data/natura-2000-spatial-lite-1

  Save the extracted shapefile to: data/raw_downloads/Natura2000_end2021.shp
  Then run:

    natura <- st_read('data/raw_downloads/Natura2000_end2021.shp') |>
                filter(startsWith(SITECODE, 'IT')) |>
                st_transform(italy_crs) |> vect()
    natura_rast <- rasterize(natura, base_ras, field = 1)
    dist_natura <- distance(natura_rast) |> snap()
    dist_norm   <- 1 - dist_natura / global(dist_natura, 'max', na.rm=TRUE)$max
    slope_norm  <- rast('data/processed_data/variables/slope.tif') /
                     global(rast('data/processed_data/variables/slope.tif'),
                            'max', na.rm=TRUE)$max
    env_score   <- (dist_norm * 0.7 + slope_norm * 0.3) |> mask(base_ras)
    writeRaster(env_score, 'data/processed_data/variables/env_impactScore_solar.tif')
    writeRaster(env_score, 'data/processed_data/variables/env_impactScore_wind.tif')

================================================================
")
