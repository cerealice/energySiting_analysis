source("./syntax/function.R")

base_ras  <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path  <- "./data/processed_data/variables"
italy_crs <- 3035

snap <- function(r, method = "bilinear") {
  r |> project(base_ras) |> resample(base_ras, method = method) |> mask(base_ras)
}

# ── Shared: Italian communes with ISTAT codes ─────────────────────────────────
comuni <- giscoR::gisco_get_communes(country = "IT", year = "2016") %>%
  st_transform(italy_crs) %>%
  mutate(istat_code = str_sub(COMM_ID, -6))  # last 6 chars = ISTAT code

# Assign NUTS-3 province to each municipality (centroid-based to avoid boundary issues)
nuts3_16 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "3",
                                    year = "2016", resolution = "03") %>%
  st_transform(italy_crs) %>%
  select(NUTS_ID)

comuni_prov_ids <- comuni %>%
  st_centroid() %>%
  st_join(nuts3_16, join = st_within) %>%
  st_drop_geometry() %>%
  select(istat_code, NUTS_ID)

# Augment comuni with province IDs for gap-filling below
comuni <- comuni %>% left_join(comuni_prov_ids, by = "istat_code")


# ── 1. Poverty proxy — MEF IRPEF municipal mean taxable income ────────────────
# Lower mean income → higher poverty risk.
# Source: Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.csv
# Join key: Codice Istat Comune (6-digit, zero-padded)

mef <- read_delim(
  "./data/raw_downloads/Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.csv",
  delim     = ";",
  locale    = locale(encoding = "latin1", decimal_mark = ",", grouping_mark = "."),
  show_col_types = FALSE
) %>%
  mutate(
    istat_code  = sprintf("%06d", as.integer(`Codice Istat Comune`)),
    mean_income = `Reddito imponibile - Ammontare in euro` /
                  `Reddito imponibile - Frequenza`
  ) %>%
  filter(!is.na(mean_income))

comuni %>%
  left_join(mef %>% select(istat_code, mean_income), by = "istat_code") %>%
  # Gap-fill: municipalities without tax data get their province median income
  group_by(NUTS_ID) %>%
  mutate(mean_income = coalesce(mean_income, median(mean_income, na.rm = TRUE))) %>%
  ungroup() %>%
  # Final fallback: national median for provinces with no data at all
  mutate(mean_income = coalesce(mean_income, median(mean_income, na.rm = TRUE))) %>%
  vect() %>%
  rasterize(base_ras, field = "mean_income") %>%
  snap() %>%
  writeRaster(file.path(var_path, "svi_pov.tif"), overwrite = TRUE)

message("saved: svi_pov.tif")


# ── 2. Unemployment — ISTAT LFS provincial (NUTS-3) ──────────────────────────
# Source: Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv
# REF_AREA = 5-char NUTS-3 codes. ISTAT uses a mix of NUTS 2016 (ITD*, ITE*)
# and pre-2010 codes (IT1XX). Fix: join to NUTS 2016 geometry; use NUTS 2006
# as a fallback for the ~3 legacy IT1XX codes; fill any remaining gaps with
# national average.

unemp <- read_csv(
  "./data/raw_downloads/Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv",
  show_col_types = FALSE
) %>%
  filter(SEX == 9, nchar(REF_AREA) == 5, DATA_TYPE == "UNEM_R") %>%
  group_by(REF_AREA) %>%
  slice_max(TIME_PERIOD, n = 1) %>%
  ungroup() %>%
  select(REF_AREA, Osservazione)

# Primary join: NUTS 2016 geometry (covers ITD*, ITE*, ITF*, ITG*, ITC* codes)
unemp_rast_2016 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "3",
                                           year = "2016", resolution = "03") %>%
  st_transform(italy_crs) %>%
  left_join(unemp, by = c("NUTS_ID" = "REF_AREA")) %>%
  vect() %>%
  rasterize(base_ras, field = "Osservazione") %>%
  snap()

# Fallback join: NUTS 2006 geometry (covers legacy IT1XX codes)
unemp_rast_2006 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "3",
                                           year = "2006", resolution = "03") %>%
  st_transform(italy_crs) %>%
  left_join(unemp, by = c("NUTS_ID" = "REF_AREA")) %>%
  vect() %>%
  rasterize(base_ras, field = "Osservazione") %>%
  snap()

# Merge: prefer 2016 values; fill gaps with 2006; remaining gaps → national mean
unemp_merged <- terra::merge(unemp_rast_2016, unemp_rast_2006)

nat_mean_unemp <- global(unemp_merged, "mean", na.rm = TRUE)[[1]]
unemp_final <- ifel(is.na(unemp_merged), nat_mean_unemp, unemp_merged) %>%
  mask(base_ras)

writeRaster(unemp_final, file.path(var_path, "svi_unemp.tif"), overwrite = TRUE)
message("saved: svi_unemp.tif")


# ── 3. Foreign-born % — ISTAT census, municipal level ────────────────────────
# Source: Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv
# GENDER is parsed as logical ("T" → TRUE). REF_AREA = 6-digit ISTAT code.
# COUNTRY_BIRTH: "WORLD" = total population, "WRL_X_ITA" = born abroad.

foreignborn_vals <- read_csv(
  "./data/raw_downloads/Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv",
  show_col_types = FALSE
) %>%
  filter(GENDER, nchar(REF_AREA) == 6,
         COUNTRY_BIRTH %in% c("WORLD", "WRL_X_ITA")) %>%
  group_by(REF_AREA, COUNTRY_BIRTH) %>%
  slice_max(TIME_PERIOD, n = 1, with_ties = FALSE) %>%
  ungroup() %>%
  pivot_wider(id_cols = REF_AREA, names_from = COUNTRY_BIRTH,
              values_from = Osservazione) %>%
  rename(total = WORLD, foreign = WRL_X_ITA) %>%
  mutate(istat_code = REF_AREA,
         foreignborn_pct = if_else(total > 0, foreign / total, NA_real_)) %>%
  select(istat_code, foreignborn_pct)

comuni %>%
  left_join(foreignborn_vals, by = "istat_code") %>%
  # Gap-fill: municipalities without census data get their province median
  group_by(NUTS_ID) %>%
  mutate(foreignborn_pct = coalesce(foreignborn_pct,
                                    median(foreignborn_pct, na.rm = TRUE))) %>%
  ungroup() %>%
  # Final fallback: national median
  mutate(foreignborn_pct = coalesce(foreignborn_pct,
                                    median(foreignborn_pct, na.rm = TRUE))) %>%
  vect() %>%
  rasterize(base_ras, field = "foreignborn_pct") %>%
  snap() %>%
  writeRaster(file.path(var_path, "svi_foreignborn.tif"), overwrite = TRUE)

message("saved: svi_foreignborn.tif")
message("Run stack.R to rebuild the predictor stack.")
