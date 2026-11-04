source("./syntax/function.R")

# ── Zenodo NUTS-3 socioeconomic indicators ────────────────────────────────────
# Source: DOI 10.5281/zenodo.11121790
# Paper:  Nature Scientific Data, 2025
# File:   NUTS_3_DATA.csv  →  place in ./data/raw_downloads/
#
# We extract two variables not already in the predictor stack:
#   1. gdp_pc_const_p        — GDP per capita (constant prices), economic
#                              development proxy independent of household income
#   2. institutional_quality_index — composite governance score; provinces with
#                              stronger institutions may process permits faster
#
# Join key: province_name (Italian) matched to gisco NUTS-3 NAME_LATN field.
# ─────────────────────────────────────────────────────────────────────────────

base_ras  <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path  <- "./data/processed_data/variables"
italy_crs <- 3035

snap <- function(r, method = "bilinear") {
  r |> project(base_ras) |> resample(base_ras, method = method) |> mask(base_ras)
}

# ── 1. Load and clean Zenodo data ─────────────────────────────────────────────
zenodo_raw <- read_csv(
  "./data/raw_downloads/NUTS_3_DATA.csv",
  show_col_types = FALSE
)

# Select the most recent year with actual data for EACH variable independently.
# This avoids the case where the latest row has gdp_pc but inst_quality = NA
# (or vice versa), which would leave half the provinces as NA after the join.
zenodo_gdp <- zenodo_raw %>%
  filter(!is.na(gdp_pc_const_p)) %>%
  group_by(province_name) %>%
  slice_max(year, n = 1, with_ties = FALSE) %>%
  ungroup() %>%
  select(province_name, gdp_pc = gdp_pc_const_p)

zenodo_inst <- zenodo_raw %>%
  filter(!is.na(institutional_quality_index)) %>%
  group_by(province_name) %>%
  slice_max(year, n = 1, with_ties = FALSE) %>%
  ungroup() %>%
  select(province_name, inst_quality = institutional_quality_index)

zenodo <- full_join(zenodo_gdp, zenodo_inst, by = "province_name")

message(sprintf("Zenodo data: %d provinces with gdp_pc, %d with inst_quality",
                sum(!is.na(zenodo$gdp_pc)), sum(!is.na(zenodo$inst_quality))))

# ── 2. Load NUTS-3 geometries ─────────────────────────────────────────────────
nuts3 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "3",
                                 year = "2016", resolution = "03") %>%
  st_transform(italy_crs)

# ── 3. Name harmonisation table ───────────────────────────────────────────────
# Maps Zenodo province_name → gisco NAME_LATN where they differ.
# Extend this table if the diagnostic below reports unmatched provinces.
name_fix <- tribble(
  ~province_name,             ~gisco_name,
  "Aosta",                    "Valle d'Aosta/Vallée d'Aoste",
  "Bolzano-Bozen",            "Bolzano-Bozen / Bozen-Bolzano",
  "Massa Carrara",            "Massa-Carrara",
  "Massa-Carrara",            "Massa-Carrara",
  "Forlì-Cesena",             "Forlì-Cesena",
  "Forli'-Cesena",            "Forlì-Cesena",
  "Pesaro e Urbino",          "Pesaro e Urbino",
  "Reggio di Calabria",       "Reggio di Calabria",
  "Reggio Calabria",          "Reggio di Calabria",
  "Verbano Cusio Ossola",     "Verbano-Cusio-Ossola",
  "Verbano-Cusio-Ossola",     "Verbano-Cusio-Ossola",
  "Barletta-Andria-Trani",    "Barletta-Andria-Trani",
  "Fermo",                    "Fermo",
  "Monza e della Brianza",    "Monza e della Brianza",
  "Sud Sardegna",             "Sud Sardegna"
)

zenodo_fixed <- zenodo %>%
  left_join(name_fix, by = "province_name") %>%
  mutate(join_name = coalesce(gisco_name, province_name)) %>%
  select(join_name, gdp_pc, inst_quality)

# ── 4. Join to NUTS-3 geometries ──────────────────────────────────────────────
nuts3_joined <- nuts3 %>%
  left_join(zenodo_fixed, by = c("NAME_LATN" = "join_name"))

# Diagnostic: report any provinces that failed to join
unmatched_gisco <- nuts3_joined %>%
  filter(is.na(gdp_pc) & is.na(inst_quality)) %>%
  pull(NAME_LATN)

unmatched_zenodo <- setdiff(
  zenodo_fixed$join_name,
  nuts3$NAME_LATN
)

if (length(unmatched_gisco) > 0) {
  message("Provinces in gisco with NO Zenodo match (will be gap-filled):\n  ",
          paste(unmatched_gisco, collapse = "\n  "))
}
if (length(unmatched_zenodo) > 0) {
  message("Province names in Zenodo not found in gisco:\n  ",
          paste(unmatched_zenodo, collapse = "\n  "))
}

# Gap-fill unmatched provinces with national median (same as make_socioeconomic.R)
nuts3_final <- nuts3_joined %>%
  mutate(
    gdp_pc      = coalesce(gdp_pc,      median(gdp_pc,      na.rm = TRUE)),
    inst_quality = coalesce(inst_quality, median(inst_quality, na.rm = TRUE))
  )

# ── 5. GDP per capita raster ──────────────────────────────────────────────────
nuts3_final %>%
  select(gdp_pc) %>%
  vect() %>%
  rasterize(base_ras, field = "gdp_pc") %>%
  snap() %>%
  writeRaster(file.path(var_path, "zenodo_gdp_pc.tif"), overwrite = TRUE)

message("saved: zenodo_gdp_pc.tif")

# ── 6. Institutional quality index raster ─────────────────────────────────────
nuts3_final %>%
  select(inst_quality) %>%
  vect() %>%
  rasterize(base_ras, field = "inst_quality") %>%
  snap() %>%
  writeRaster(file.path(var_path, "zenodo_inst_quality.tif"), overwrite = TRUE)

message("saved: zenodo_inst_quality.tif")
message("Run stack.R to rebuild the predictor stack.")
