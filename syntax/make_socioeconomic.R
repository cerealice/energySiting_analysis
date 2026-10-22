source("./syntax/function.R")

base_ras  <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path  <- "./data/processed_data/variables"
italy_crs <- 3035

snap <- function(r, method = "bilinear") {
  r |> project(base_ras) |> resample(base_ras, method = method) |> mask(base_ras)
}

comuni <- giscoR::gisco_get_communes(country = "IT", year = "2020") %>%
  st_transform(italy_crs) %>%
  mutate(istat_code = sprintf("%06d", as.integer(COMM_ID)))


# ── 1. Poverty proxy — MEF IRPEF municipality-level income ───────────────────
# File: Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.csv
# Mean taxable income per taxpayer = Reddito imponibile - Ammontare / Frequenza
# Lower income → higher poverty risk (model picks up sign from coefficient).

message("1. Poverty proxy (MEF IRPEF mean income per taxpayer)")

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

comuni_pov <- comuni %>%
  left_join(mef %>% select(istat_code, mean_income), by = "istat_code")

pov_rast <- rasterize(vect(comuni_pov), base_ras, field = "mean_income") |> snap()
writeRaster(pov_rast, file.path(var_path, "svi_pov.tif"), overwrite = TRUE)
message("  saved: svi_pov.tif")


# ── 2. Unemployment — ISTAT LFS provincial level ─────────────────────────────
# File: Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv
# REF_AREA = NUTS-3 province codes (5-char, e.g. "ITC11"). SEX=9 = total.

message("2. Unemployment rate (ISTAT LFS, provincial / NUTS-3)")

unemp <- read_csv(
  "./data/raw_downloads/Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv",
  show_col_types = FALSE
) %>%
  filter(SEX == 9,
         nchar(REF_AREA) == 5,     # NUTS-3 province codes only
         DATA_TYPE == "UNEM_R") %>%
  group_by(REF_AREA) %>%
  slice_max(TIME_PERIOD, n = 1) %>%
  ungroup() %>%
  select(REF_AREA, Osservazione)

nuts3 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "3",
                                 year = "2021", resolution = "03") %>%
  st_transform(italy_crs)

nuts3_unemp <- nuts3 %>%
  left_join(unemp, by = c("NUTS_ID" = "REF_AREA"))

unemp_rast <- rasterize(vect(nuts3_unemp), base_ras, field = "Osservazione") |> snap()
writeRaster(unemp_rast, file.path(var_path, "svi_unemp.tif"), overwrite = TRUE)
message("  saved: svi_unemp.tif")


# ── 3. Foreign-born % — ISTAT permanent census, municipality level ────────────
# File: Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv
# Structure (long format):
#   REF_AREA      = 6-digit ISTAT municipality code (e.g. "001001") for communes,
#                   or NUTS/national codes for aggregates — filter nchar == 6
#   GENDER        = "T" (total), "M", "F"
#   COUNTRY_BIRTH = "WORLD" (total), "WRL_X_ITA" (foreign-born), "IT" (Italian-born), ...
#   TIME_PERIOD   = year (2021 or 2024)
#   Osservazione  = count
# Foreign-born % = WRL_X_ITA / WORLD

message("3. Foreign-born % (ISTAT census, municipality level)")

pop <- read_csv(
  "./data/raw_downloads/Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv",
  show_col_types = FALSE
) %>%
  filter(GENDER        == "T",
         nchar(REF_AREA) == 6,          # municipality-level codes only
         COUNTRY_BIRTH %in% c("WORLD", "WRL_X_ITA")) %>%
  group_by(REF_AREA) %>%
  slice_max(TIME_PERIOD, n = 1) %>%     # keep most recent year per commune
  ungroup()

fb <- pop %>%
  pivot_wider(
    id_cols     = REF_AREA,
    names_from  = COUNTRY_BIRTH,
    values_from = Osservazione
  ) %>%
  mutate(
    istat_code     = REF_AREA,
    foreignborn_pct = WRL_X_ITA / WORLD
  ) %>%
  filter(!is.na(foreignborn_pct))

comuni_fb <- comuni %>%
  left_join(fb %>% select(istat_code, foreignborn_pct), by = "istat_code")

fb_rast <- rasterize(vect(comuni_fb), base_ras, field = "foreignborn_pct") |> snap()
writeRaster(fb_rast, file.path(var_path, "svi_foreignborn.tif"), overwrite = TRUE)
message("  saved: svi_foreignborn.tif")


message("Done. Run stack.R to rebuild the predictor stack with real socioeconomic data.")
