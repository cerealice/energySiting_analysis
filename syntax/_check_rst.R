load('./derived/model_results.RData')

cat("=== Solar: range of pe by variable ===\n")
agg <- aggregate(pe ~ var, data = rst_s, FUN = function(x) c(min=min(x), max=max(x), extreme=max(abs(x))))
agg <- agg[order(-sapply(agg$pe[,3], identity)), ]
print(agg, row.names = FALSE)

cat("\n=== Rows where |pe| > 5 (quasi-separation) ===\n")
print(rst_s[abs(rst_s$pe) > 5, c("var","Group","pe","se","color")])

cat("\n=== Wind: rows where |pe| > 5 ===\n")
print(rst_w[abs(rst_w$pe) > 5, c("var","Group","pe","se","color")])
