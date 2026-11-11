source("./syntax/function.R")

load("./derived/total.RData")
results_masked <- rast("./derived/results_masked.tif")

# Original figures are saved to fig/original/ so they are never overwritten
# by new experimental versions in fig/new/
dir.create("./fig/original", showWarnings = FALSE, recursive = TRUE)

# plot(dac_masked)
# plot(results_masked)

### f1
f1a <- solar_locations %>%
  ggplot() +
  geom_sf(data = region_boundaries, fill = "gray50", color = "gray0") +  # Italy NUTS-2 border
  geom_sf(aes(color = `Capacity (MW)`), size = 0.5) +
  theme_minimal() +
  scale_color_gradientn(colors = brewer.pal(n = 9, name = "YlOrRd")) +
  labs(title = "Existing solar", color = "Capacity\n(MW)") +
  coord_sf(crs = st_crs(3035), datum = NA) +
  theme(legend.position = "right")


f1b <- wind_locations %>%
  ggplot() +
  geom_sf(data = region_boundaries, fill = "gray50", color = "gray0") +  # Italy NUTS-2 border
  geom_sf(aes(color = p_cap / 1000), size = 0.5) +
  theme_minimal() +
  scale_color_gradientn(colors = brewer.pal(n = 9, name = "YlOrRd")) +
  labs(title = "Existing wind", color = "Capacity\n(GW)") +
  coord_sf(crs = st_crs(3035), datum = NA) +
  theme(legend.position = "right")

f1c <- s_ab_sf %>%
  st_buffer(dist = 5000) %>%
  ggplot() +
  geom_sf(data = region_boundaries, fill = "gray50", color = "gray0") +
  geom_sf(aes(fill = factor(iteration)), color = "NA", size = 0.001) +
  theme_minimal() +
  scale_fill_manual(values = brewer.pal(n = 10, name = "Paired")) +
  labs(title = "Pseudo-absence - solar", fill = "Iteration") +
  coord_sf(crs = st_crs(3035), datum = NA) +
  theme(legend.position = "right")

f1d <- w_ab_sf %>%
  ggplot() +
  geom_sf(data = region_boundaries, fill = "gray50", color = "gray0") +
  geom_sf(aes(fill = factor(iteration)), color = "NA", size = 0.001) +
  theme_minimal() +
  scale_fill_manual(values = brewer.pal(n = 10, name = "Paired")) +
  labs(title = "Pseudo-absence - wind", fill = "Iteration") +
  coord_sf(crs = st_crs(3035), datum = NA) +
  theme(legend.position = "right")


ggsave("./fig/original/f1.png",
       ggarrange(f1a,f1b,f1c,f1d, nrow=2, ncol = 2), width = 14, height = 10, dpi = 300)


### f2
# Binary LULC dummies cause quasi-complete separation in logistic regression,
# producing coefficients ~1e+07 that make the axis unreadable. These variables
# are well-represented in the RF/GBM variable importance panels below, so they
# are excluded here. The axis is auto-scaled from the remaining coefficients.
lulc_sep_vars <- c("Forest", "Grassland", "Shrubland", "Riparian",
                   "Vegetated", "Agriculture", "Developed", "Other lands")

# s_reg <- rst_s %>%
#   ggplot(aes(x = pe, y = reorder(var, pe))) +
#   geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +
#   geom_errorbar(aes(xmin=pe-1.96*se, xmax=pe+1.96*se),color="gray50", width = 0.5) +
#   geom_point(aes(fill = color),size = 2,pch=21) +
#   theme_bw() +
#   facet_wrap(~ Group, nrow = 1) +
#   
#   labs(fill = "Significant", y = "", x = "Odds ratio (log scale)", title = "A") +
#   scale_fill_manual(values=c("gray", "red")) +
#   theme(panel.grid.minor = element_blank(),
#         panel.grid.major.x = element_blank(),
#         strip.background =element_rect(fill="gray22",color="gray22"),
#         strip.text = element_text(color = 'white',family="sans",size=12),
#         legend.position = "none",
#         axis.text.x = element_text(color = "black",family="sans",size=6),
#         axis.text.y = element_text(color = "black",family="sans",size=9),
#         axis.title.x = element_text(color = "black",family="sans",size=11),
#         plot.title=element_text(family="sans", size=16, hjust = -0.09)) 


# ── NUTS-2 → NUTS-1 aggregation ───────────────────────────────────────────────
# modeling.R rename map already relabelled nuts2_itc1..itc4 → "Nord-Ovest" etc.
# Multiple NUTS-2 within the same macro-area now share a var name; collapse them
# by mean coefficient and pooled SE before plotting.
aggregate_nuts <- function(rst) {
  rst %>%
    group_by(var, Group) %>%
    summarise(
      pe    = mean(pe, na.rm = TRUE),
      se    = sqrt(mean(se^2, na.rm = TRUE)),
      color = if_else(abs(mean(pe, na.rm = TRUE)) /
                        sqrt(mean(se^2, na.rm = TRUE)) > 1.96, "Y", "N"),
      .groups = "drop"
    )
}
rst_s <- aggregate_nuts(rst_s)
rst_w <- aggregate_nuts(rst_w)

s_reg1 <- rst_s %>%
  filter(!var %in% lulc_sep_vars, color == "Y") %>%
  mutate(Group = factor(Group),
         color = factor(color, levels = c("Y","N"))) %>%
  ggplot(aes(x = pe, y = reorder(var, pe))) +
  geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +
  geom_point(aes(fill = color),size = 2,pch=21) +
  theme_bw() +
  labs(fill = "Significant", y = "", x = "Odds ratio (log scale)", title = "A") +
  scale_fill_manual(values=c("red", "gray")) +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = "none",
        axis.text.x = element_text(color = "black",family="sans",size=6),
        axis.text.y = element_text(color = "black",family="sans",size=9),
        axis.title.x = element_text(color = "black",family="sans",size=11),
        plot.title=element_text(family="sans", size=16, hjust = -0.22))


s_reg2 <- rst_s %>%
  filter(Group == 5, !var %in% lulc_sep_vars, color == "Y") %>%
  mutate(color = factor(color, levels = c("Y","N"))) %>%
  ggplot(aes(x = pe, y = reorder(var,pe))) +
  geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +
  geom_errorbar(aes(xmin=pe-1.96*se, xmax=pe+1.96*se),color="gray50", width = 0.5) +
  geom_point(aes(fill = color),size = 2,pch=21) +
  theme_bw() +
  labs(fill = "Significant", y = "", x = "Odds ratio (log scale)", title = "") +
  scale_fill_manual(values=c("red", "gray")) +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = c(0.7, 0.3),
        axis.text.x = element_text(color = "black",family="sans",size=6),
        axis.text.y = element_text(color = "black",family="sans",size=9),
        axis.title.x = element_text(color = "black",family="sans",size=11),
        plot.title=element_text(family="sans", size=16, hjust = -0.09))


# w_reg <- rst_w %>% 
#   ggplot(aes(x = pe, y = reorder(var, pe))) +
#   geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +
#   geom_errorbar(aes(xmin=pe-1.96*se, xmax=pe+1.96*se),color="gray50", width = 0.5) +
#   geom_point(aes(fill = color),size = 2,pch=21) +
#   theme_bw() +
#   labs(title = "B") +
#   facet_wrap(~ Group, nrow = 1) +
#   
#   labs(fill = "Significant", y = "", x = "Odds ratio (log scale)") +
#   scale_fill_manual(values=c("gray", "red")) +
#   theme(panel.grid.minor = element_blank(),
#         panel.grid.major.x = element_blank(),
#         strip.background =element_rect(fill="gray22",color="gray22"),
#         strip.text = element_text(color = 'white',family="sans",size=12),
#         legend.position = "bottom",
#         axis.text.x = element_text(color = "black",family="sans",size=6),
#         axis.text.y = element_text(color = "black",family="sans",size=9),
#         axis.title.x = element_text(color = "black",family="sans",size=11),
#         plot.title=element_text(family="sans", size=16,  hjust = -0.09)) 


w_reg1 <- rst_w %>%
  filter(!var %in% lulc_sep_vars, color == "Y") %>%
  mutate(Group = factor(Group),
         color = factor(color, levels = c("Y","N"))) %>%
  ggplot(aes(x = pe, y = reorder(var, pe))) +
  geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +
  geom_point(aes(fill = color),size = 2,pch=21) +
  theme_bw() +
  labs(fill = "Significant", y = "", x = "Odds ratio (log scale)", title = "B") +
  scale_fill_manual(values=c("red", "gray")) +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = "none",
        axis.text.x = element_text(color = "black",family="sans",size=6),
        axis.text.y = element_text(color = "black",family="sans",size=9),
        axis.title.x = element_text(color = "black",family="sans",size=11),
        plot.title=element_text(family="sans", size=16, hjust = -0.22))

w_reg2 <- rst_w %>%
  filter(Group == 5, !var %in% lulc_sep_vars, color == "Y") %>%
  mutate(color = factor(color, levels = c("Y","N"))) %>%
  ggplot(aes(x = pe, y = reorder(var, pe))) +
  geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +
  geom_errorbar(aes(xmin=pe-1.96*se, xmax=pe+1.96*se),color="gray50", width = 0.5) +
  geom_point(aes(fill = color),size = 2,pch=21) +
  theme_bw() +
  labs(fill = "Significant", y = "", x = "Odds ratio (log scale)", title = "") +
  scale_fill_manual(values=c("red", "gray")) +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = c(0.2, 0.7),
        axis.text.x = element_text(color = "black",family="sans",size=6),
        axis.text.y = element_text(color = "black",family="sans",size=9),
        axis.title.x = element_text(color = "black",family="sans",size=11),
        plot.title=element_text(family="sans", size=20))


importance_s <- imp %>% 
  filter(tech == "Solar") %>% 
  ggplot() +
  geom_col(aes(x = reorder(rowname, desc(Overall)), y = Overall, fill = model), width = 0.7, position = position_dodge(0.8)) +
  labs(x = "", y = "Importance (%)", fill = "", title = "") +
  theme_bw() +
  scale_fill_brewer(palette = "Paired") +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = "right",
        axis.text.x = element_text(color = "black",family="sans",size=11, angle = 45, hjust = 1),
        axis.text.y = element_text(color = "black",family="sans",size=9),
        axis.title.x = element_text(color = "black",family="sans",size=9),
        plot.title=element_text(family="sans", size=16, hjust = -0.03)) 


importance_w <- imp %>% 
  filter(tech == "Wind") %>% 
  ggplot() +
  geom_col(aes(x = reorder(rowname, desc(Overall)), y = Overall, fill = model), width = 0.7, position = position_dodge(0.8)) +
  labs(x = "", y = "Importance (%)", fill = "", title = "") +
  theme_bw() +
  scale_fill_brewer(palette = "Paired") +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = "right",
        axis.text.x = element_text(color = "black",family="sans",size=11,angle = 45, hjust = 1),
        axis.text.y = element_text(color = "black",family="sans",size=9),
        axis.title.x = element_text(color = "black",family="sans",size=9),
        plot.title=element_text(family="sans", size=16, hjust = -0.02)) 


f2 <- ggarrange(ggarrange(ggarrange(s_reg1, s_reg2, ncol = 2), 
                             importance_s, 
                             heights = c(1.5, 1),
                             nrow = 2),
                   ggarrange(ggarrange(w_reg1, w_reg2, ncol = 2), 
                             importance_w, 
                             heights = c(1.5, 1),
                             nrow = 2), 
                   nrow = 2, heights = c(1,1))
ggsave("./fig/original/f2.png", f2, width = 12, height = 14, dpi = 300)

### f3 
model_name <- c("GLM Solar","Lasso Solar","RF Solar","GBM Solar",
            "GLM Wind","Lasso Wind","RF Wind","GBM Wind")


temp_file <- tempfile(fileext = ".png")
png(temp_file, width = 8, height = 12, units = "in", res = 300)

par(mfrow = c(4, 2), bty = 'n')

# Use the raster extent (stable across terra versions) and a shared viridis
# colour ramp fixed at 0–1 so all 8 maps are directly comparable
map_ext  <- ext(results_masked[[1]])
map_cols <- viridis(100)

for(i in 1:8){
  plot(map_ext, main = model_name[[i]], cex.main = 2,
       col = "white", border = NA, axes = FALSE)
  plot(terra::vect(rgn), col = "gray70", border = NA, add = TRUE)
  plot(results_masked[[i]],
       col = map_cols, range = c(0, 1),
       axes = FALSE, legend = FALSE, add = TRUE)
  plot(terra::vect(rgn), border = "white", col = NA, add = TRUE, lwd = 1.5)
}

dev.off()

# Read and convert to grob
raster_img <- png::readPNG(temp_file)
raster_grobs <- grid::rasterGrob(raster_img, interpolate = TRUE)

raster_grobs_labeled <- arrangeGrob(raster_grobs, 
                                    top = textGrob("A", 
                                                   x = unit(0, "npc"),         
                                                   just = "left",    
                                                   gp = gpar(fontsize = 16)))
# grid.draw(raster_grobs_labeled)

barplot <- rgn_results %>%
  mutate(region = factor(region, levels = c("Nord-Ovest","Nord-Est","Centro","Sud","Isole"))) %>%
  ggplot(aes(x = region, y = mean, fill = model)) +
  geom_bar(stat = "identity", position = position_dodge(width = 0.8), width = 0.6) +
  # geom_point(position = position_dodge(width = 0.8)) +
  # geom_errorbar(aes(ymin = mean - sd, ymax = mean + sd),
  #               position = position_dodge(width = 0.8),
  #               width = 0.2, color = "black") +
  
  facet_wrap(~tech, nrow = 2)+
  coord_flip() +
  scale_y_continuous(labels = scales::percent_format(accuracy = 1), limits = c(0,0.4)) +
  scale_fill_brewer(palette = "Paired") +
  labs(
    title = "B",
    x = "",
    y = "Mean probability",
    fill = ""
  ) +
  theme_minimal() +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = "bottom",
        legend.text = element_text(size = 8),
        legend.key.size = unit(0.2, 'cm'), 
        axis.text.x = element_text(color = "black",family="sans",size=8),
        axis.text.y = element_text(color = "black",family="sans",size=12),
        axis.title.x = element_text(color = "black",family="sans",size=12),
        plot.title=element_text(family="sans", size=16, hjust = -0.5)) 

barplot_grob <- ggplotGrob(barplot)
# grid.draw(barplot_grob)


temp_file <- tempfile(fileext = ".png")
png(temp_file, width = 8, height = 2, units = "in", res = 300)

par(mfrow = c(1,1), bty = 'n')

r <- results_masked[[1]]
n_colors <- 100
color_ramp <- viridis(n_colors)
breaks <- seq(0, 1, length.out = n_colors + 1)

# # Create a blank plot canvas
plot.new()
plot.window(xlim = c(0, 1), ylim = c(0, 1))

legend_x <- seq(0, 1, length.out = n_colors)
rect(xleft = legend_x[-length(legend_x)],
     ybottom = 0.4,
     xright = legend_x[-1],
     ytop = 1.5,
     col = color_ramp,
     border = NA)

axis(1, at = seq(0, 1, by = 0.2), labels = seq(0, 1, by = 0.2), cex.axis = 1.5)
title(main = "Probability", cex.main = 1.7, font.main = 1)
dev.off()

# Read and convert to grob
raster_img <- png::readPNG(temp_file)
legend_grob <- grid::rasterGrob(raster_img, interpolate = TRUE)


layout_matrix <- rbind(
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(1,1,2),
  c(3,3,2)
)

# Save to PNG
png(filename = "./fig/original/f3.png", width = 10, height = 10, units = "in", res = 300)

grid.newpage()
grid.arrange(grobs = list(raster_grobs_labeled, barplot_grob, legend_grob), layout_matrix = layout_matrix)

dev.off()

### f4
# NUTS-2 geometries for choropleth maps (GLMM now uses 21 NUTS-2 regions)
rgn2 <- giscoR::gisco_get_nuts(country = "IT", nuts_level = "2",
                                year = "2021", resolution = "03") |>
  st_transform(crs = 3035) |>
  mutate(region = NAME_LATN)

s_f4 <- s_d %>%
  mutate(region = factor(region)) %>%
    ggplot(aes(x = R_effect, y = region, xmin=R_effect-SE, xmax=R_effect+SE)) +
    geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +

    geom_pointrangeh(position = position_dodge2v(height = 0.4), color = "gray10", fatten = 2, size = 0.7) +

    facet_wrap(~panel_label, scales = "free_x") +
    theme_bw() +
    
    labs(x = "Odds ratio (log scale)", y ="", color = "",
         title = "") +
  
    theme(panel.grid.minor = element_blank(),
          panel.grid.major.x = element_blank(),
          strip.background =element_rect(fill="gray22",color="gray22"),
          strip.text = element_text(color = 'white',family="sans",size=12),
          legend.position = "bottom",
          axis.text.x = element_text(color = "black",family="sans",size=11),
          axis.text.y = element_text(color = "black",family="sans",size=11),
          axis.title.x = element_text(color = "black",family="sans",size=11),
          plot.title=element_text(family="sans", size=20)) 
  

w_f4 <- w_d %>%
  mutate(region = factor(region)) %>%
  ggplot(aes(x = R_effect, y = region, xmin=R_effect-SE, xmax=R_effect+SE)) +
  geom_vline(xintercept = 0,linetype = "dashed", size = 0.5, color = "gray30") +

  geom_pointrangeh(position = position_dodge2v(height = 0.4), color = "gray10", fatten = 2, size = 0.7) +

  facet_wrap(~panel_label, scales = "free_x") +
  theme_bw() +
  
  labs(x = "Odds ratio (log scale)", y ="", color = "",
       title = "") +
  
  theme(panel.grid.minor = element_blank(),
        panel.grid.major.x = element_blank(),
        strip.background =element_rect(fill="gray22",color="gray22"),
        strip.text = element_text(color = 'white',family="sans",size=12),
        legend.position = "bottom",
        axis.text.x = element_text(color = "black",family="sans",size=11),
        axis.text.y = element_text(color = "black",family="sans",size=11),
        axis.title.x = element_text(color = "black",family="sans",size=11),
        plot.title=element_text(family="sans", size=20))


s_panel_labels <- s_d %>%
  distinct(variable, panel_label) %>%
  arrange(variable) %>%
  pull(panel_label)

maps <- map(.x = s_panel_labels,
            .f = function(x) {
              var_name <- s_d$variable[s_d$panel_label == x][1]
              rgn2 %>%
              left_join(s_d, by = "region") %>%
              filter(panel_label == x) %>%

              ggplot() +
              geom_sf(fill = "white", color = "gray0") +
              geom_sf(aes(fill = R_effect), size = 0.3) +

              theme_minimal() +
              scale_fill_gradient2(
                low      = if (var_name %in% c("Transmission dist", "Environmental score")) "darkorange3" else "royalblue3",
                mid      = "white",
                high     = if (var_name %in% c("Transmission dist", "Environmental score")) "royalblue3" else "darkorange3",
                midpoint = 0) +

              labs(title = x, fill = "") +
              coord_sf(crs = st_crs(3035), datum = NA) +
              theme(legend.position = "right",
                    plot.title = element_text(hjust = 0.5))
})

s_f41 <- plot_grid(plotlist = maps, labels = "A", label_size = 14, label_fontface = "plain", nrow = 1, hjust = -0.2)


w_panel_labels <- w_d %>%
  distinct(variable, panel_label) %>%
  arrange(variable) %>%
  pull(panel_label)

maps <- map(.x = w_panel_labels,
            .f = function(x) {
              var_name <- w_d$variable[w_d$panel_label == x][1]
              rgn2 %>%
              left_join(w_d, by = "region") %>%
              filter(panel_label == x) %>%

              ggplot() +
              geom_sf(fill = "white", color = "gray0") +
              geom_sf(aes(fill = R_effect), size = 0.3) +

              theme_minimal() +
              scale_fill_gradient2(
                low      = if (var_name %in% c("Transmission dist", "Environmental score")) "darkorange3" else "royalblue3",
                mid      = "white",
                high     = if (var_name %in% c("Transmission dist", "Environmental score")) "royalblue3" else "darkorange3",
                midpoint = 0) +

              labs(title = x, fill = "") +
              coord_sf(crs = st_crs(3035), datum = NA) +
              theme(legend.position = "right",
                    plot.title = element_text(hjust = 0.5))
})

w_f41 <- plot_grid(plotlist = maps, labels = "B", label_size = 14, label_fontface = "plain", nrow = 1, hjust = -0.2)


f4 <- ggarrange(s_f41, s_f4, w_f41, w_f4, heights = c(1,1,1,1), nrow = 4)
ggsave("./fig/original/f4.png", f4, width = 12, height = 12)



# dodge <- position_dodge(width = 0.6)
# f5b <- ttest_results %>%
#   mutate(sig = p_value < 0.05) %>%
#   pivot_longer(
#     cols = c(mean_DAC, mean_nonDAC, se_DAC, se_nonDAC),
#     names_to = c(".value", "group"),
#     names_pattern = "(mean|se)_(DAC|nonDAC)"
#   ) %>%
#   mutate(
#     group = recode(group, "DAC" = "DAC", "nonDAC" = "Non-DAC"),
#     ci_low  = mean - 1.96 * se,
#     ci_high = mean + 1.96 * se
#   ) %>%
#   mutate(region = factor(region, levels = c("West","Mtwest","Midwest","Texas","South","Northeast"))) %>% 
#   ggplot(aes(x = group, y = mean)) +
#   
#   # POINTS: filled if significant, hollow if not
#   geom_point(
#     aes(
#       color = model,
#       fill = sig,
#       group = interaction(model, sig)
#     ),
#     shape = 21,
#     size = 2,
#     stroke = 1,
#     position = dodge
#   ) +
#   
#   # ERROR BARS: must use the same grouping + dodge
#   geom_errorbar(
#     aes(
#       ymin = ci_low,
#       ymax = ci_high,
#       color = model,
#       group = interaction(model, sig)
#     ),
#     width = 0.3,
#     position = dodge
#   ) +
#   
#   facet_grid(tech ~ region, switch = "y") +
#   
#   scale_fill_manual(values = c(`FALSE` = "white", `TRUE` = "black")) +
#   scale_color_manual(values = c(
#     "GLM"      = "#1b9e77",
#     "Lasso"    = "#d95f02",
#     "RF"       = "#7570b3",
#     "GBM"      = "#e7298a"
#   )) +
#   
#   labs(
#     title = "DAC vs Non‑DAC Mean Values with 95% CI",
#     subtitle = "Significant differences (p < 0.05) shown as filled points",
#     x = "",
#     y = "Mean Value",
#     color = "Model",
#     fill = "Significant"
#   ) +
#   theme_bw(base_size = 14) +
#   theme(panel.grid.minor = element_blank(),
#         panel.grid.major.x = element_blank(),
#         strip.background =element_rect(fill="gray22",color="gray22"),
#         strip.text = element_text(color = 'white',family="sans",size=12),
#         strip.text.y.left = element_text(angle = 0, size = 12, face = "bold"),
#         strip.placement = "outside",
#         legend.position = "bottom",
#         axis.text.x = element_text(angle = 30, hjust = 1,
#                                    color = "black",family="sans",size=11),
#         axis.text.y = element_text(color = "black",family="sans",size=11),
#         axis.title.x = element_text(color = "black",family="sans",size=11),
#         plot.title=element_text(family="sans", size=20))



# ── f5: DAC analysis (US-specific) ───────────────────────────────────────────
# The Disadvantaged Communities (DAC) analysis was US-specific and has been
# removed for the Italy fork. Add an Italian equivalent (e.g. deprived-area
# mapping based on ISTAT deprivation indices) when that data is available.




