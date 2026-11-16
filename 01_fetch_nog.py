# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "beautifulsoup4"]
# ///

import os
import requests
from bs4 import BeautifulSoup

SCRAPER_API_URL = "https://api.scraperapi.com/"
PAGE_URL = "https://inpost.pl/godziny-odbiorow"
OUTPUT_DIR = "data_raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nog_current.csv")

api_key = os.getenv("SCRAPER_API_KEY")
if not api_key:
    raise RuntimeError("Missing SCRAPER_API_KEY environment variable.")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_via_scraperapi(url: str, render_js: bool = False) -> requests.Response:
    payload = {
        "api_key": api_key,
        "url": url,
        "country_code": "pl",
    }
    if render_js:
        payload["render"] = "true"

    resp = requests.get(SCRAPER_API_URL, params=payload, timeout=90)
    resp.raise_for_status()
    return resp


def main() -> None:
    print("1. Fetching InPost page via ScraperAPI to parse active CSV path...")
    response = fetch_via_scraperapi(PAGE_URL, render_js=True)

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

    print(f"2. Downloading CSV via ScraperAPI from: {file_url}")
    csv_response = fetch_via_scraperapi(file_url, render_js=False)

    content_type = csv_response.headers.get("content-type", "")
    if "text/html" in content_type.lower():
        raise RuntimeError("Received HTML instead of CSV (blocked by WAF).")

    with open(OUTPUT_FILE, "wb") as f:
        f.write(csv_response.content)

    size_kb = len(csv_response.content) // 1024
    print(f"Done. Saved to {OUTPUT_FILE} ({size_kb} KB).")


if __name__ == "__main__":
    main()
