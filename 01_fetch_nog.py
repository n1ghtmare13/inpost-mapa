# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "beautifulsoup4"]
# ///

import os
import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://inpost.pl/godziny-odbiorow"
OUTPUT_DIR = "data_raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nog_current.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

print("1. Fetching InPost page to parse active CSV path...")
response = requests.get(PAGE_URL, headers=headers, timeout=15)
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

file_url = f"https://inpost.pl/sites/default/files/{target_path}"

print(f"2. Downloading CSV from: {file_url}")
csv_response = requests.get(file_url, headers=headers, timeout=30)
csv_response.raise_for_status()

with open(OUTPUT_FILE, "wb") as f:
    f.write(csv_response.content)

size_kb = len(csv_response.content) // 1024
print(f"Done. Saved to {OUTPUT_FILE} ({size_kb} KB).")