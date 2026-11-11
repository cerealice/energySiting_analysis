"""make_zenodo_socioeconomic.R — GDP per capita and institutional quality
(NUTS-3, Zenodo DOI 10.5281/zenodo.11121790)."""
from __future__ import annotations

import pandas as pd

from .. import config
from ._geo import base, gisco_nuts, mask_base, rasterize, save_var

NAME_FIX = {
    "Aosta": "Valle d'Aosta/Vallée d'Aoste", "Bolzano-Bozen": "Bolzano-Bozen / Bozen-Bolzano",
    "Massa Carrara": "Massa-Carrara", "Forli'-Cesena": "Forlì-Cesena",
    "Reggio Calabria": "Reggio di Calabria", "Verbano Cusio Ossola": "Verbano-Cusio-Ossola",
}


def latest(df, col):
    d = df.dropna(subset=[col]).sort_values("year").groupby("province_name").tail(1)
    return d[["province_name", col]]


def run():
    config.ensure_dirs()
    b = base()
    z = pd.read_csv(config.RAW / "NUTS_3_DATA.csv")
    zen = latest(z, "gdp_pc_const_p").rename(columns={"gdp_pc_const_p": "gdp_pc"}).merge(
        latest(z, "institutional_quality_index").rename(
            columns={"institutional_quality_index": "inst_quality"}), on="province_name", how="outer")
    zen["join_name"] = zen["province_name"].map(NAME_FIX).fillna(zen["province_name"])
    n3 = gisco_nuts(3, "2016").merge(zen, left_on="NAME_LATN", right_on="join_name", how="left")
    miss = n3.loc[n3.gdp_pc.isna() & n3.inst_quality.isna(), "NAME_LATN"].tolist()
    if miss:
        print("Provinces with no Zenodo match (gap-filled):", miss)
    for col, out in (("gdp_pc", "zenodo_gdp_pc.tif"), ("inst_quality", "zenodo_inst_quality.tif")):
        n3[col] = n3[col].fillna(n3[col].median())
        save_var(mask_base(rasterize(n3, b.grid, field=col), b), out, b)


if __name__ == "__main__":
    run()
