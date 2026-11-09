# /// script
# requires-python = ">=3.10"
# dependencies = ["geopandas", "pandas", "shapely"]
# ///

import os
import time
import pandas as pd
import geopandas as gpd
from shapely import prepare, contains_xy

ZONES_GEOJSON = "public/data/zones.geojson"
NOG_CSV = "data_raw/nog_current.csv"
PRG_POLSKA_CSV = "POLSKA.csv"
MISMATCHES_CSV = "data_raw/mismatches_sample.csv"
CHUNK_SIZE = 500_000

def parse_zone(val: str):
    v = str(val).upper()
    if "A" in v or "16" in v: return "A"
    if "B" in v or "15" in v: return "B"
    if "C" in v or "14" in v: return "C"
    if "D" in v or "13" in v: return "D"
    return None

print("1. Loading zones polygon map...")
gdf_zones = gpd.read_file(ZONES_GEOJSON).to_crs(epsg=2180)

# Pre-compile prepared geometries for ultra-fast spatial indexing
zone_geoms = {}
for z in ["A", "B", "C", "D"]:
    poly = gdf_zones[gdf_zones["z"] == z].geometry.union_all()
    prepare(poly)
    zone_geoms[z] = poly

print("2. Loading NOG truth table...")
df_nog = pd.read_csv(NOG_CSV, sep=None, engine="python", dtype=str)
postcode_col = [c for c in df_nog.columns if any(k in c.lower() for k in ["kod", "post", "zip"])][0]
zone_col = [c for c in df_nog.columns if any(k in c.lower() for k in ["strefa", "zone", "godz", "cutoff"])][0]

df_nog["p_norm"] = df_nog[postcode_col].str.replace("-", "").str.strip()
df_nog["expected_zone"] = df_nog[zone_col].apply(parse_zone)
nog_lookup = df_nog.dropna(subset=["expected_zone"]).drop_duplicates(subset=["p_norm"]).set_index("p_norm")["expected_zone"].to_dict()

print("3. Streaming and evaluating all address points from POLSKA.csv...")
start_time = time.time()

total_tested = 0
total_correct = 0
confusion = {true_z: {map_z: 0 for map_z in ["A", "B", "C", "D", "OUTSIDE"]} for true_z in ["A", "B", "C", "D"]}
mismatch_samples = []

chunk_no = 1
for chunk in pd.read_csv(PRG_POLSKA_CSV, sep=";", usecols=["adruni", "miejscowosc", "numer"], chunksize=CHUNK_SIZE, dtype=str):
    # Parse adruni: postcode|teryt|simc1|simc2|ulic|x_geod|y_geod|nr|
    split_cols = chunk["adruni"].str.split("|", expand=True)
    if split_cols.shape[1] < 7:
        continue

    p_norm = split_cols[0].str.strip()
    
    # Map coordinate swap: GIS X = Easting (geodetic Y), GIS Y = Northing (geodetic X)
    try:
        x_gis = pd.to_numeric(split_cols[6], errors="coerce").to_numpy()
        y_gis = pd.to_numeric(split_cols[5], errors="coerce").to_numpy()
    except Exception:
        continue

    # Filter out entries missing coords or absent from NOG
    valid_mask = (~pd.isna(x_gis)) & (~pd.isna(y_gis))
    expected_zones = p_norm.map(nog_lookup).to_numpy()
    has_expected = ~pd.isna(expected_zones)

    mask = valid_mask & has_expected
    if not mask.any():
        continue

    x_vals = x_gis[mask]
    y_vals = y_gis[mask]
    exp_z = expected_zones[mask]

    # Vectorized Point-in-Polygon check against prepared geometries
    in_a = contains_xy(zone_geoms["A"], x_vals, y_vals)
    in_b = contains_xy(zone_geoms["B"], x_vals, y_vals)
    in_c = contains_xy(zone_geoms["C"], x_vals, y_vals)
    in_d = contains_xy(zone_geoms["D"], x_vals, y_vals)

    map_z = ["OUTSIDE"] * len(x_vals)
    for i in range(len(x_vals)):
        if in_a[i]: map_z[i] = "A"
        elif in_b[i]: map_z[i] = "B"
        elif in_c[i]: map_z[i] = "C"
        elif in_d[i]: map_z[i] = "D"

    for ez, mz in zip(exp_z, map_z):
        confusion[ez][mz] += 1
        if ez == mz:
            total_correct += 1
        total_tested += 1

    # Keep a small sample of mismatches for spatial inspection
    mismatches_idx = [i for i, (ez, mz) in enumerate(zip(exp_z, map_z)) if ez != mz]
    if mismatches_idx and len(mismatch_samples) < 5000:
        chunk_valid = chunk[mask].iloc[mismatches_idx]
        for idx_pos, (_, r) in enumerate(chunk_valid.iterrows()):
            if len(mismatch_samples) >= 5000:
                break
            mismatch_samples.append({
                "miejscowosc": r.get("miejscowosc", ""),
                "numer": r.get("numer", ""),
                "expected": exp_z[mismatches_idx[idx_pos]],
                "map": map_z[mismatches_idx[idx_pos]],
                "x_gis": x_vals[mismatches_idx[idx_pos]],
                "y_gis": y_vals[mismatches_idx[idx_pos]]
            })

    print(f" -> Processed chunk {chunk_no} ({total_tested:,} verified points so far)...")
    chunk_no += 1

elapsed = time.time() - start_time
accuracy = (total_correct / total_tested * 100) if total_tested else 0

print("\n" + "=" * 54)
print(f"NATIONAL ACCURACY BENCHMARK (POLSKA.csv)")
print(f"Total time elapsed:     {elapsed:.1f} s")
print(f"Total buildings tested: {total_tested:,}")
print(f"Correctly classified:   {total_correct:,}")
print(f"Mismatched:             {total_tested - total_correct:,}")
print(f"FINAL MODEL ACCURACY:   {accuracy:.2f}%")
print("=" * 54)

print("\nConfusion Matrix (Expected NOG vs Map Geometry):")
df_conf = pd.DataFrame(confusion).T
print(df_conf)

if mismatch_samples:
    pd.DataFrame(mismatch_samples).to_csv(MISMATCHES_CSV, index=False)
    print(f"\nSaved sample of mismatches to: {MISMATCHES_CSV}")