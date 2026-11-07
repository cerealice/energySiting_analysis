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

models <- c("GLM","Lasso","RF","GBM")

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
# Use NUTS-2 (21 regions) as the GLMM grouping variable.
# The 5 NUTS-1 macro-regions are too few for stable random-slope estimation
# (need ~7+ groups per variance parameter). NUTS-2 is also the stratification
# unit used in absence.R, so the grouping is consistent throughout.
#
# NUTS-2 is recovered via spatial join — no changes needed to upstream scripts.
# Absence zone IDs map to s_ab_sf$id; presence zone IDs map to unique_id in
# solar/wind_locations (which already carries state_code = NUTS-2 name).

nuts2_sf <- region_boundaries %>% select(NUTS_NAME)

s_ab_nuts2 <- s_ab_sf %>%
  st_centroid() %>%
  st_transform(st_crs(nuts2_sf)) %>%
  st_join(nuts2_sf, join = st_within) %>%
  st_drop_geometry() %>%
  select(id, nuts2 = NUTS_NAME)

w_ab_nuts2 <- w_ab_sf %>%
  st_centroid() %>%
  st_transform(st_crs(nuts2_sf)) %>%
  st_join(nuts2_sf, join = st_within) %>%
  st_drop_geometry() %>%
  select(id, nuts2 = NUTS_NAME)

s_pres_nuts2 <- solar_locations %>% st_drop_geometry() %>%
  transmute(unique_id, nuts2 = state_code)
w_pres_nuts2 <- wind_locations %>% st_drop_geometry() %>%
  transmute(unique_id, nuts2 = state_code)

assign_nuts2 <- function(dat, ab_lut, pres_lut) {
  bind_rows(
    dat %>% filter(treat == 0) %>% left_join(ab_lut,   by = c("zone" = "id")),
    dat %>% filter(treat == 1) %>% left_join(pres_lut, by = c("zone" = "unique_id"))
  )
}

s_dat <- assign_nuts2(s_dat, s_ab_nuts2, s_pres_nuts2)
w_dat <- assign_nuts2(w_dat, w_ab_nuts2, w_pres_nuts2)

rgn_cols <- grep("^region_", names(s_dat), value = TRUE)

sol <- s_dat %>%
  dplyr::select(-zone, -all_of(rgn_cols)) %>%
  rename(region = nuts2)

win <- w_dat %>%
  dplyr::select(-zone, -all_of(rgn_cols)) %>%
  rename(region = nuts2)


RE <- function(tech) {
  # With 21 NUTS-2 regions, the joint 3-slope model is identifiable.
  # Each (rv | region) adds 3 covariance parameters; 21 groups / 3 params = 7,
  # well above the minimum. bobyqa is retained for numerical stability.
  if (tech == "solar") {
    da      <- sol
    rv_vars <- c("pop", "tx", "env")
  } else {
    da      <- win
    rv_vars <- c("cf", "tx", "lag")
  }

  fixed_vars <- setdiff(names(da), c("treat", "region"))

  # The GLMM is used only for regional heterogeneity, not the main result.
  # Strategy for numerical stability:
  #   1. Use only the top-8 RF predictors as fixed effects (avoids collinearity
  #      from binary LULC dummies with near-zero variance within some regions)
  #   2. Use nAGQ = 0 (Laplace approximation, skips the PIRLS step that fails)
  #   3. Try slope model; if singular, fall back to intercept-only
  #   4. If all fail, return stratified per-region GLM coefficients

  # Top predictors from RF (drop region dummies and low-importance binary LULC)
  core_vars <- intersect(
    c("cf", "tx", "sub", "lag", "env", "slope", "pop", "gdp_pc",
      "unemploy", "inst_quality", "roads", "poverty"),
    fixed_vars
  )

  # --- helper: try multiple optimizers, return first non-singular fit ----------
  try_glmer <- function(formula, da) {
    opts <- c("bobyqa", "Nelder_Mead", "nlminbwrap")
    for (opt in opts) {
      fit <- tryCatch(
        suppressWarnings(
          glmer(formula, family = binomial, data = da, nAGQ = 0,
                control = glmerControl(optimizer = opt,
                                       optCtrl   = list(maxfun = 3e5)))
        ),
        error = function(e) NULL
      )
      if (!is.null(fit) && !isSingular(fit)) return(fit)
    }
    # return last fit even if singular rather than NULL
    fit
  }

  # --- helper: stratified per-region GLM as a fallback -------------------------
  stratified_glm <- function(da, rv) {
    core_f <- as.formula(paste("treat ~", paste(core_vars, collapse = " + ")))
    bind_rows(lapply(split(da, da$region), function(sub) {
      if (nrow(sub) < 15 || length(unique(sub$treat)) < 2) return(NULL)
      fit <- tryCatch(glm(core_f, family = binomial, data = sub), error = function(e) NULL)
      if (is.null(fit) || !rv %in% names(coef(fit))) return(NULL)
      se_tbl <- tryCatch(summary(fit)$coefficients, error = function(e) NULL)
      if (is.null(se_tbl) || !rv %in% rownames(se_tbl)) return(NULL)
      data.frame(region     = sub$region[1],
                 variable   = rv,
                 R_effect   = se_tbl[rv, "Estimate"],
                 SE         = se_tbl[rv, "Std. Error"] * 1.96,
                 model_type = "stratified")
    }))
  }

  # --- wind: try joint 3-slope GLMM before fitting slopes individually ---------
  # (cf + tx + lag | region) adds 4 RE per group; with 21 NUTS-2 regions this
  # is identifiable.  Fall through to per-variable fitting if it is singular.
  if (tech == "wind") {
    f_joint <- as.formula(paste(
      "treat ~", paste(core_vars, collapse = " + "),
      paste0("+ (", paste(rv_vars, collapse = " + "), " | region)")
    ))
    fit_joint <- try_glmer(f_joint, da)

    if (!is.null(fit_joint) && !isSingular(fit_joint)) {
      message("  [RE] Joint 3-slope GLMM converged for wind")
      re <- ranef(fit_joint)$region
      pv <- attr(ranef(fit_joint, condVar = TRUE)[[1]], "postVar")
      # postVar slice order: 1 = (Intercept), 2 = cf, 3 = tx, 4 = lag
      d_joint <- lapply(seq_along(rv_vars), function(k) {
        rv <- rv_vars[k]
        data.frame(region     = rownames(re),
                   variable   = rv,
                   R_effect   = re[[rv]],
                   SE         = sqrt(pv[k + 1L, k + 1L, ]) * 1.96,
                   model_type = "slope")
      })
      return(bind_rows(d_joint))
    }
    message("  [RE] Joint 3-slope GLMM singular for wind — fitting slopes individually")
  }

  # --- per-variable slope fitting (solar always; wind if joint failed) ---------
  d_list <- lapply(rv_vars, function(rv) {

    f_slope <- as.formula(paste(
      "treat ~", paste(core_vars, collapse = " + "),
      paste0("+ (", rv, " | region)")
    ))
    f_int <- as.formula(paste(
      "treat ~", paste(core_vars, collapse = " + "), "+ (1 | region)"
    ))

    fit <- try_glmer(f_slope, da)

    # Fall back to intercept model if slope is singular
    if (is.null(fit) || isSingular(fit)) {
      message(sprintf(
        "  [RE] Slope (%s | region) singular for %s — trying (1 | region)", rv, tech
      ))
      fit <- try_glmer(f_int, da)

      # Last resort: stratified GLM
      if (is.null(fit) || isSingular(fit)) {
        message(sprintf(
          "  [RE] GLMM singular for %s / %s — using stratified per-region GLM", tech, rv
        ))
        return(stratified_glm(da, rv))
      }

      # Intercept-only GLMM: RE = regional baseline shift, not a slope
      re <- ranef(fit)$region
      pv <- attr(ranef(fit, condVar = TRUE)[[1]], "postVar")
      return(data.frame(
        region     = rownames(re),
        variable   = rv,
        R_effect   = re[["(Intercept)"]],
        SE         = sqrt(pv[1L, 1L, ]) * 1.96,
        model_type = "intercept"
      ))
    }

    # Slope GLMM succeeded
    re     <- ranef(fit)$region
    pv     <- attr(ranef(fit, condVar = TRUE)[[1]], "postVar")
    re_col <- if (rv %in% names(re)) rv else "(Intercept)"
    se_idx <- if (rv %in% names(re)) 2L else 1L

    data.frame(
      region     = rownames(re),
      variable   = rv,
      R_effect   = re[[re_col]],
      SE         = sqrt(pv[se_idx, se_idx, ]) * 1.96,
      model_type = "slope"
    )
  })

  bind_rows(d_list)
}

# panel_label = variable name for slope models; appends "(intercept only)" or
# "(per-region GLM)" so plot.R can annotate figure 4 facet strips correctly.
make_panel_label <- function(d) {
  d %>% mutate(panel_label = case_when(
    model_type == "intercept"  ~ paste0(variable, "\n(intercept only)"),
    model_type == "stratified" ~ paste0(variable, "\n(per-region GLM)"),
    TRUE                       ~ as.character(variable)
  ))
}

s_d <- RE("solar") %>%
  mutate(variable = factor(variable, levels = c("pop", "tx", "env"))) %>%
  mutate(variable = recode(variable,
                           "pop" = "Population density",
                           "tx"  = "Transmission dist",
                           "env" = "Environmental score")) %>%
  make_panel_label()

w_d <- RE("wind") %>%
  mutate(variable = factor(variable, levels = c("cf", "lag", "tx"))) %>%
  mutate(variable = recode(variable,
                           "cf"  = "Capacity factor",
                           "tx"  = "Transmission dist",
                           "lag" = "Spatial lag")) %>%
  make_panel_label()

save(solar_locations, wind_locations, s_ab_sf, w_ab_sf,
     imp, solar_resamps, wind_resamps, rst_s, rst_w,
     s_dat, w_dat, rgn_results, s_d, w_d, rgn,
     file = "./derived/total.RData")
