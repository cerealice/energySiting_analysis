source("./syntax/function.R")
librarian::shelf("blockCV")

# ── Shared model formula (must match modeling.R exactly) ─────────────────────
# lulc_other = reference land-cover class (omitted → "Other lands" baseline)
# region_isole = reference region dummy  (omitted → "Isole" baseline)
region_model <- treat ~ tx + roads + sub + slope + pop + unemploy + foreignborn +
  poverty + gdp_pc + inst_quality +
  lulc_forest + lulc_grassland + lulc_shrubland + lulc_riparian + lulc_sparse +
  lulc_agriculture + lulc_developed +
  region_nordovest + region_nordest + region_centro + region_sud +
  env + cf + lag


# ── 1. Recover spatial coordinates for each zone ──────────────────────────────
# Presences: mean x/y of cells sharing the same zone ID in the hull raster

get_presence_xy <- function(hull_tif) {
  hull <- terra::rast(hull_tif)
  as.data.frame(hull, xy = TRUE, na.rm = TRUE) %>%
    setNames(c("x", "y", "zone")) %>%
    group_by(zone) %>%
    summarise(x = mean(x), y = mean(y), .groups = "drop")
}

presence_xy_s <- get_presence_xy("./derived/solar_hull_existing.tif")
presence_xy_w <- get_presence_xy("./derived/wind_hull_existing.tif")

# Absences: centroid of each buffered polygon in s_ab_sf / w_ab_sf
load("./derived/absence.RData")   # loads s_ab_sf, w_ab_sf

get_absence_xy <- function(ab_sf) {
  coords <- ab_sf %>%
    sf::st_centroid() %>%
    sf::st_coordinates() %>%
    as.data.frame()
  data.frame(zone = ab_sf$id, x = coords[, 1], y = coords[, 2])
}

absence_xy_s <- get_absence_xy(s_ab_sf)
absence_xy_w <- get_absence_xy(w_ab_sf)


# ── 2. Attach coordinates to training data and convert to sf ──────────────────
# Presence zone IDs (raster cell values, 1…N_plants) overlap with absence
# polygon IDs (ab_sf$id, also starting at 1).  Tag each lookup table with the
# treat value so the join key is (zone, treat) — unique by construction.

coords_s <- bind_rows(
  mutate(presence_xy_s, treat = "X1"),
  mutate(absence_xy_s,  treat = "X0")
)
coords_w <- bind_rows(
  mutate(presence_xy_w, treat = "X1"),
  mutate(absence_xy_w,  treat = "X0")
)

attach_coords <- function(dat_csv, coords) {
  dat_csv %>%
    left_join(coords, by = c("zone", "treat")) %>%
    filter(!is.na(x), !is.na(y)) %>%
    mutate(treat = factor(make.names(treat))) %>%
    sf::st_as_sf(coords = c("x", "y"), crs = 3035, remove = FALSE)
}

s_dat_sf <- attach_coords(read.csv("./derived/solar.csv"), coords_s)
w_dat_sf <- attach_coords(read.csv("./derived/wind.csv"),  coords_w)

cat(sprintf("Solar training points with coords: %d / %d\n",
            nrow(s_dat_sf), nrow(read.csv("./derived/solar.csv"))))
cat(sprintf("Wind  training points with coords: %d / %d\n",
            nrow(w_dat_sf), nrow(read.csv("./derived/wind.csv"))))


# ── 3. Find spatial autocorrelation range ─────────────────────────────────────
# This determines the minimum block size needed for genuine spatial independence.

base_r <- terra::rast("./data/processed_data/masks/Italy_base_raster.tif")

cat("\nEstimating spatial autocorrelation range — solar...\n")
range_s <- blockCV::cv_spatial_autocor(
  r        = base_r,
  x        = s_dat_sf,
  column   = "treat",
  progress = FALSE
)
cat(sprintf("  Solar autocorrelation range: %.0f m\n", range_s$range))

cat("Estimating spatial autocorrelation range — wind...\n")
range_w <- blockCV::cv_spatial_autocor(
  r        = base_r,
  x        = w_dat_sf,
  column   = "treat",
  progress = FALSE
)
cat(sprintf("  Wind autocorrelation range:  %.0f m\n", range_w$range))


# ── 4. Build spatial block folds ──────────────────────────────────────────────
# Use the detected range (rounded up to nearest 10km) as the block size.
# If range < 50km, use 50km as a conservative floor.

block_size_s <- max(50000, ceiling(range_s$range / 10000) * 10000)
block_size_w <- max(50000, ceiling(range_w$range / 10000) * 10000)

cat(sprintf("\nBlock size — solar: %.0f m\n", block_size_s))
cat(sprintf("Block size — wind:  %.0f m\n", block_size_w))

set.seed(42)
sb_s <- blockCV::cv_spatial(
  x          = s_dat_sf,
  column     = "treat",
  r          = base_r,
  size       = block_size_s,
  k          = 5,
  selection  = "random",
  progress   = FALSE,
  report     = FALSE
)

sb_w <- blockCV::cv_spatial(
  x          = w_dat_sf,
  column     = "treat",
  r          = base_r,
  size       = block_size_w,
  k          = 5,
  selection  = "random",
  progress   = FALSE,
  report     = FALSE
)

# Save fold maps
dir.create("./fig/original", showWarnings = FALSE, recursive = TRUE)
png("./fig/original/spatial_blocks_solar.png", width = 800, height = 900, res = 150)
plot(sb_s)
dev.off()
png("./fig/original/spatial_blocks_wind.png", width = 800, height = 900, res = 150)
plot(sb_w)
dev.off()
cat("\nSaved block maps to fig/original/\n")


# ── 5. Fit GBM and RF under spatial CV ───────────────────────────────────────
# Only the top-2 models from random CV to keep runtime manageable.
# caret trainControl accepts spatial folds via the `index` argument:
# index[[i]] = row indices used for TRAINING in fold i.

make_spatial_tc <- function(sb) {
  train_idx <- lapply(sb$folds_list, function(f) f[[1]])
  trainControl(
    method          = "cv",
    index           = train_idx,
    returnResamp    = "all",
    savePredictions = TRUE,
    classProbs      = TRUE,
    summaryFunction = twoClassSummary
  )
}

tc_s <- make_spatial_tc(sb_s)
tc_w <- make_spatial_tc(sb_w)

tune_grid_gbm <- expand.grid(
  n.trees           = c(50, 100),
  interaction.depth = c(3, 6),
  shrinkage         = c(0.01, 0.1),
  n.minobsinnode    = c(5, 10)
)

cat("\nFitting GBM — solar (spatial CV)...\n")
mdl_s_gbm_sp <- train(
  form      = region_model,
  data      = sf::st_drop_geometry(s_dat_sf),
  method    = "gbm",
  trControl = tc_s,
  tuneGrid  = tune_grid_gbm,
  na.action = na.omit,
  verbose   = FALSE
)

cat("Fitting RF — solar (spatial CV)...\n")
mdl_s_rf_sp <- train(
  form      = region_model,
  data      = sf::st_drop_geometry(s_dat_sf),
  method    = "rf",
  metric    = "ROC",
  trControl = tc_s,
  na.action = na.omit,
  importance = TRUE
)

cat("Fitting GBM — wind (spatial CV)...\n")
mdl_w_gbm_sp <- train(
  form      = region_model,
  data      = sf::st_drop_geometry(w_dat_sf),
  method    = "gbm",
  trControl = tc_w,
  tuneGrid  = tune_grid_gbm,
  na.action = na.omit,
  verbose   = FALSE
)

cat("Fitting RF — wind (spatial CV)...\n")
mdl_w_rf_sp <- train(
  form      = region_model,
  data      = sf::st_drop_geometry(w_dat_sf),
  method    = "rf",
  metric    = "ROC",
  trControl = tc_w,
  na.action = na.omit,
  importance = TRUE
)


# ── 6. Compare random CV vs spatial CV ───────────────────────────────────────

load("./derived/model_results.RData")   # solar_resamps, wind_resamps

extract_roc <- function(resamps, model_name) {
  resamps$values[[paste0(model_name, "~ROC")]]
}

comparison <- tibble(
  technology = c(rep("Solar", 20), rep("Wind", 20)),
  model      = rep(c(rep("GBM", 10), rep("RF", 10)), 2),
  cv_type    = "Random (10-fold)",
  ROC        = c(
    extract_roc(solar_resamps, "xg"),
    extract_roc(solar_resamps, "rf"),
    extract_roc(wind_resamps,  "xg"),
    extract_roc(wind_resamps,  "rf")
  )
) %>%
  bind_rows(tibble(
    technology = c(rep("Solar", nrow(mdl_s_gbm_sp$resample) + nrow(mdl_s_rf_sp$resample)),
                   rep("Wind",  nrow(mdl_w_gbm_sp$resample) + nrow(mdl_w_rf_sp$resample))),
    model      = c(rep("GBM", nrow(mdl_s_gbm_sp$resample)),
                   rep("RF",  nrow(mdl_s_rf_sp$resample)),
                   rep("GBM", nrow(mdl_w_gbm_sp$resample)),
                   rep("RF",  nrow(mdl_w_rf_sp$resample))),
    cv_type    = "Spatial block (5-fold)",
    ROC        = c(mdl_s_gbm_sp$resample$ROC, mdl_s_rf_sp$resample$ROC,
                   mdl_w_gbm_sp$resample$ROC, mdl_w_rf_sp$resample$ROC)
  ))

# Print summary
cat("\n══════════════════════════════════════════════════════════\n")
cat("  Random CV  vs  Spatial CV — AUC-ROC comparison\n")
cat("══════════════════════════════════════════════════════════\n")
comparison %>%
  group_by(technology, model, cv_type) %>%
  summarise(mean_ROC = mean(ROC), sd_ROC = sd(ROC), .groups = "drop") %>%
  mutate(label = sprintf("%.3f (±%.3f)", mean_ROC, sd_ROC)) %>%
  select(technology, model, cv_type, label) %>%
  pivot_wider(names_from = cv_type, values_from = label) %>%
  as.data.frame() %>%
  print(row.names = FALSE)


# ── 7. Plot comparison ────────────────────────────────────────────────────────

f_cv_compare <- comparison %>%
  ggplot(aes(x = cv_type, y = ROC, fill = cv_type)) +
  geom_boxplot(alpha = 0.7, outlier.size = 1.5) +
  geom_jitter(width = 0.1, size = 1.5, alpha = 0.6) +
  facet_grid(technology ~ model) +
  scale_fill_manual(values = c("Random (10-fold)"      = "#7FC97F",
                                "Spatial block (5-fold)" = "#F0A500")) +
  labs(x = NULL, y = "AUC-ROC", fill = NULL,
       title = "Random CV vs Spatial block CV",
       subtitle = sprintf("Block sizes: Solar = %.0f km, Wind = %.0f km",
                          block_size_s / 1000, block_size_w / 1000)) +
  theme_bw() +
  theme(legend.position  = "bottom",
        panel.grid.minor = element_blank(),
        strip.background = element_rect(fill = "gray20"),
        strip.text       = element_text(color = "white", face = "bold"))

ggsave("./fig/original/f_spatial_cv_comparison.png",
       f_cv_compare, width = 8, height = 6, dpi = 300)
cat("\nSaved: ./fig/original/f_spatial_cv_comparison.png\n")


# ── 8. Save spatial CV results ────────────────────────────────────────────────

saveRDS(mdl_s_gbm_sp, "./derived/mdl_solarxg_spatialcv.rds")
saveRDS(mdl_s_rf_sp,  "./derived/mdl_solarrf_spatialcv.rds")
saveRDS(mdl_w_gbm_sp, "./derived/mdl_windxg_spatialcv.rds")
saveRDS(mdl_w_rf_sp,  "./derived/mdl_windrf_spatialcv.rds")
saveRDS(list(solar = sb_s, wind = sb_w), "./derived/spatial_folds.rds")

cat("\nSaved spatial CV models and folds to ./derived/\n")
cat("\n── What to report in the paper ─────────────────────────\n")
cat("Table X: AUC-ROC under random 10-fold CV and spatial block CV\n")
cat(sprintf("         Block size: solar = %.0f km, wind = %.0f km\n",
            block_size_s/1000, block_size_w/1000))
cat(sprintf("         Autocorrelation range: solar = %.0f m, wind = %.0f m\n",
            range_s$range, range_w$range))
cat("         The gap between random and spatial CV = spatial optimism\n")
cat("         (report both; do NOT hide the random CV number)\n")
