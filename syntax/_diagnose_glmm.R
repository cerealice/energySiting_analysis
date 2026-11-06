source("./syntax/function.R")
s_dat <- read.csv("./derived/solar.csv")
load("./derived/absence.RData")
load("./derived/location.RData")

nuts2_sf <- region_boundaries %>% select(NUTS_NAME)
s_ab_nuts2 <- s_ab_sf %>% st_centroid() %>%
  st_join(nuts2_sf, join = st_within) %>%
  st_drop_geometry() %>% select(id, nuts2 = NUTS_NAME)
s_pres_nuts2 <- solar_locations %>% st_drop_geometry() %>%
  transmute(unique_id, nuts2 = state_code)

s_full <- bind_rows(
  s_dat %>% filter(treat == "X0") %>% left_join(s_ab_nuts2,   by = c("zone" = "id")),
  s_dat %>% filter(treat == "X1") %>% left_join(s_pres_nuts2, by = c("zone" = "unique_id"))
) %>% mutate(treat_int = as.integer(treat == "X1"))

cat("NAs in nuts2:", sum(is.na(s_full$nuts2)), "\n")
tbl <- table(Region = s_full$nuts2, Treat = s_full$treat_int)
print(tbl)
cat("\nRegions with 0 presences:", paste(rownames(tbl)[tbl[,2] == 0], collapse = ", "), "\n")
cat("Regions with 0 absences:", paste(rownames(tbl)[tbl[,1] == 0], collapse = ", "), "\n")
cat("Min obs per region:", min(rowSums(tbl)), "\n")
