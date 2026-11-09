source("./syntax/function.R")
librarian::shelf("jsonlite")

# ── Load all results ──────────────────────────────────────────────────────────
load("./derived/model_results.RData")   # solar_resamps, wind_resamps, imp, rst_s, rst_w
load("./derived/total.RData")           # s_d, w_d, rgn_results, solar_locations, wind_locations, s_ab_sf, w_ab_sf

mdl_solarxg_sp <- readRDS("./derived/mdl_solarxg_spatialcv.rds")
mdl_solarrf_sp <- readRDS("./derived/mdl_solarrf_spatialcv.rds")
mdl_windxg_sp  <- readRDS("./derived/mdl_windxg_spatialcv.rds")
mdl_windrf_sp  <- readRDS("./derived/mdl_windrf_spatialcv.rds")

# ── Build updated SITE sub-objects ────────────────────────────────────────────

# 1. CV fold AUC (random 10-fold, from model_results.RData)
get_folds <- function(resamps, key) resamps$values[[paste0(key, "~ROC")]]

cv <- list(
  solar = list(
    glm   = get_folds(solar_resamps, "glm"),
    lasso = get_folds(solar_resamps, "lasso"),
    rf    = get_folds(solar_resamps, "rf"),
    xg    = get_folds(solar_resamps, "xg")
  ),
  wind = list(
    glm   = get_folds(wind_resamps, "glm"),
    lasso = get_folds(wind_resamps, "lasso"),
    rf    = get_folds(wind_resamps, "rf"),
    xg    = get_folds(wind_resamps, "xg")
  )
)

# 2. Spatial CV fold AUC (5-fold, from spatialcv models)
spcv <- list(
  solar = list(
    xg = mdl_solarxg_sp$resample$ROC,
    rf = mdl_solarrf_sp$resample$ROC
  ),
  wind = list(
    xg = mdl_windxg_sp$resample$ROC,
    rf = mdl_windrf_sp$resample$ROC
  )
)

cat("Random CV means:\n")
cat(sprintf("  Solar  — GLM %.3f  Lasso %.3f  RF %.3f  GBM %.3f\n",
            mean(cv$solar$glm), mean(cv$solar$lasso),
            mean(cv$solar$rf),  mean(cv$solar$xg)))
cat(sprintf("  Wind   — GLM %.3f  Lasso %.3f  RF %.3f  GBM %.3f\n",
            mean(cv$wind$glm), mean(cv$wind$lasso),
            mean(cv$wind$rf),  mean(cv$wind$xg)))

cat("\nSpatial CV means:\n")
cat(sprintf("  Solar  — GBM %.3f  RF %.3f\n", mean(spcv$solar$xg), mean(spcv$solar$rf)))
cat(sprintf("  Wind   — GBM %.3f  RF %.3f\n", mean(spcv$wind$xg),  mean(spcv$wind$rf)))

# 3. RE slopes (s_d, w_d) ─ format as [region, variable, R_effect, SE]
format_re <- function(d) {
  lapply(seq_len(nrow(d)), function(i)
    list(d$region[i], d$variable[i], round(d$R_effect[i], 4), round(d$SE[i], 4)))
}

s_d_out <- format_re(s_d)
w_d_out <- format_re(w_d)

# 4. Pack into JSON and patch presentation.html ───────────────────────────────
html_path <- "./presentation.html"
html <- readLines(html_path, warn = FALSE)
site_line <- grep("^window\\.SITE\\s*=", html)

if (length(site_line) != 1) stop("Could not find exactly one 'window.SITE =' line.")

old_line <- html[site_line]

# Parse existing SITE object (strip trailing semicolons / line endings)
site_json <- sub("^window\\.SITE\\s*=\\s*", "", old_line)
site_json <- sub(";\\s*$", "", site_json)
site_obj  <- fromJSON(site_json, simplifyVector = FALSE)

# Replace the sub-keys we have fresh data for
site_obj$cv    <- cv
site_obj$spcv  <- spcv
site_obj$s_d   <- s_d_out
site_obj$w_d   <- w_d_out

# Serialise back — auto_unbox=TRUE keeps scalars as JSON scalars not 1-arrays
new_line <- paste0("window.SITE = ", toJSON(site_obj, auto_unbox = TRUE), ";")

html[site_line] <- new_line
writeLines(html, html_path)

cat(sprintf("\nDone — updated cv, spcv, s_d, w_d in %s\n", html_path))
cat("Reload presentation.html in the browser to see updated charts.\n")
