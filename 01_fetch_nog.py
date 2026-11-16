# /// script
# requires-python = ">=3.10"
# dependencies = ["curl_cffi", "beautifulsoup4"]
# ///

import os
from bs4 import BeautifulSoup
from curl_cffi import requests

PAGE_URL = "https://inpost.pl/godziny-odbiorow"
OUTPUT_DIR = "data_raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nog_current.csv")
PROXY_URL = os.getenv("PROXY_URL")

os.makedirs(OUTPUT_DIR, exist_ok=True)
proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

with requests.Session(impersonate="chrome", proxies=proxies) as session:
    session.headers.update({
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    print("1. Fetching InPost page to parse active CSV path...")
    response = session.get(PAGE_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form", class_="pickup--hours")

    if not form:
        raise RuntimeError("Could not find the 'pickup--hours' form on page.")

    current_file = form.get("data-csv-file", "").strip()
    new_file = form.get("data-new-csv-file", "").strip()
    announcement = form.get("data-new-csv-info", "").strip()

    print(f" -> Current file reference : {current_file}")
    if new_file:
        print(f" -> Upcoming file reference: {new_file} ({announcement})")

    target_path = new_file if new_file else current_file
    if not target_path:
        raise RuntimeError("No CSV file reference found in form attributes.")

    if target_path.startswith("http"):
        file_url = target_path
    elif target_path.startswith("/"):
        file_url = f"https://inpost.pl{target_path}"
    else:
        file_url = f"https://inpost.pl/sites/default/files/{target_path}"

    print(f"2. Downloading CSV from: {file_url}")
    csv_response = session.get(
        file_url,
        headers={"Referer": PAGE_URL},
        timeout=30,
    )
    csv_response.raise_for_status()

with open(OUTPUT_FILE, "wb") as f:
    f.write(csv_response.content)

size_kb = len(csv_response.content) // 1024
print(f"Done. Saved to {OUTPUT_FILE} ({size_kb} KB).")
