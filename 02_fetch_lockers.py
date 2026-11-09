# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///

import json
import os
import requests

API_URL = "https://api-shipx-pl.easypack24.net/v1/points"
OUTPUT_DIR = "data_raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "lockers_raw.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

params = {
    "status": "Operating",
    "per_page": 1000,
    "page": 1
}

points = []
print("Fetching all operating points from InPost API...")

while True:
    response = requests.get(API_URL, params=params, timeout=25)
    response.raise_for_status()
    payload = response.json()
    
    items = payload.get("items", [])
    if not items:
        break

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

            points.append({
                "n": name,
                "t": point_type,
                "lt": round(lat, 5),
                "ln": round(lon, 5),
                "p": address.get("post_code", ""),
                "c": address.get("city", ""),
                "s": f"{address.get('street', '')} {address.get('building_number', '')}".strip()
            })

    total_pages = payload.get("total_pages", 1)
    print(f" -> Page {params['page']}/{total_pages} | Total items: {len(points)}")

    if params["page"] >= total_pages:
        break
    params["page"] += 1

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(points, f, ensure_ascii=False)

print(f"\nDone. Successfully saved {len(points)} points to {OUTPUT_FILE}.")