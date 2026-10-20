from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv
import re

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "historical"
OUTPUT = DATA_DIR / "pune_station_hourly_aqi.csv"

FILES = {
    "5ec1c512-c3f1-4ef6-81eb-4a5147241377.csv": "Hadapsar IITM",
    "6c9be432-4a82-4661-972f-e4ac9be0d252.csv": "Bhosari IITM",
    "f421cdb4-57de-42ad-bd16-0bfd54e79cae.csv": "Karve Road MPCB",
}

MONTH_PATTERN = re.compile(
    r"^(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)-(\d{4})$",
    re.IGNORECASE,
)

tz = ZoneInfo("Asia/Kolkata")
output_rows = []
seen = set()

for filename, station in FILES.items():
    path = DATA_DIR / filename

    if not path.exists():
        print(f"SKIPPED: file not found: {filename}")
        continue

    current_month = None
    station_count = 0

    with path.open(
        "r", encoding="utf-8-sig", errors="replace", newline=""
    ) as f:
        for row in csv.reader(f):
            cells = [x.strip() for x in row]

            if not cells or not cells[0]:
                continue

            month_match = MONTH_PATTERN.match(cells[0])
            if month_match:
                current_month = datetime.strptime(
                    cells[0], "%B-%Y"
                ).replace(day=1)
                continue

            if current_month is None or not cells[0].isdigit():
                continue

            day = int(cells[0])

            for hour, raw_value in enumerate(cells[1:25]):
                if not raw_value:
                    continue

                try:
                    value = float(raw_value)
                except ValueError:
                    continue

                try:
                    local_time = datetime(
                        current_month.year,
                        current_month.month,
                        day,
                        hour,
                        tzinfo=tz,
                    )
                except ValueError:
                    continue

                key = (station, local_time.isoformat())

                if key in seen:
                    continue

                seen.add(key)
                output_rows.append({
                    "timestamp": local_time.isoformat(),
                    "station": station,
                    "aqi": value,
                    "source_file": filename,
                })
                station_count += 1

    print(f"{station}: {station_count:,} hourly readings")

output_rows.sort(key=lambda r: (r["timestamp"], r["station"]))

with OUTPUT.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["timestamp", "station", "aqi", "source_file"],
    )
    writer.writeheader()
    writer.writerows(output_rows)

print(f"\nTotal hourly readings: {len(output_rows):,}")
print(f"Saved to: {OUTPUT}")
print("Original station files were not modified.")
