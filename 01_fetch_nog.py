# /// script
# requires-python = ">=3.10"
# dependencies = ["patchright", "beautifulsoup4"]
# ///

import os
import subprocess
import sys
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright

PAGE_URL = "https://inpost.pl/godziny-odbiorow"
OUTPUT_DIR = "data_raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nog_current.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def ensure_chromium() -> None:
    subprocess.run(
        [sys.executable, "-m", "patchright", "install", "chromium"],
        check=True,
    )


def main() -> None:
    ensure_chromium()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        print("1. Opening InPost page in headless Chromium...")
        page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45000)

      
        page.wait_for_selector("form.pickup--hours", state="attached", timeout=30000)

        soup = BeautifulSoup(page.content(), "html.parser")
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
        csv_response = context.request.get(
            file_url,
            headers={"Referer": PAGE_URL},
            timeout=30000,
        )

        if not csv_response.ok:
            raise RuntimeError(f"Failed to download CSV: HTTP {csv_response.status}")

        content = csv_response.body()
        content_type = csv_response.headers.get("content-type", "")
        if "text/html" in content_type.lower():
            raise RuntimeError("Received HTML instead of CSV (likely blocked by WAF).")

        with open(OUTPUT_FILE, "wb") as f:
            f.write(content)

        browser.close()

    size_kb = len(content) // 1024
    print(f"Done. Saved to {OUTPUT_FILE} ({size_kb} KB).")


if __name__ == "__main__":
    main()
