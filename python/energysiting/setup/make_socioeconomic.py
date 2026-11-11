"""make_socioeconomic.R — poverty (MEF IRPEF), unemployment (ISTAT LFS, NUTS-3),
foreign-born share (ISTAT census) rasters."""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd

from .. import config
from ._geo import base, gisco_communes, gisco_nuts, mask_base, rasterize, save_var


def comuni_with_province():
    com = gisco_communes("IT", "2016")
    com["istat_code"] = com["COMM_ID"].str[-6:]
    n3 = gisco_nuts(3, "2016")[["NUTS_ID", "geometry"]]
    cent = gpd.GeoDataFrame(com[["istat_code"]], geometry=com.geometry.centroid, crs=com.crs)
    prov = gpd.sjoin(cent, n3, predicate="within", how="left")[["istat_code", "NUTS_ID"]]
    return com.merge(prov.drop_duplicates("istat_code"), on="istat_code", how="left")


def gap_fill(df, col):
    df[col] = df[col].fillna(df.groupby("NUTS_ID")[col].transform("median"))
    df[col] = df[col].fillna(df[col].median())
    return df


def run():
    config.ensure_dirs()
    b = base()
    com = comuni_with_province()

    # 1. poverty proxy: mean taxable income per municipality
    mef = pd.read_csv(config.RAW / "Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.csv",
                      sep=";", encoding="latin1", decimal=",", thousands=".")
    mef["istat_code"] = mef["Codice Istat Comune"].astype(int).map("{:06d}".format)
    mef["mean_income"] = (mef["Reddito imponibile - Ammontare in euro"]
                          / mef["Reddito imponibile - Frequenza"])
    d = gap_fill(com.merge(mef[["istat_code", "mean_income"]].dropna(), on="istat_code", how="left"),
                 "mean_income")
    save_var(mask_base(rasterize(d, b.grid, field="mean_income"), b), "svi_pov.tif", b)

    # 2. unemployment (NUTS-3; NUTS-2016 geometry, NUTS-2006 fallback, national mean)
    u = pd.read_csv(config.RAW / "Dati provinciali (IT1,151_914_DF_DCCV_TAXDISOCCU1_8,1.0).csv")
    u = u[(u.SEX.astype(str) == "9") & (u.REF_AREA.str.len() == 5) & (u.DATA_TYPE == "UNEM_R")]
    u = u.sort_values("TIME_PERIOD").groupby("REF_AREA").tail(1)[["REF_AREA", "Osservazione"]]
    r16 = rasterize(gisco_nuts(3, "2016").merge(u, left_on="NUTS_ID", right_on="REF_AREA", how="left"),
                    b.grid, field="Osservazione")
    r06 = rasterize(gisco_nuts(3, "2006").merge(u, left_on="NUTS_ID", right_on="REF_AREA", how="left"),
                    b.grid, field="Osservazione")
    merged = np.where(np.isfinite(r16), r16, r06)
    merged = mask_base(merged, b)
    merged = np.where(np.isnan(merged), np.nanmean(merged), merged)
    save_var(mask_base(merged, b), "svi_unemp.tif", b)

    # 3. foreign-born share
    fb = pd.read_csv(config.RAW / "Popolazione per paese di nascita - comuni (IT1,DF_DCSS_HCUE_COM_3_COM,1.0).csv",
                     dtype={"REF_AREA": str})
    fb = fb[(fb.GENDER.astype(str).isin(["T", "True", "TRUE"])) & (fb.REF_AREA.str.len() == 6)
            & fb.COUNTRY_BIRTH.isin(["WORLD", "WRL_X_ITA"])]
    fb = fb.sort_values("TIME_PERIOD").groupby(["REF_AREA", "COUNTRY_BIRTH"]).tail(1)
    w = fb.pivot(index="REF_AREA", columns="COUNTRY_BIRTH", values="Osservazione")
    w["foreignborn_pct"] = np.where(w["WORLD"] > 0, w["WRL_X_ITA"] / w["WORLD"], np.nan)
    d = gap_fill(com.merge(w["foreignborn_pct"].rename_axis("istat_code").reset_index(),
                           on="istat_code", how="left"), "foreignborn_pct")
    save_var(mask_base(rasterize(d, b.grid, field="foreignborn_pct"), b), "svi_foreignborn.tif", b)


if __name__ == "__main__":
    run()
