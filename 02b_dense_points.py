# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "pyarrow"]
# ///

import os
import time
import pandas as pd

PRG_CSV = "POLSKA.csv"
OUTPUT_PARQUET = "data_raw/prg_subsampled_points.parquet"
CHUNK_SIZE = 1_000_000

os.makedirs("data_raw", exist_ok=True)

print("1. Subsampling building points from PRG (POLSKA.csv)...")
t0 = time.time()

samples = []
chunk_no = 1

for chunk in pd.read_csv(PRG_CSV, sep=";", usecols=["adruni"], chunksize=CHUNK_SIZE, dtype=str):
    # Parse adruni: postcode|teryt|simc1|simc2|ulic|x_geod|y_geod|nr|
    split_cols = chunk["adruni"].str.split("|", expand=True)
    if split_cols.shape[1] < 7:
        continue

    p_norm = split_cols[0].str.strip()

    # Coordinate mapping: GIS X = Easting (col 6), GIS Y = Northing (col 5) in EPSG:2180
    x_gis = pd.to_numeric(split_cols[6], errors="coerce")
    y_gis = pd.to_numeric(split_cols[5], errors="coerce")

    df_valid = pd.DataFrame({"p": p_norm, "x": x_gis, "y": y_gis}).dropna()

    df_sub = df_valid.iloc[::35]
    samples.append(df_sub)

    print(f" -> Processed chunk {chunk_no}...")
    chunk_no += 1

df_all = pd.concat(samples, ignore_index=True)
df_all.to_parquet(OUTPUT_PARQUET, index=False, compression="snappy")

print(f" -> Generated {len(df_all):,} anchor points in {time.time() - t0:.1f} s.")
print(f" -> Saved to: {OUTPUT_PARQUET}")