load('./derived/model_results.RData')

for (tch in c("Solar", "Wind")) {
  for (mdl in c("RF", "GBM")) {
    cat(sprintf("\n=== %s %s ===\n", tch, mdl))
    sub <- imp[imp$tech == tch & imp$model == mdl, c("rowname", "Overall")]
    print(sub[order(-sub$Overall), ], row.names = FALSE)
  }
}
