if (!require(librarian)){
  install.packages("librarian")
  library(librarian)
}

librarian::shelf("raster", "sf", "tidyverse", "terra", "here", "tictoc", "foreach", "doParallel", "foreign", "dplyr",
                 "readxl", "giscoR",
                 "stargazer", "caret", "ggpubr", "tidyterra", "gridExtra", "rasterVis", "RColorBrewer", "grid",
                 "lme4", "lmerTest", "ggstance", "cowplot", "mapview","viridis","patchwork")
sf_use_s2(FALSE)
library(ggnewscale)
ggsave <- function(..., bg = 'white') ggplot2::ggsave(..., bg = bg)

# Italian CRS: ETRS89 / LAEA Europe (equal-area; European equivalent of EPSG:5070)
projection <- raster::crs("+init=epsg:3035")

# Italian NUTS-2 regional boundaries via Eurostat (no shapefile download needed)
region_boundaries <- giscoR::gisco_get_nuts(
  year       = "2021",
  resolution = "03",
  spatialtype = "RG",
  country    = "IT",
  nuts_level = "2"
) %>%
  st_transform(crs = 3035) %>%
  select(NUTS_ID, NUTS_NAME, geometry)
