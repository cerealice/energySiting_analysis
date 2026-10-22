source("./syntax/function.R")

base_ras  <- rast("./data/processed_data/masks/Italy_base_raster.tif")
var_path  <- "./data/processed_data/variables"
italy_crs <- 3035

snap <- function(r, method = "bilinear") {
  r |> project(base_ras) |> resample(base_ras, method = method) |> mask(base_ras)
}

comuni <- giscoR::gisco_get_communes(country = "IT", year = "2016") %>%
  st_transform(italy_crs) %>%
  mutate(istat_code = str_sub(COMM_ID, -6))  # last 6 chars = ISTAT code


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
  vect() %>%
  rasterize(base_ras, field = "mean_income") %>%
  snap() %>%
  writeRaster(file.path(var_path, "svi_pov.tif"), overwrite = TRUE)

message("saved: svi_pov.tif")


# ── 2. Unemployment — ISTAT LFS provincial (NUTS-3) ──────────────────────────
# Source: Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv
# REF_AREA = 5-char NUTS-3 codes (e.g. "ITC11"). SEX = 9 (total).

unemp <- read_csv(
  "./data/raw_downloads/Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv",
  show_col_types = FALSE
) %>%
  filter(SEX == 9, nchar(REF_AREA) == 5, DATA_TYPE == "UNEM_R") %>%
  group_by(REF_AREA) %>%
  slice_max(TIME_PERIOD, n = 1) %>%
  ungroup() %>%
  select(REF_AREA, Osservazione)

giscoR::gisco_get_nuts(country = "IT", nuts_level = "3",
                       year = "2021", resolution = "03") %>%
  st_transform(italy_crs) %>%
  left_join(unemp, by = c("NUTS_ID" = "REF_AREA")) %>%
  vect() %>%
  rasterize(base_ras, field = "Osservazione") %>%
  snap() %>%
  writeRaster(file.path(var_path, "svi_unemp.tif"), overwrite = TRUE)

message("saved: svi_unemp.tif")


# ── 3. Foreign-born % — ISTAT census, municipal level ────────────────────────
# Source: Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv
# GENDER is parsed as logical ("T" → TRUE). REF_AREA = 6-digit ISTAT code for communes.
# COUNTRY_BIRTH: "WORLD" = total, "WRL_X_ITA" = born abroad.

read_csv(
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
  mutate(istat_code = REF_AREA, foreignborn_pct = foreign / total) %>%
  filter(!is.na(foreignborn_pct)) %>%
  { left_join(comuni, select(., istat_code, foreignborn_pct), by = "istat_code") } %>%
  vect() %>%
  rasterize(base_ras, field = "foreignborn_pct") %>%
  snap() %>%
  writeRaster(file.path(var_path, "svi_foreignborn.tif"), overwrite = TRUE)

message("saved: svi_foreignborn.tif")
message("Run stack.R to rebuild the predictor stack.")
