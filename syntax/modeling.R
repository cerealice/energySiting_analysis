source("./syntax/function.R")

## modeling
#### solar
solar.cov.existing <- read_csv("./derived/existing_cov_solar.csv")
s.bg <- read_csv("./derived/bg_cov_solar.csv")
solar.cov.bg <- s.bg %>%
  mutate(group = c(rep(seq(1,10,1), each = floor(nrow(s.bg)/10)),
                   rep(10, nrow(s.bg) %% 10)))

# Named lookup: coefficient rowname → display label.
# Using rownames_to_column() + recode() avoids hard-coded positional matching,
# so dropped variables (rank-deficient columns) don't misalign the labels.
var_labels <- c(
  "(Intercept)"        = "(Intercept)",
  # Infrastructure
  "tx"                 = "Transmission dist",
  "roads"              = "Road dist",
  "sub"                = "Substation dist",
  "slope"              = "Slope",
  "pop"                = "Population density",
  # Socioeconomic
  "unemploy"           = "Unemployment",
  "foreignborn"        = "Foreign born",
  "poverty"            = "Poverty",
  "gdp_pc"             = "GDP per capita",
  "inst_quality"       = "Institutional quality",
  # WorldClim BIO
  "wclim_bio01"        = "Annual mean temp (WC)",
  "wclim_bio02"        = "Diurnal temp range (WC)",
  "wclim_bio03"        = "Isothermality (WC)",
  "wclim_bio04"        = "Temp seasonality (WC)",
  "wclim_bio05"        = "Max temp warmest (WC)",
  "wclim_bio06"        = "Min temp coldest (WC)",
  "wclim_bio07"        = "Annual temp range (WC)",
  "wclim_bio08"        = "Temp wettest qtr (WC)",
  "wclim_bio09"        = "Temp driest qtr (WC)",
  "wclim_bio10"        = "Temp warmest qtr (WC)",
  "wclim_bio11"        = "Temp coldest qtr (WC)",
  "wclim_bio12"        = "Annual precip (WC)",
  "wclim_bio13"        = "Precip wettest mo (WC)",
  "wclim_bio14"        = "Precip driest mo (WC)",
  "wclim_bio15"        = "Precip seasonality (WC)",
  "wclim_bio16"        = "Precip wettest qtr (WC)",
  "wclim_bio17"        = "Precip driest qtr (WC)",
  "wclim_bio18"        = "Precip warmest qtr (WC)",
  "wclim_bio19"        = "Precip coldest qtr (WC)",
  # ERA5 climate
  "era5_t2m_mean"      = "Temperature mean (ERA5)",
  "era5_t2m_max"       = "Temperature max (ERA5)",
  "era5_t2m_min"       = "Temperature min (ERA5)",
  "era5_t2m_std"       = "Temperature SD (ERA5)",
  "era5_d2m_mean"      = "Dewpoint temp (ERA5)",
  "era5_tp_sum"        = "Precipitation (ERA5)",
  "era5_cp_sum"        = "Convective precip (ERA5)",
  "era5_sf_sum"        = "Snowfall (ERA5)",
  "era5_e_sum"         = "Evaporation (ERA5)",
  "era5_pev_sum"       = "Potential evap (ERA5)",
  "era5_ro_sum"        = "Runoff (ERA5)",
  "era5_u10_mean"      = "Wind U 10m (ERA5)",
  "era5_v10_mean"      = "Wind V 10m (ERA5)",
  "era5_u100_mean"     = "Wind U 100m (ERA5)",
  "era5_v100_mean"     = "Wind V 100m (ERA5)",
  "era5_i10fg_mean"    = "Wind gust (ERA5)",
  "era5_ssrd_sum"      = "Solar radiation (ERA5)",
  "era5_ssr_sum"       = "Net solar rad (ERA5)",
  "era5_cdir_sum"      = "Clear-sky direct solar (ERA5)",
  "era5_ssrdc_sum"     = "Clear-sky solar down (ERA5)",
  "era5_tcc_mean"      = "Cloud cover (ERA5)",
  "era5_blh_mean"      = "Boundary layer H (ERA5)",
  "era5_sp_mean"       = "Surface pressure (ERA5)",
  "era5_cape_mean"     = "CAPE (ERA5)",
  # LUH3 land use
  "luh3_primf"         = "Primary forest (LUH3)",
  "luh3_primn"         = "Primary non-forest (LUH3)",
  "luh3_secdf"         = "Secondary forest (LUH3)",
  "luh3_secdn"         = "Secondary non-forest (LUH3)",
  "luh3_pastr"         = "Pasture (LUH3)",
  "luh3_range"         = "Rangeland (LUH3)",
  "luh3_urban"         = "Urban (LUH3)",
  "luh3_c3ann"         = "C3 annual crops (LUH3)",
  "luh3_c4ann"         = "C4 annual crops (LUH3)",
  "luh3_c3per"         = "C3 perennial crops (LUH3)",
  "luh3_c4per"         = "C4 perennial crops (LUH3)",
  "luh3_c3nfx"         = "N-fixing crops (LUH3)",
  # NDVI
  "wt_ndvi_mean"       = "NDVI (MODIS)",
  # CORINE LULC
  "lulc_forest"        = "Forest",
  "lulc_grassland"     = "Grassland",
  "lulc_shrubland"     = "Shrubland",
  "lulc_riparian"      = "Riparian",
  "lulc_sparse"        = "Vegetated",
  "lulc_agriculture"   = "Agriculture",
  "lulc_developed"     = "Developed",
  # lulc_other omitted — reference class
  # NUTS-2 regions (aggregated to NUTS-1 in plot.R Figure 2)
  "nuts2_itc1" = "Nord-Ovest", "nuts2_itc2" = "Nord-Ovest",
  "nuts2_itc3" = "Nord-Ovest", "nuts2_itc4" = "Nord-Ovest",
  "nuts2_ith1" = "Nord-Est",   "nuts2_ith2" = "Nord-Est",
  "nuts2_ith3" = "Nord-Est",   "nuts2_ith4" = "Nord-Est",   "nuts2_ith5" = "Nord-Est",
  "nuts2_iti1" = "Centro",     "nuts2_iti2" = "Centro",
  "nuts2_iti3" = "Centro",     "nuts2_iti4" = "Centro",
  "nuts2_itf1" = "Sud",        "nuts2_itf2" = "Sud",
  "nuts2_itf3" = "Sud",        "nuts2_itf4" = "Sud",
  "nuts2_itf5" = "Sud",        "nuts2_itf6" = "Sud",
  "nuts2_itg1" = "Sicilia",
  "env"                = "Environmental score",
  "cf"                 = "Capacity factor",
  "lag"                = "Spatial lag"
)

# region_model is defined once in function.R (sourced above).
# Redefined here only to keep the collinearity note visible alongside the models.
# NOTE: ~90 predictors total. GLM/LASSO may have collinearity warnings — this is
# expected with highly correlated climate variables. GBM, RF, and NN are unaffected.
region_model <- treat ~
  # Infrastructure & demographics
  tx + roads + sub + slope + pop +
  # Socioeconomic
  unemploy + foreignborn + poverty + gdp_pc + inst_quality +
  # WorldClim BIO1-BIO19
  wclim_bio01 + wclim_bio02 + wclim_bio03 + wclim_bio04 + wclim_bio05 +
  wclim_bio06 + wclim_bio07 + wclim_bio08 + wclim_bio09 + wclim_bio10 +
  wclim_bio11 + wclim_bio12 + wclim_bio13 + wclim_bio14 + wclim_bio15 +
  wclim_bio16 + wclim_bio17 + wclim_bio18 + wclim_bio19 +
  # ERA5 climate (annual means 2000-2020)
  era5_t2m_mean + era5_t2m_max + era5_t2m_min + era5_t2m_std +
  era5_d2m_mean +
  era5_tp_sum + era5_cp_sum + era5_sf_sum +
  era5_e_sum + era5_pev_sum + era5_ro_sum +
  era5_u10_mean + era5_v10_mean + era5_u100_mean + era5_v100_mean + era5_i10fg_mean +
  era5_ssrd_sum + era5_ssr_sum + era5_cdir_sum + era5_ssrdc_sum +
  era5_tcc_mean + era5_blh_mean + era5_sp_mean + era5_cape_mean +
  # LUH3 land-use states 2020
  luh3_primf + luh3_primn + luh3_secdf + luh3_secdn +
  luh3_pastr + luh3_range + luh3_urban +
  luh3_c3ann + luh3_c4ann + luh3_c3per + luh3_c4per + luh3_c3nfx +
  # MODIS NDVI
  wt_ndvi_mean +
  # CORINE land cover (lulc_other omitted — reference)
  lulc_forest + lulc_grassland + lulc_shrubland + lulc_riparian +
  lulc_sparse + lulc_agriculture + lulc_developed +
  # NUTS-2 regions (nuts2_itg2 omitted — reference: Sardegna)
  nuts2_itc1 + nuts2_itc2 + nuts2_itc3 + nuts2_itc4 +
  nuts2_ith1 + nuts2_ith2 + nuts2_ith3 + nuts2_ith4 + nuts2_ith5 +
  nuts2_iti1 + nuts2_iti2 + nuts2_iti3 + nuts2_iti4 +
  nuts2_itf1 + nuts2_itf2 + nuts2_itf3 + nuts2_itf4 + nuts2_itf5 + nuts2_itf6 +
  nuts2_itg1 +
  # Technology-specific
  env + cf + lag


# ── NA imputation ─────────────────────────────────────────────────────────────
# LUH3 land-use fractions: NA from raster masking means no coverage → 0
# (a fraction of 0 is scientifically valid; NaN in LUH3 for Italy = absent type)
# All other numerics: edge-cell NAs from WorldClim/ERA5 downscaling → column median
impute_dat <- function(df) {
  df %>%
    mutate(across(starts_with("luh3_"), ~replace_na(., 0))) %>%
    mutate(across(where(is.numeric), ~replace_na(., median(., na.rm = TRUE))))
}

# Derive NUTS-1 macro-region factor from the 20 binary NUTS-2 columns.
# Reference level = "Isole" (Sicilia + Sardegna) — smallest renewable share,
# matches the omitted nuts2_itg2 reference used previously.
add_nuts1 <- function(df) {
  df %>% mutate(nuts1 = factor(
    case_when(
      nuts2_itc1 == 1 | nuts2_itc2 == 1 | nuts2_itc3 == 1 | nuts2_itc4 == 1 ~ "Nord-Ovest",
      nuts2_ith1 == 1 | nuts2_ith2 == 1 | nuts2_ith3 == 1 | nuts2_ith4 == 1 | nuts2_ith5 == 1 ~ "Nord-Est",
      nuts2_iti1 == 1 | nuts2_iti2 == 1 | nuts2_iti3 == 1 | nuts2_iti4 == 1 ~ "Centro",
      nuts2_itf1 == 1 | nuts2_itf2 == 1 | nuts2_itf3 == 1 | nuts2_itf4 == 1 |
        nuts2_itf5 == 1 | nuts2_itf6 == 1 ~ "Sud",
      TRUE ~ "Isole"
    ),
    levels = c("Isole", "Nord-Ovest", "Nord-Est", "Centro", "Sud")
  ))
}

### combined
rst_s <- data.frame()
aic <- c()
for(i in 1:10){
  s_dat <- solar.cov.bg %>%
    filter(group == i) %>%
    dplyr::select(-group) %>%
    rbind(solar.cov.existing) %>%
    mutate(treat = factor(treat)) %>%
    impute_dat() %>%
    mutate(treat = factor(make.names(treat)))

  if (nrow(s_dat) == 0 || length(levels(s_dat$treat)) < 2) {
    raw <- solar.cov.bg %>% filter(group == i) %>% select(-group) %>% rbind(solar.cov.existing)
    na_cols <- sort(colSums(is.na(raw)), decreasing = TRUE)
    na_cols <- na_cols[na_cols > 0]
    stop(sprintf("Solar group %d: na.omit() removed all rows. Columns with NAs:\n%s",
                 i, paste(sprintf("  %-25s %d", names(na_cols), na_cols), collapse = "\n")))
  }

  glm1_solar <- glm(region_model, data = s_dat, family = binomial(link = "logit"))

  tp <- summary(glm1_solar)$coefficients %>%
    as.data.frame() %>%
    rownames_to_column("var") %>%
    mutate(var   = recode(var, !!!var_labels),
           color = ifelse(`Pr(>|z|)` < 0.05, "Y", "N")) %>%
    dplyr::select(-"z value", -"Pr(>|z|)") %>%
    filter(var != "(Intercept)") %>%
    rename(se = "Std. Error", pe = Estimate) %>%
    mutate(Group = i)

  rst_s <- tp %>%
    rbind(rst_s)

  aic[i] <- glm1_solar$aic

}


s_dat <- solar.cov.bg %>%
  filter(group == which(aic == sort(aic)[5])) %>%
  dplyr::select(-group) %>%
  rbind(solar.cov.existing) %>%
  mutate(treat = factor(treat)) %>%
  impute_dat() %>%
  mutate(treat = factor(make.names(treat)))   # "0"/"1" → "X0"/"X1" (valid R names for caret)

write.csv(s_dat, "./derived/solar.csv", row.names = FALSE)


glm1_solar <- glm(region_model, data = s_dat, family = binomial(link = "logit"))


solar.pg <- predict(object = solar_future, model = glm1_solar, type = "response", ext=extent(solar_future))
writeRaster(solar.pg, "./derived/pred_logReg_s.tif", overwrite=TRUE)


### ML
tc_kfold <- trainControl(method = "cv", number = 10, returnResamp="all",
                         savePredictions = TRUE, classProbs = TRUE,
                         summaryFunction = twoClassSummary)


# ### GLM
mdl_solarglm <- train(form = region_model, data=s_dat, method = "glm",
                      trControl = tc_kfold,
                      na.action=na.omit,
                      family = 'binomial')

varimp_solarglm <- varImp(mdl_solarglm)
# solar.pg.glm <- predict(object = solar_future, mdl_solarglm, type = "prob", ext=extent(solar_future), progress='text', index=2)
# writeRaster(solar.pg.glm, "./derived/pred_logReg_ML_s.tif", overwrite=TRUE)


### lasso
lambda <- 10^seq(-3, 3, length = 100)
mdl_solarlasso <- train(form = region_model, data=s_dat, method = "glmnet",
                        trControl = tc_kfold,
                        tuneGrid = expand.grid(alpha = 1, lambda = lambda),
                        na.action=na.omit)

varimp_solarlasso <- varImp(mdl_solarlasso)
solar.pg.lasso <- predict(object = solar_future, mdl_solarlasso, type = "prob", ext=extent(solar_future), progress='text', index=2)
writeRaster(solar.pg.lasso, "./derived/pred_lasso_s.tif", overwrite=TRUE)

#### GBM (replaces xgbTree: caret's xgbTree is incompatible with xgboost >= 2.0)
librarian::shelf("gbm")
tune_grid <- expand.grid(
  n.trees           = c(50, 100),
  interaction.depth = c(3, 6),
  shrinkage         = c(0.01, 0.1),
  n.minobsinnode    = c(5, 10)
)

mdl_solarxg = train(form = region_model, data=s_dat,
                    method="gbm", trControl = tc_kfold,
                    tuneGrid = tune_grid,
                    na.action = na.omit,
                    verbose = FALSE)

varimp_solarxg <- varImp(mdl_solarxg)
solar.pg.xg <- predict(object = solar_future, mdl_solarxg, type = "prob", ext=extent(solar_future), progress='text', index=2)
writeRaster(solar.pg.xg, "./derived/pred_xg_s.tif", overwrite=TRUE)


#### RF
mdl_solarrf = train(form = region_model, data=s_dat,
                    metric = "ROC",
                    method = "rf", trControl = tc_kfold,
                    na.action = na.omit,
                    importance = TRUE)

varimp_solarrf <- varImp(mdl_solarrf)
solar.pg.rf <- predict(object = solar_future, mdl_solarrf, type = "prob", ext=extent(solar_future), progress='text', index=2)
writeRaster(solar.pg.rf, "./derived/pred_randomForest_s.tif", overwrite=TRUE)


#### Neural network
librarian::shelf("nnet")
tune_nn <- expand.grid(size = c(5, 10, 20), decay = c(0.001, 0.01, 0.1))

mdl_solarnn <- train(form = region_model, data = s_dat,
                     method = "nnet",
                     trControl = tc_kfold,
                     tuneGrid = tune_nn,
                     preProcess = c("center", "scale"),
                     na.action = na.omit,
                     MaxNWts = 5000,
                     trace = FALSE)

varimp_solarnn <- varImp(mdl_solarnn)
solar.pg.nn <- predict(object = solar_future, mdl_solarnn, type = "prob",
                       ext = extent(solar_future), progress = 'text', index = 2)
writeRaster(solar.pg.nn, "./derived/pred_nn_s.tif", overwrite = TRUE)


### summary
solarmodel_list <- list(
  glm   = mdl_solarglm,
  lasso = mdl_solarlasso,
  xg    = mdl_solarxg,
  rf    = mdl_solarrf,
  nn    = mdl_solarnn
)

solar_resamps <- resamples(solarmodel_list)


### wind
wind.cov.existing <- read_csv("./derived/existing_cov_wind.csv")
w.bg <- read_csv("./derived/bg_cov_wind.csv")
wind.cov.bg <- w.bg %>%
  mutate(group = c(rep(seq(1,10,1), each = floor(nrow(w.bg)/10)),
                   rep(10, nrow(w.bg) %% 10)))


### combined
rst_w <- data.frame()
aic <- c()
for(i in 1:10){
  w_dat <- wind.cov.bg %>%
    filter(group == i) %>%
    dplyr::select(-group) %>%
    rbind(wind.cov.existing) %>%
    mutate(treat = factor(treat)) %>%
    impute_dat() %>%
    mutate(treat = factor(make.names(treat)))

  if (nrow(w_dat) == 0 || length(levels(w_dat$treat)) < 2) {
    raw <- wind.cov.bg %>% filter(group == i) %>% select(-group) %>% rbind(wind.cov.existing)
    na_cols <- sort(colSums(is.na(raw)), decreasing = TRUE)
    na_cols <- na_cols[na_cols > 0]
    stop(sprintf("Wind group %d: na.omit() removed all rows. Columns with NAs:\n%s",
                 i, paste(sprintf("  %-25s %d", names(na_cols), na_cols), collapse = "\n")))
  }

  glm1_wind <- glm(region_model, data = w_dat, family = binomial(link = "logit"))

  tp <- summary(glm1_wind)$coefficients %>%
    as.data.frame() %>%
    rownames_to_column("var") %>%
    mutate(var   = recode(var, !!!var_labels),
           color = ifelse(`Pr(>|z|)` < 0.05, "Y", "N")) %>%
    dplyr::select(-"z value", -"Pr(>|z|)") %>%
    filter(var != "(Intercept)") %>%
    rename(se = "Std. Error", pe = Estimate) %>%
    mutate(Group = i)

  rst_w <- tp %>%
    rbind(rst_w)

  aic[i] <- glm1_wind$aic

}


w_dat <- wind.cov.bg %>%
  filter(group == which(aic == sort(aic)[5])) %>%
  dplyr::select(-group) %>%
  rbind(wind.cov.existing) %>%
  mutate(treat = factor(treat)) %>%
  impute_dat() %>%
  mutate(treat = factor(make.names(treat)))   # "0"/"1" → "X0"/"X1"

write.csv(w_dat, "./derived/wind.csv", row.names = FALSE)


glm1_wind <- glm(region_model, data = w_dat, family = binomial(link = "logit"))


wind.pg <- predict(object = wind_future, model = glm1_wind, type = "response", ext=extent(wind_future))
writeRaster(wind.pg, "./derived/pred_logReg_w.tif", overwrite=TRUE)


# ### GLM
mdl_windglm <- train(form = region_model, data=w_dat, method = "glm",
                      trControl = tc_kfold,
                      na.action=na.omit,
                      family = 'binomial')

varimp_windglm <- varImp(mdl_windglm)
# wind.pg.glm <- predict(object = wind_future, mdl_windglm, type = "prob", ext=extent(wind_future), progress='text', index=2)
# writeRaster(wind.pg.glm, "./derived/pred_logReg_ML_s.tif", overwrite=TRUE)


### lasso
lambda <- 10^seq(-3, 3, length = 100)
mdl_windlasso <- train(form = region_model, data=w_dat, method = "glmnet",
                        trControl = tc_kfold,
                        tuneGrid = expand.grid(alpha = 1, lambda = lambda),
                        na.action=na.omit)

varimp_windlasso <- varImp(mdl_windlasso)
wind.pg.lasso <- predict(object = wind_future, mdl_windlasso, type = "prob", ext=extent(wind_future), progress='text', index=2)
writeRaster(wind.pg.lasso, "./derived/pred_lasso_w.tif", overwrite=TRUE)

#### GBM (replaces xgbTree: caret's xgbTree is incompatible with xgboost >= 2.0)
tune_grid <- expand.grid(
  n.trees           = c(50, 100),
  interaction.depth = c(3, 6),
  shrinkage         = c(0.01, 0.1),
  n.minobsinnode    = c(5, 10)
)

mdl_windxg = train(form = region_model, data=w_dat,
                    method="gbm", trControl = tc_kfold,
                    tuneGrid = tune_grid,
                    na.action = na.omit,
                    verbose = FALSE)

varimp_windxg <- varImp(mdl_windxg)
wind.pg.xg <- predict(object = wind_future, mdl_windxg, type = "prob", ext=extent(wind_future), progress='text', index=2)
writeRaster(wind.pg.xg, "./derived/pred_xg_w.tif", overwrite=TRUE)


#### RF
mdl_windrf = train(form = region_model, data=w_dat,
                    metric = "ROC",
                    method = "rf", trControl = tc_kfold,
                    na.action = na.omit,
                    importance = TRUE)

varimp_windrf <- varImp(mdl_windrf)
wind.pg.rf <- predict(object = wind_future, mdl_windrf, type = "prob", ext=extent(wind_future), progress='text', index=2)
writeRaster(wind.pg.rf, "./derived/pred_randomForest_w.tif", overwrite=TRUE)


#### Neural network
mdl_windnn <- train(form = region_model, data = w_dat,
                    method = "nnet",
                    trControl = tc_kfold,
                    tuneGrid = tune_nn,
                    preProcess = c("center", "scale"),
                    na.action = na.omit,
                    MaxNWts = 5000,
                    trace = FALSE)

varimp_windnn <- varImp(mdl_windnn)
wind.pg.nn <- predict(object = wind_future, mdl_windnn, type = "prob",
                      ext = extent(wind_future), progress = 'text', index = 2)
writeRaster(wind.pg.nn, "./derived/pred_nn_w.tif", overwrite = TRUE)


### summary
windmodel_list <- list(
  glm   = mdl_windglm,
  lasso = mdl_windlasso,
  xg    = mdl_windxg,
  rf    = mdl_windrf,
  nn    = mdl_windnn
)

wind_resamps <- resamples(windmodel_list)



imp <- rbind(
  varimp_windrf[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    dplyr::select(-X0) %>%
    mutate(model = "RF",
           tech = "Wind") %>%
    rename(Overall = X1),
  varimp_windxg[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "GBM",
           tech = "Wind"),
  varimp_windlasso[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "Lasso",
           tech = "Wind"),
  varimp_windglm[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "GLM",
           tech = "Wind"),
  varimp_windnn[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "NN",
           tech = "Wind"),

  varimp_solarrf[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    dplyr::select(-X0) %>%
    mutate(model = "RF",
           tech = "Solar") %>%
    rename(Overall = X1),
  varimp_solarxg[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "GBM",
           tech = "Solar"),
  varimp_solarlasso[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "Lasso",
           tech = "Solar"),
  varimp_solarglm[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "GLM",
           tech = "Solar"),
  varimp_solarnn[[1]] %>%
    as.data.frame() %>%
    rownames_to_column() %>%
    mutate(model = "NN",
           tech = "Solar")
) %>%
  mutate(rowname = recode(
    rowname,
    "tx"             = "Transmission dist",
    "roads"          = "Road dist",
    "sub"            = "Substation dist",
    "slope"          = "Slope",
    "pop"            = "Population density",
    # "fer"          = "FER incentive",   # excluded — constant across Italy
    "unemploy"       = "Unemployment",
    "foreignborn"    = "Foreign born",
    "poverty"        = "Poverty",
    "gdp_pc"         = "GDP per capita",
    "inst_quality"   = "Institutional quality",
    "lulc_forest"       = "Forest",
    "lulc_grassland"    = "Grassland",
    "lulc_shrubland"    = "Shrubland",
    "lulc_riparian"     = "Riparian",
    "lulc_sparse"       = "Sparsely vegetated",
    "lulc_agriculture"  = "Agriculture",
    "lulc_developed"    = "Developed",
    "lulc_other"        = "Otherland",
    # WorldClim BIO
    "wclim_bio01"       = "Annual mean temp (WC)",
    "wclim_bio02"       = "Diurnal temp range (WC)",
    "wclim_bio03"       = "Isothermality (WC)",
    "wclim_bio04"       = "Temp seasonality (WC)",
    "wclim_bio05"       = "Max temp warmest (WC)",
    "wclim_bio06"       = "Min temp coldest (WC)",
    "wclim_bio07"       = "Annual temp range (WC)",
    "wclim_bio08"       = "Temp wettest qtr (WC)",
    "wclim_bio09"       = "Temp driest qtr (WC)",
    "wclim_bio10"       = "Temp warmest qtr (WC)",
    "wclim_bio11"       = "Temp coldest qtr (WC)",
    "wclim_bio12"       = "Annual precip (WC)",
    "wclim_bio13"       = "Precip wettest mo (WC)",
    "wclim_bio14"       = "Precip driest mo (WC)",
    "wclim_bio15"       = "Precip seasonality (WC)",
    "wclim_bio16"       = "Precip wettest qtr (WC)",
    "wclim_bio17"       = "Precip driest qtr (WC)",
    "wclim_bio18"       = "Precip warmest qtr (WC)",
    "wclim_bio19"       = "Precip coldest qtr (WC)",
    # ERA5 climate
    "era5_t2m_mean"     = "Temperature mean (ERA5)",
    "era5_t2m_max"      = "Temperature max (ERA5)",
    "era5_t2m_min"      = "Temperature min (ERA5)",
    "era5_t2m_std"      = "Temperature SD (ERA5)",
    "era5_d2m_mean"     = "Dewpoint temp (ERA5)",
    "era5_tp_sum"       = "Precipitation (ERA5)",
    "era5_cp_sum"       = "Convective precip (ERA5)",
    "era5_sf_sum"       = "Snowfall (ERA5)",
    "era5_e_sum"        = "Evaporation (ERA5)",
    "era5_pev_sum"      = "Potential evap (ERA5)",
    "era5_ro_sum"       = "Runoff (ERA5)",
    "era5_u10_mean"     = "Wind U 10m (ERA5)",
    "era5_v10_mean"     = "Wind V 10m (ERA5)",
    "era5_u100_mean"    = "Wind U 100m (ERA5)",
    "era5_v100_mean"    = "Wind V 100m (ERA5)",
    "era5_i10fg_mean"   = "Wind gust (ERA5)",
    "era5_ssrd_sum"     = "Solar radiation (ERA5)",
    "era5_ssr_sum"      = "Net solar rad (ERA5)",
    "era5_cdir_sum"     = "Clear-sky direct solar (ERA5)",
    "era5_ssrdc_sum"    = "Clear-sky solar down (ERA5)",
    "era5_tcc_mean"     = "Cloud cover (ERA5)",
    "era5_blh_mean"     = "Boundary layer H (ERA5)",
    "era5_sp_mean"      = "Surface pressure (ERA5)",
    "era5_cape_mean"    = "CAPE (ERA5)",
    # LUH3 land use
    "luh3_primf"        = "Primary forest (LUH3)",
    "luh3_primn"        = "Primary non-forest (LUH3)",
    "luh3_secdf"        = "Secondary forest (LUH3)",
    "luh3_secdn"        = "Secondary non-forest (LUH3)",
    "luh3_pastr"        = "Pasture (LUH3)",
    "luh3_range"        = "Rangeland (LUH3)",
    "luh3_urban"        = "Urban (LUH3)",
    "luh3_c3ann"        = "C3 annual crops (LUH3)",
    "luh3_c4ann"        = "C4 annual crops (LUH3)",
    "luh3_c3per"        = "C3 perennial crops (LUH3)",
    "luh3_c4per"        = "C4 perennial crops (LUH3)",
    "luh3_c3nfx"        = "N-fixing crops (LUH3)",
    # NDVI
    "wt_ndvi_mean"      = "NDVI (MODIS)",
    "nuts2_itc1"        = "Piemonte",
    "nuts2_itc2"        = "Valle d'Aosta",
    "nuts2_itc3"        = "Liguria",
    "nuts2_itc4"        = "Lombardia",
    "nuts2_ith1"        = "PA Bolzano",
    "nuts2_ith2"        = "PA Trento",
    "nuts2_ith3"        = "Veneto",
    "nuts2_ith4"        = "Friuli-VG",
    "nuts2_ith5"        = "Emilia-Romagna",
    "nuts2_iti1"        = "Toscana",
    "nuts2_iti2"        = "Umbria",
    "nuts2_iti3"        = "Marche",
    "nuts2_iti4"        = "Lazio",
    "nuts2_itf1"        = "Abruzzo",
    "nuts2_itf2"        = "Molise",
    "nuts2_itf3"        = "Campania",
    "nuts2_itf4"        = "Puglia",
    "nuts2_itf5"        = "Basilicata",
    "nuts2_itf6"        = "Calabria",
    "nuts2_itg1"        = "Sicilia",
    "env"            = "Environmental score",
    "cf"             = "Capacity factor",
    "lag"            = "Spatial lag"
  ))

save(imp, solar_resamps, wind_resamps, rst_s, rst_w, file = "./derived/model_results.RData")
load("./derived/model_results.RData")

# Save model objects for calibration, spatial CV, and threshold metrics in performance.R
saveRDS(mdl_solarglm,   "./derived/mdl_solarglm.rds")
saveRDS(mdl_solarlasso, "./derived/mdl_solarlasso.rds")
saveRDS(mdl_solarrf,    "./derived/mdl_solarrf.rds")
saveRDS(mdl_solarxg,    "./derived/mdl_solarxg.rds")
saveRDS(mdl_solarnn,    "./derived/mdl_solarnn.rds")
saveRDS(mdl_windglm,    "./derived/mdl_windglm.rds")
saveRDS(mdl_windlasso,  "./derived/mdl_windlasso.rds")
saveRDS(mdl_windrf,     "./derived/mdl_windrf.rds")
saveRDS(mdl_windxg,     "./derived/mdl_windxg.rds")
saveRDS(mdl_windnn,     "./derived/mdl_windnn.rds")
