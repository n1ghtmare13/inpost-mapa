# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "beautifulsoup4"]
# ///

import json
import os
import re
from datetime import date, datetime, timezone
import requests
from bs4 import BeautifulSoup

SCRAPER_API_URL = "https://api.scraperapi.com/"
PAGE_URL = "https://inpost.pl/godziny-odbiorow"
DATA_RAW_DIR = "data_raw"
PUBLIC_DATA_DIR = "public/data"

CURRENT_FILE = os.path.join(DATA_RAW_DIR, "nog_current.csv")
UPCOMING_FILE = os.path.join(DATA_RAW_DIR, "nog_upcoming.csv")
META_FILE = os.path.join(PUBLIC_DATA_DIR, "nog_meta.json")

api_key = os.getenv("SCRAPER_API_KEY")
if not api_key:
    raise RuntimeError("Missing SCRAPER_API_KEY environment variable.")

os.makedirs(DATA_RAW_DIR, exist_ok=True)
os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)


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


def build_file_url(path: str) -> str:
    if path.startswith("http"):
        return path
    if path.startswith("/"):
        return f"https://inpost.pl{path}"
    return f"https://inpost.pl/sites/default/files/{path}"


def download_csv(rel_path: str, destination: str) -> None:
    file_url = build_file_url(rel_path)
    print(f"Downloading {file_url} -> {destination}")
    csv_response = fetch_via_scraperapi(file_url, render_js=False)

    if "text/html" in csv_response.headers.get("content-type", "").lower():
        raise RuntimeError(f"Received HTML instead of CSV for {file_url}")

    with open(destination, "wb") as f:
        f.write(csv_response.content)


def parse_effective_date(info_text: str) -> date | None:
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", info_text)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    return date(year, month, day)


def main() -> None:
    print("1. Fetching InPost page via ScraperAPI...")
    response = fetch_via_scraperapi(PAGE_URL, render_js=False)
    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form", class_="pickup--hours")

    if not form:
        print(" -> Form not found in static HTML, retrying with JS rendering...")
        response = fetch_via_scraperapi(PAGE_URL, render_js=True)
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form", class_="pickup--hours")

    if not form:
        raise RuntimeError("Could not find the 'pickup--hours' form on page.")

    current_ref = form.get("data-csv-file", "").strip()
    new_ref = form.get("data-new-csv-file", "").strip()
    announcement = form.get("data-new-csv-info", "").strip()

    if not current_ref:
        raise RuntimeError("No 'data-csv-file' attribute found.")

    effective_date = parse_effective_date(announcement) if new_ref else None
    today = date.today()

    meta = {
        "announcement": None,
        "effective_date": None,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if new_ref and (effective_date is None or today >= effective_date):
        download_csv(new_ref, CURRENT_FILE)
        if os.path.exists(UPCOMING_FILE):
            os.remove(UPCOMING_FILE)
    else:
        download_csv(current_ref, CURRENT_FILE)

        if new_ref and effective_date and today < effective_date:
            download_csv(new_ref, UPCOMING_FILE)
            meta["announcement"] = announcement
            meta["effective_date"] = effective_date.isoformat()
        elif os.path.exists(UPCOMING_FILE):
            os.remove(UPCOMING_FILE)

    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Done. Metadata saved to {META_FILE}.")


if __name__ == "__main__":
    main()