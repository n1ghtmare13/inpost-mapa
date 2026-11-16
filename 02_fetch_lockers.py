# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///

import json
import os
from concurrent.futures import ThreadPoolExecutor
import requests

API_URL = "https://api-shipx-pl.easypack24.net/v1/points"
OUTPUT_DIR = "data_raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "lockers_raw.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_page(page: int) -> dict:
    resp = requests.get(
        API_URL,
        params={"status": "Operating", "per_page": 1000, "page": page},
        timeout=25,
    )
    resp.raise_for_status()
    return resp.json()


def extract_points(items: list[dict]) -> list[dict]:
    batch = []
    for item in items:
        location = item.get("location") or {}
        address = item.get("address_details") or {}
        lat = location.get("latitude")
        lon = location.get("longitude")

        if lat and lon:
            raw_type = item.get("type")
            types = raw_type if isinstance(raw_type, list) else [raw_type]
            name = item.get("name", "")

            is_pop = ("pop" in types) or ("parcel_locker_superpop" in types) or name.startswith("POP-")
            point_type = "pop" if is_pop else "locker"

            batch.append({
                "n": name,
                "t": point_type,
                "lt": round(lat, 5),
                "ln": round(lon, 5),
                "p": address.get("post_code", ""),
                "c": address.get("city", ""),
                "s": f"{address.get('street', '')} {address.get('building_number', '')}".strip(),
            })
    return batch


print("Fetching all operating points from InPost API...")
first_payload = fetch_page(1)
total_pages = first_payload.get("total_pages", 1)
points = extract_points(first_payload.get("items", []))
print(f" -> Page 1/{total_pages} | Total items: {len(points)}")

if total_pages > 1:
    with ThreadPoolExecutor(max_workers=8) as pool:
        for page_no, payload in enumerate(pool.map(fetch_page, range(2, total_pages + 1)), start=2):
            points.extend(extract_points(payload.get("items", [])))
            print(f" -> Page {page_no}/{total_pages} | Total items: {len(points)}")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(points, f, ensure_ascii=False)

print(f"\nDone. Successfully saved {len(points)} points to {OUTPUT_FILE}.")