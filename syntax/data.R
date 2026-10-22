source("./syntax/function.R")

### data
load("./derived/absence.RData")   # s_ab_sf, w_ab_sf
load("./derived/location.RData")  # solar_locations, wind_locations

# suitable areas
s_roi <- rast("./derived/solar_absence_roi.tif")
w_roi <- rast("./derived/wind_absence_roi.tif")

# predictor analysis
load("./derived/model_results.RData")  # imp, solar_resamps, wind_resamps, rst_s, rst_w
s_dat <- read_csv("./derived/solar.csv") %>% mutate(treat = as.integer(treat == "X1"))
w_dat <- read_csv("./derived/wind.csv") %>% mutate(treat = as.integer(treat == "X1"))


# prediction
solar.pg.glm   <- rast("./derived/pred_logReg_s.tif")
solar.pg.lasso <- rast("./derived/pred_lasso_s.tif")
solar.pg.rf    <- rast("./derived/pred_randomForest_s.tif")
solar.pg.xg    <- rast("./derived/pred_xg_s.tif")
wind.pg.glm    <- rast("./derived/pred_logReg_w.tif")
wind.pg.lasso  <- rast("./derived/pred_lasso_w.tif")
wind.pg.rf     <- rast("./derived/pred_randomForest_w.tif")
wind.pg.xg     <- rast("./derived/pred_xg_w.tif")
results <- list(solar.pg.glm, solar.pg.lasso, solar.pg.rf, solar.pg.xg,
                wind.pg.glm,  wind.pg.lasso,  wind.pg.rf,  wind.pg.xg)

### mask prediction surface
results_masked <- list()
for(i in 1:4){ results_masked[[i]] <- mask(results[[i]], s_roi) }
for(i in 5:8){ results_masked[[i]] <- mask(results[[i]], w_roi) }

terra::writeRaster(rast(results_masked), "./derived/results_masked.tif", overwrite=TRUE)


### Italian NUTS-1 macro-regions ─────────────────────────────────────────────
# Fetch the 5 NUTS-1 boundaries (same call used in function.R for NUTS-2)
rgn <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "1",
                               year = "2021", resolution = "03") |>
  st_transform(crs = 3035) |>
  rename(region = NUTS_ID) |>
  mutate(region = recode(region,
                         "ITC" = "Nord-Ovest",
                         "ITH" = "Nord-Est",
                         "ITI" = "Centro",
                         "ITF" = "Sud",
                         "ITG" = "Isole"))

# bring into the analysis CRS used by prediction rasters
rgn_vect <- rgn %>%
  mutate(id = 1:5) %>%
  st_transform(crs = 3035) %>%
  terra::vect()

models <- c("GLM","Lasso","RF","XGBoost")

### mean probability by region ────────────────────────────────────────────────
rgn_results <- data.frame()
for(j in 1:8){

  data <- results_masked[[j]]

  res <- numeric()
  for (i in 1:length(rgn_vect)) {
    cropped_raster <- terra::crop(data, rgn_vect[i])
    masked_raster  <- mask(cropped_raster, rgn_vect[i])
    res[i] <- mean(values(masked_raster), na.rm = TRUE)
  }

  if(j %in% c(1:4)){
    tp <- rgn %>%
      st_drop_geometry() %>%
      mutate(mean  = res,
             model = models[j],
             tech  = "Solar")
  } else {
    tp <- rgn %>%
      st_drop_geometry() %>%
      mutate(mean  = res,
             model = models[j-4],
             tech  = "Wind")
  }

  rgn_results <- tp %>% rbind(rgn_results)
}


### Random-effects slope analysis ─────────────────────────────────────────────
# Recover the one-hot region columns (cols 19–23 in the zonal CSV)
# and derive a single region label before dropping the dummies.
# Italian CSV column order after zonal.R:
#   zone | tx roads sub slope pop fer unemploy foreignborn poverty (9)
#        | lulc_forest … lulc_other (8)
#        | region_nordovest … region_isole (5, cols 19–23)
#        | env cf lag | treat

sol <- s_dat %>%
  mutate(region = names(s_dat[19:23])[max.col(s_dat[19:23])]) %>%
  dplyr::select(-zone, -region_nordovest:-region_isole)

win <- w_dat %>%
  mutate(region = names(w_dat[19:23])[max.col(w_dat[19:23])]) %>%
  dplyr::select(-zone, -region_nordovest:-region_isole)


library(nlme)
RE <- function(tech){
  if(tech == "solar"){
    da          <- sol
    model1vars  <- setdiff(names(da)[c(1:20)], c("pop","tx","env"))
    fvar        <- as.formula(paste("treat ~", paste(model1vars, collapse = " + "),
                                    "+ (pop+tx+env|region)"))
  } else {
    da          <- win
    model1vars  <- setdiff(names(da)[c(1:20)], c("cf","tx","lag"))
    fvar        <- as.formula(paste("treat ~", paste(model1vars, collapse = " + "),
                                    "+ (cf+tx+lag|region)"))
  }

  fit <- glmer(fvar, family = "binomial", data = da)

  tp <- sqrt(attr(ranef(fit, condVar=T)[[1]], "postVar"))*1.96

  d <- as.data.frame(ranef(fit)$region) %>%
    tibble::rownames_to_column("region") %>%
    mutate(region = recode(region,
                           "region_nordovest" = "Nord-Ovest",
                           "region_nordest"   = "Nord-Est",
                           "region_centro"    = "Centro",
                           "region_sud"       = "Sud",
                           "region_isole"     = "Isole")) %>%
    dplyr::select(-`(Intercept)`) %>%
    gather(variable, R_effect, -region) %>%
    mutate(SE = c(tp[2,2,], tp[3,3,], tp[4,4,]))

  return(d)
}

s_d <- RE("solar") %>%
  mutate(variable = factor(variable, levels = c("pop", "tx", "env"))) %>%
  mutate(variable = recode(variable,
                           "pop" = "Population density",
                           "tx"  = "Transmission dist",
                           "env" = "Environmental score"))

w_d <- RE("wind") %>%
  mutate(variable = factor(variable, levels = c("cf", "lag", "tx"))) %>%
  mutate(variable = recode(variable,
                           "cf"  = "Capacity factor",
                           "tx"  = "Transmission dist",
                           "lag" = "Spatial lag"))

save(solar_locations, wind_locations, s_ab_sf, w_ab_sf,
     imp, solar_resamps, wind_resamps, rst_s, rst_w,
     s_dat, w_dat, rgn_results, s_d, w_d, rgn,
     file = "./derived/total.RData")
