source("./syntax/function.R")

load("./derived/total.RData")
results_masked <- rast("./derived/results_masked.tif")

dir.create("./fig/new", showWarnings = FALSE, recursive = TRUE)


# ══════════════════════════════════════════════════════════════════════════════
# New Fig 1 — presence dot maps (top) + pseudo-absence density heatmaps (bottom)
#
# The original second row colours pseudo-absence dots by iteration (discrete,
# hard to read spatially).  The new version replaces that with a 2-D kernel
# density surface so you can immediately see where pseudo-absences are
# concentrated across Italy.
# ══════════════════════════════════════════════════════════════════════════════

# ── Top row: unchanged presence dot maps ─────────────────────────────────────
f1a <- solar_locations %>%
  ggplot() +
  geom_sf(data = region_boundaries, fill = "gray50", color = "gray0") +
  geom_sf(aes(color = `Capacity (MW)`), size = 0.5) +
  theme_minimal() +
  scale_color_gradientn(colors = brewer.pal(n = 9, name = "YlOrRd")) +
  labs(title = "Existing solar", color = "Capacity\n(MW)") +
  coord_sf(crs = st_crs(3035), datum = NA) +
  theme(legend.position = "right",
        plot.title = element_text(hjust = 0.5, size = 13, face = "bold"))

f1b <- wind_locations %>%
  ggplot() +
  geom_sf(data = region_boundaries, fill = "gray50", color = "gray0") +
  geom_sf(aes(color = p_cap / 1000), size = 0.5) +
  theme_minimal() +
  scale_color_gradientn(colors = brewer.pal(n = 9, name = "YlOrRd")) +
  labs(title = "Existing wind", color = "Capacity\n(GW)") +
  coord_sf(crs = st_crs(3035), datum = NA) +
  theme(legend.position = "right",
        plot.title = element_text(hjust = 0.5, size = 13, face = "bold"))


# ── Bottom row: pseudo-absence density heatmaps ───────────────────────────────
# Extract XY coordinates from the sf objects (st_centroid handles both point
# and polygon geometries safely).
s_ab_xy <- s_ab_sf %>%
  st_centroid() %>%
  st_coordinates() %>%
  as.data.frame()

w_ab_xy <- w_ab_sf %>%
  st_centroid() %>%
  st_coordinates() %>%
  as.data.frame()

absence_map <- function(xy, title) {
  ggplot() +
    # Base: Italy regions as a dark backdrop so density colours pop
    geom_sf(data = region_boundaries, fill = "gray25", color = NA) +
    # 2-D kernel density estimate, rendered as a continuous raster
    stat_density_2d(
      data    = xy,
      aes(x = X, y = Y, fill = after_stat(density)),
      geom    = "raster",
      contour = FALSE,
      interpolate = TRUE
    ) +
    scale_fill_viridis_c(
      option   = "magma",
      na.value = NA,
      name     = "Density",
      labels   = scales::label_scientific(digits = 1)
    ) +
    # Region borders on top so Italy's shape stays visible
    geom_sf(data = region_boundaries, fill = NA,
            color = "white", linewidth = 0.4) +
    coord_sf(crs = st_crs(3035), datum = NA) +
    theme_minimal() +
    labs(title = title) +
    theme(
      legend.position  = "right",
      plot.title       = element_text(hjust = 0.5, size = 13, face = "bold"),
      panel.grid       = element_blank()
    )
}

f1c_new <- absence_map(s_ab_xy, "Pseudo-absence \u2013 solar")
f1d_new <- absence_map(w_ab_xy, "Pseudo-absence \u2013 wind")


# ── Assemble and save ─────────────────────────────────────────────────────────
ggsave(
  "./fig/new/f1.png",
  ggarrange(f1a, f1b, f1c_new, f1d_new, nrow = 2, ncol = 2),
  width  = 14,
  height = 10,
  dpi    = 300
)

message("Saved: ./fig/new/f1.png")
