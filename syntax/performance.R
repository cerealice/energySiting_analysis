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


# ── 5. Load all eight model objects ──────────────────────────────────────────

mdl_solarglm   <- readRDS("./derived/mdl_solarglm.rds")
mdl_solarlasso <- readRDS("./derived/mdl_solarlasso.rds")
mdl_solarrf    <- readRDS("./derived/mdl_solarrf.rds")
mdl_solarxg    <- readRDS("./derived/mdl_solarxg.rds")
mdl_solarnn    <- readRDS("./derived/mdl_solarnn.rds")
mdl_windglm    <- readRDS("./derived/mdl_windglm.rds")
mdl_windlasso  <- readRDS("./derived/mdl_windlasso.rds")
mdl_windrf     <- readRDS("./derived/mdl_windrf.rds")
mdl_windxg     <- readRDS("./derived/mdl_windxg.rds")
mdl_windnn     <- readRDS("./derived/mdl_windnn.rds")

model_list <- list(
  Solar = list(GLM = mdl_solarglm, Lasso = mdl_solarlasso, RF = mdl_solarrf, GBM = mdl_solarxg, NN = mdl_solarnn),
  Wind  = list(GLM = mdl_windglm,  Lasso = mdl_windlasso,  RF = mdl_windrf,  GBM = mdl_windxg,  NN = mdl_windnn)
)


# ── 6. Helpers for threshold-dependent metrics ────────────────────────────────

# Extract fold predictions at best-tune parameters.
# Uses near-equality for numeric hyperparams (lambda, etc.) to avoid fp issues.
get_pred_df <- function(model) {
  pred <- model$pred
  bt   <- model$bestTune
  for (nm in names(bt)) {
    if (is.numeric(pred[[nm]])) {
      pred <- pred[abs(pred[[nm]] - bt[[nm]]) < 1e-10, ]
    } else {
      pred <- pred[pred[[nm]] == bt[[nm]], ]
    }
  }
  pred
}

# Precision / Recall / F1  (positive class = X1 = presence)
metrics_at_threshold <- function(pred_df, threshold) {
  pred_class <- ifelse(pred_df$X1 >= threshold, "X1", "X0")
  obs        <- as.character(pred_df$obs)
  TP <- sum(pred_class == "X1" & obs == "X1")
  FP <- sum(pred_class == "X1" & obs == "X0")
  FN <- sum(pred_class == "X0" & obs == "X1")
  TN <- sum(pred_class == "X0" & obs == "X0")
  prec   <- if ((TP + FP) == 0) NA_real_ else TP / (TP + FP)
  recall <- if ((TP + FN) == 0) NA_real_ else TP / (TP + FN)
  f1     <- if (is.na(prec) || is.na(recall) || (prec + recall) == 0) NA_real_
            else 2 * prec * recall / (prec + recall)
  c(Precision = prec, Recall = recall, F1 = f1,
    TP = TP, FP = FP, FN = FN, TN = TN)
}

# Threshold that maximises F1 (search over a fine grid)
optimal_threshold <- function(pred_df, grid = seq(0.05, 0.95, by = 0.01)) {
  f1s <- sapply(grid, function(t) metrics_at_threshold(pred_df, t)["F1"])
  grid[which.max(f1s)]
}

# PR-AUC via trapezoidal rule across a threshold grid (positive = X1)
compute_pr_auc <- function(pred_df, grid = seq(0, 1, by = 0.005)) {
  pts <- t(sapply(grid, function(t) metrics_at_threshold(pred_df, t)[c("Recall", "Precision")]))
  pts <- as.data.frame(pts)
  pts <- pts[!is.na(pts$Precision) & !is.na(pts$Recall), ]
  pts <- pts[order(pts$Recall), ]
  with(pts, sum(diff(Recall) * (head(Precision, -1) + tail(Precision, -1)) / 2))
}


# ── 7. Summary table: Precision / Recall / F1 / PR-AUC ───────────────────────

thresh_summary <- bind_rows(lapply(names(model_list), function(tech) {
  bind_rows(lapply(names(model_list[[tech]]), function(mdl_name) {
    pd  <- get_pred_df(model_list[[tech]][[mdl_name]])
    opt <- optimal_threshold(pd)
    m05 <- metrics_at_threshold(pd, 0.5)
    mop <- metrics_at_threshold(pd, opt)
    pra <- compute_pr_auc(pd)
    data.frame(
      technology     = tech,
      model          = mdl_name,
      threshold_type = c("fixed_0.5", "optimal_F1"),
      threshold      = c(0.5, opt),
      Precision      = c(m05["Precision"], mop["Precision"]),
      Recall         = c(m05["Recall"],    mop["Recall"]),
      F1             = c(m05["F1"],        mop["F1"]),
      PR_AUC         = pra,
      stringsAsFactors = FALSE
    )
  }))
}))

cat("\n══════════════════════════════════════════════════════════\n")
cat("  Precision / Recall / F1 / PR-AUC — 10-fold CV (pooled)\n")
cat("══════════════════════════════════════════════════════════\n\n")
print(as.data.frame(thresh_summary[, c("technology","model","threshold_type","threshold",
                                       "Precision","Recall","F1","PR_AUC")]),
      row.names = FALSE, digits = 3)


# ── 8. ROC and PR curves (pooled across folds) ────────────────────────────────

make_curve_data <- function(tech, model_list_tech, grid = seq(0, 1, by = 0.005)) {
  bind_rows(lapply(names(model_list_tech), function(mdl_name) {
    pd  <- get_pred_df(model_list_tech[[mdl_name]])
    obs <- as.character(pd$obs)
    pts <- t(sapply(grid, function(t) {
      pc  <- ifelse(pd$X1 >= t, "X1", "X0")
      TP  <- sum(pc == "X1" & obs == "X1")
      FP  <- sum(pc == "X1" & obs == "X0")
      FN  <- sum(pc == "X0" & obs == "X1")
      TN  <- sum(pc == "X0" & obs == "X0")
      TPR <- if ((TP + FN) == 0) NA_real_ else TP / (TP + FN)   # recall / sensitivity
      FPR <- if ((TN + FP) == 0) NA_real_ else FP / (TN + FP)   # 1 − specificity
      PPV <- if ((TP + FP) == 0) NA_real_ else TP / (TP + FP)   # precision
      c(Recall = TPR, FPR = FPR, Precision = PPV)
    }))
    as.data.frame(pts) %>%
      mutate(model = mdl_name, technology = tech, threshold = grid)
  }))
}

curves <- bind_rows(
  make_curve_data("Solar", model_list$Solar),
  make_curve_data("Wind",  model_list$Wind)
)

## ROC curves
p_roc_curves <- curves %>%
  filter(!is.na(Recall), !is.na(FPR)) %>%
  ggplot(aes(x = FPR, y = Recall, colour = model)) +
  geom_line(linewidth = 0.8) +
  geom_abline(linetype = "dashed", colour = "grey60") +
  facet_wrap(~ technology) +
  scale_colour_brewer(palette = "Set1", name = "Model") +
  labs(x = "False positive rate (1 − Specificity)",
       y = "True positive rate (Recall)",
       title = "ROC curves — 10-fold CV (pooled folds)") +
  theme_bw() +
  theme(panel.grid.minor = element_blank(),
        strip.background = element_rect(fill = "gray20"),
        strip.text = element_text(colour = "white"))

ggsave("./fig/original/f_roc_curves.png", p_roc_curves, width = 10, height = 5, dpi = 300)
cat("Saved: ./fig/original/f_roc_curves.png\n")

## PR curves
p_pr_curves <- curves %>%
  filter(!is.na(Recall), !is.na(Precision)) %>%
  ggplot(aes(x = Recall, y = Precision, colour = model)) +
  geom_line(linewidth = 0.8) +
  facet_wrap(~ technology) +
  scale_colour_brewer(palette = "Set1", name = "Model") +
  labs(x = "Recall (True positive rate)",
       y = "Precision (Positive predictive value)",
       title = "Precision–Recall curves — 10-fold CV (pooled folds)") +
  theme_bw() +
  theme(panel.grid.minor = element_blank(),
        strip.background = element_rect(fill = "gray20"),
        strip.text = element_text(colour = "white"))

ggsave("./fig/original/f_pr_curves.png", p_pr_curves, width = 10, height = 5, dpi = 300)
cat("Saved: ./fig/original/f_pr_curves.png\n")
