# /// script
# requires-python = ">=3.10"
# dependencies = ["geopandas", "pandas", "shapely", "requests", "pyarrow"]
# ///

import json
import os
import time
import geopandas as gpd
import pandas as pd
import shapely

INPUT_LOCKERS = "data_raw/lockers_raw.json"
INPUT_NOG = "data_raw/nog_current.csv"
DENSE_POINTS_PARQUET = "data_raw/prg_subsampled_points.parquet"
BOUNDARY_CACHE = "data_raw/poland_boundary.geojson"
OUTPUT_GEOJSON = "public/data/zones.geojson"
OUTPUT_POINTS = "public/data/points.json"

os.makedirs("public/data", exist_ok=True)
os.makedirs("data_raw", exist_ok=True)

def fast_union(geoms):
    """Uses coverage_union_all (optimized for adjacent Voronoi partitions) with fallback."""
    arr = geoms.to_numpy() if hasattr(geoms, "to_numpy") else list(geoms)
    try:
        return shapely.coverage_union_all(arr)
    except Exception:
        return shapely.union_all(arr)

def get_poland_boundary():
    if os.path.exists(BOUNDARY_CACHE):
        print(" -> Using cached Poland boundary...")
        gdf_b = gpd.read_file(BOUNDARY_CACHE)
    else:
        print(" -> Downloading Poland boundary vector...")
        url = "https://raw.githubusercontent.com/jusuff/PolandGeoJson/refs/heads/main/data/poland.country.json"
        gdf_b = gpd.read_file(url)
        gdf_b.to_file(BOUNDARY_CACHE, driver="GeoJSON")

    # Add a 200m buffer in EPSG:2180 so borderline coastal/mountain buildings are not marked as OUTSIDE
    return gdf_b.to_crs(epsg=2180).geometry.union_all().buffer(200)

print("1. Loading raw lockers & cutoff NOG...")
with open(INPUT_LOCKERS, "r", encoding="utf-8") as f:
    df_lockers = pd.DataFrame(json.load(f))

df_nog = pd.read_csv(INPUT_NOG, sep=None, engine="python", dtype=str)
postcode_col = [c for c in df_nog.columns if any(k in c.lower() for k in ["kod", "post", "zip"])][0]
zone_col = [c for c in df_nog.columns if any(k in c.lower() for k in ["strefa", "zone", "godz", "cutoff"])][0]

df_nog = df_nog[[postcode_col, zone_col]].dropna()
df_nog.columns = ["p", "raw_zone"]

def parse_zone(val: str):
    v = str(val).upper()
    if "A" in v or "16" in v: return "A"
    if "B" in v or "15" in v: return "B"
    if "C" in v or "14" in v: return "C"
    if "D" in v or "13" in v: return "D"
    return None

df_nog["z"] = df_nog["raw_zone"].apply(parse_zone)
df_nog["p_norm"] = df_nog["p"].str.replace("-", "").str.strip()
df_nog = df_nog.dropna(subset=["z"]).drop_duplicates(subset=["p_norm"])
nog_lookup = df_nog.set_index("p_norm")["z"].to_dict()

# Process locker locations (EPSG:4326 -> EPSG:2180)
df_lockers["p_norm"] = df_lockers["p"].str.replace("-", "").str.strip()
df_merged = df_lockers.merge(df_nog[["p_norm", "z"]], on="p_norm", how="inner").drop_duplicates(subset=["ln", "lt"])

gdf_lockers = gpd.GeoDataFrame(
    df_merged,
    geometry=gpd.points_from_xy(df_merged["ln"], df_merged["lt"]),
    crs="EPSG:4326"
).to_crs(epsg=2180)[["z", "geometry"]]

combined_geoms = [gdf_lockers]

# Load dense anchor points from PRG if available
if os.path.exists(DENSE_POINTS_PARQUET):
    print(" -> Injecting dense PRG anchor points...")
    df_dense = pd.read_parquet(DENSE_POINTS_PARQUET)
    df_dense["z"] = df_dense["p"].map(nog_lookup)
    df_dense = df_dense.dropna(subset=["z"])

    gdf_dense = gpd.GeoDataFrame(
        df_dense[["z"]],
        geometry=gpd.points_from_xy(df_dense["x"], df_dense["y"]),
        crs="EPSG:2180"
    )
    combined_geoms.append(gdf_dense)
    print(f" -> Injected {len(gdf_dense):,} PRG anchor points.")

gdf_all_points = pd.concat(combined_geoms, ignore_index=True)

print(f"2. Preparing spatial boundaries for {len(gdf_all_points):,} total points...")
poland_mask = get_poland_boundary()

print("3. Generating Voronoi diagram...")
t0 = time.time()
voronoi_grid = shapely.voronoi_polygons(gdf_all_points.geometry.union_all(), extend_to=poland_mask.envelope)
gdf_voronoi = gpd.GeoDataFrame(geometry=list(voronoi_grid.geoms), crs="EPSG:2180")
print(f" -> Generated {len(gdf_voronoi):,} Voronoi cells in {time.time() - t0:.1f} s.")

print("4. Spatial join (mapping points to Voronoi cells)...")
t0 = time.time()
gdf_assigned = gpd.sjoin(gdf_voronoi, gdf_all_points[["z", "geometry"]], how="inner", predicate="contains")
gdf_assigned = gdf_assigned[~gdf_assigned.index.duplicated(keep="first")]
print(f" -> Cells mapped in {time.time() - t0:.1f} s.")

print("5. Merging zone polygons and clipping to land border...")
t0 = time.time()
raw_zones = {}
for z, grp in gdf_assigned.groupby("z"):
    print(f"    Merging zone {z} ({len(grp):,} cells)...")
    merged_poly = fast_union(grp.geometry)
    raw_zones[z] = merged_poly.intersection(poland_mask)

print(f" -> All zones merged and clipped in {time.time() - t0:.1f} s.")

print("6. Resolving overlaps via cascading difference...")
geom_a = raw_zones.get("A", shapely.Polygon())
geom_b = raw_zones.get("B", shapely.Polygon()).difference(geom_a)
mask_ab = shapely.unary_union([geom_a, geom_b])
geom_c = raw_zones.get("C", shapely.Polygon()).difference(mask_ab)
mask_abc = shapely.unary_union([mask_ab, geom_c])
geom_d = raw_zones.get("D", shapely.Polygon()).difference(mask_abc)

clean_zones = gpd.GeoDataFrame([
    {"z": "A", "geometry": geom_a},
    {"z": "B", "geometry": geom_b},
    {"z": "C", "geometry": geom_c},
    {"z": "D", "geometry": geom_d}
], crs="EPSG:2180")

clean_zones = clean_zones[~clean_zones.geometry.is_empty].to_crs(epsg=4326)
clean_zones["geometry"] = clean_zones["geometry"].simplify(tolerance=0.0001, preserve_topology=True)
clean_zones.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
print(f" -> Saved optimized zones to: {OUTPUT_GEOJSON}")

# Export only real lockers to client-side payload
points_by_zone = {"A": [], "B": [], "C": [], "D": []}
for _, row in df_merged.iterrows():
    points_by_zone[row["z"]].append([
        row["lt"], row["ln"], row["n"], row["s"], row["p"], row["c"], row["t"]
    ])

with open(OUTPUT_POINTS, "w", encoding="utf-8") as f:
    json.dump(points_by_zone, f, separators=(',', ':'), ensure_ascii=False)

print(f" -> Saved {len(df_merged):,} lockers to: {OUTPUT_POINTS}")

OUTPUT_POSTCODES = "public/data/postcodes_lookup.json"
postcode_search = {}

# Priority 1: Coords from actual lockers
for _, row in df_merged.iterrows():
    p = row["p_norm"]
    if p not in postcode_search:
        postcode_search[p] = [row["z"], round(row["lt"], 4), round(row["ln"], 4)]

# Priority 2: Coords from dense PRG anchors (only for postcodes without any locker)
if os.path.exists(DENSE_POINTS_PARQUET):
    missing_codes = set(df_dense["p"].unique()) - set(postcode_search.keys())
    if missing_codes:
        df_missing = df_dense[df_dense["p"].isin(missing_codes)].drop_duplicates(subset=["p"])
        gdf_missing = gpd.GeoDataFrame(
            df_missing,
            geometry=gpd.points_from_xy(df_missing["x"], df_missing["y"]),
            crs="EPSG:2180"
        ).to_crs(epsg=4326)

        for _, row in gdf_missing.iterrows():
            postcode_search[row["p"]] = [row["z"], round(row.geometry.y, 4), round(row.geometry.x, 4)]

with open(OUTPUT_POSTCODES, "w", encoding="utf-8") as f:
    json.dump(postcode_search, f, separators=(',', ':'))

print(f" -> Saved {len(postcode_search):,} searchable postcodes to: {OUTPUT_POSTCODES}")