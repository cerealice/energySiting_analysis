source("./syntax/function.R")

load("./derived/model_results.RData")

# ── 1. Summary table: mean ± SD of ROC, Sens, Spec per model × technology ─────

fmt_resamps <- function(resamps, tech) {
  df <- resamps$values %>%
    pivot_longer(-Resample, names_to = "key", values_to = "value") %>%
    separate(key, into = c("model", "metric"), sep = "~") %>%
    group_by(model, metric) %>%
    summarise(mean = mean(value), sd = sd(value), .groups = "drop") %>%
    mutate(label = sprintf("%.3f (±%.3f)", mean, sd),
           technology = tech,
           model = toupper(model))
  df
}

solar_summary <- fmt_resamps(solar_resamps, "Solar")
wind_summary  <- fmt_resamps(wind_resamps,  "Wind")
all_summary   <- bind_rows(solar_summary, wind_summary)

cat("\n══════════════════════════════════════════════════════════\n")
cat("  Model performance — 10-fold CV (mean ± SD)\n")
cat("══════════════════════════════════════════════════════════\n\n")

tbl <- all_summary %>%
  filter(metric == "ROC") %>%
  select(technology, model, mean, sd) %>%
  arrange(technology, desc(mean))

print(as.data.frame(tbl), row.names = FALSE)

cat("\n── Full table (ROC / Sens / Spec) ──────────────────────\n")
wide <- all_summary %>%
  select(technology, model, metric, label) %>%
  pivot_wider(names_from = metric, values_from = label) %>%
  arrange(technology, model)
print(as.data.frame(wide), row.names = FALSE)


# ── 2. Best model per technology (by mean ROC) ────────────────────────────────

best_solar <- solar_summary %>% filter(metric == "ROC") %>%
  slice_max(mean, n = 1) %>% pull(model)
best_wind  <- wind_summary  %>% filter(metric == "ROC") %>%
  slice_max(mean, n = 1) %>% pull(model)

cat(sprintf("\nBest model — Solar : %s\n", best_solar))
cat(sprintf("Best model — Wind  : %s\n", best_wind))


# ── 3. Pairwise Wilcoxon tests on ROC (is the best model significantly better?) ─

cat("\n── Pairwise Wilcoxon on ROC (solar) ───────────────────\n")
solar_roc <- solar_resamps$values %>%
  select(ends_with("ROC")) %>%
  rename_with(~ gsub("~ROC", "", .))
print(round(pairwise.wilcox.test(
  unlist(solar_roc), rep(names(solar_roc), each = 10),
  p.adjust.method = "holm")$p.value, 3))

cat("\n── Pairwise Wilcoxon on ROC (wind) ─────────────────────\n")
wind_roc <- wind_resamps$values %>%
  select(ends_with("ROC")) %>%
  rename_with(~ gsub("~ROC", "", .))
print(round(pairwise.wilcox.test(
  unlist(wind_roc), rep(names(wind_roc), each = 10),
  p.adjust.method = "holm")$p.value, 3))


# ── 4. Plots ──────────────────────────────────────────────────────────────────

dir.create("./fig/original", showWarnings = FALSE, recursive = TRUE)

## 4a. Box-plot of fold-level ROC across models
plot_roc <- function(resamps, tech, fill_col) {
  resamps$values %>%
    select(Resample, ends_with("ROC")) %>%
    pivot_longer(-Resample, names_to = "model", values_to = "ROC") %>%
    mutate(model = toupper(gsub("~ROC", "", model))) %>%
    ggplot(aes(x = reorder(model, ROC, FUN = median), y = ROC, fill = model)) +
    geom_boxplot(alpha = 0.7, outlier.size = 1.5) +
    geom_jitter(width = 0.1, size = 1, alpha = 0.5) +
    scale_fill_brewer(palette = "Set2") +
    coord_flip() +
    labs(title = tech, x = NULL, y = "AUC-ROC (10-fold CV)") +
    theme_bw() +
    theme(legend.position = "none",
          panel.grid.minor = element_blank())
}

p_solar_roc <- plot_roc(solar_resamps, "Solar", "orange")
p_wind_roc  <- plot_roc(wind_resamps,  "Wind",  "steelblue")

f_perf <- ggarrange(p_solar_roc, p_wind_roc, ncol = 2)
ggsave("./fig/original/f_performance_roc.png", f_perf, width = 10, height = 4, dpi = 300)
cat("\nSaved: ./fig/original/f_performance_roc.png\n")

## 4b. Variable importance (already in imp object from model_results.RData)
top_vars <- imp %>%
  filter(model %in% c("RF", "GBM")) %>%
  group_by(tech, rowname) %>%
  summarise(Overall = mean(Overall), .groups = "drop") %>%
  group_by(tech) %>%
  slice_max(Overall, n = 12)

f_imp <- top_vars %>%
  ggplot(aes(x = Overall, y = reorder(rowname, Overall), fill = tech)) +
  geom_col(alpha = 0.8) +
  facet_wrap(~ tech, scales = "free_y") +
  scale_fill_manual(values = c(Solar = "#E8A838", Wind = "#4A90D9")) +
  labs(x = "Variable importance (mean RF + GBM)", y = NULL,
       title = "Top 12 predictors — RF & GBM average") +
  theme_bw() +
  theme(legend.position = "none",
        panel.grid.minor = element_blank(),
        strip.background = element_rect(fill = "gray20"),
        strip.text = element_text(color = "white"))

ggsave("./fig/original/f_varimp.png", f_imp, width = 10, height = 5, dpi = 300)
cat("Saved: ./fig/original/f_varimp.png\n")


# ── 5. What is still missing for the paper ────────────────────────────────────

cat("
══════════════════════════════════════════════════════════
  NEXT STEPS NEEDED BEFORE SUBMISSION
══════════════════════════════════════════════════════════

[DONE]  10-fold random CV  — AUC, Sens, Spec reported
[TODO]  Spatial / blocked CV  (blockCV or CAST package)
        → Requires re-fitting models; random CV likely
          overestimates OOS performance by ~0.05–0.15 AUC
        → Run: library(blockCV); spatialBlock(...)

[TODO]  Calibration check (reliability diagram)
        → Requires model objects (mdl_solarrf, etc.)
        → Add to modeling.R:
          saveRDS(mdl_solarrf,  './derived/mdl_solarrf.rds')
          saveRDS(mdl_windrf,   './derived/mdl_windrf.rds')
          saveRDS(mdl_solarxg,  './derived/mdl_solarxg.rds')
          saveRDS(mdl_windxg,   './derived/mdl_windxg.rds')
        → Then: calibrate with val.prob() or CalibrationCurves

[TODO]  Area of applicability
        → library(CAST); aoa(newdata, model)

[TODO]  Temporal hold-out validation (plants built after year X)
        → Requires commissioning dates on presence points
")
