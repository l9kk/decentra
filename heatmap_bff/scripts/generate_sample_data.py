"""Generate a small synthetic mobility tracks CSV for demo purposes.

Creates ./data/tracks.csv with randomized pseudo-mobility points clustered around
Astana center (approx 51.169, 71.449) so the heatmap endpoints work out-of-box.

Usage:
  python scripts/generate_sample_data.py --rows 50000
"""

from __future__ import annotations
import argparse
import os
import csv
import math
import random
from datetime import datetime, timedelta

CENTER_LAT = 51.169
CENTER_LNG = 71.449

# Slight lat/lng deltas to simulate movement (degrees ~ about ~111km per degree lat)
# We'll make a few hotspot centers to create variation.
HOTSPOTS = [
    (CENTER_LAT, CENTER_LNG),
    (CENTER_LAT + 0.05, CENTER_LNG + 0.10),
    (CENTER_LAT - 0.04, CENTER_LNG + 0.07),
    (CENTER_LAT + 0.03, CENTER_LNG - 0.05),
]


def random_point() -> tuple[float, float]:
    base_lat, base_lng = random.choice(HOTSPOTS)
    # Local jitter ~ few hundred meters
    lat = base_lat + random.uniform(-0.01, 0.01)
    lng = base_lng + random.uniform(-0.01, 0.01)
    return lat, lng


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows", type=int, default=20000, help="Number of synthetic rows"
    )
    parser.add_argument(
        "--out", type=str, default="./data/tracks.csv", help="Output CSV path"
    )
    parser.add_argument(
        "--users", type=int, default=800, help="Approx unique randomized_id values"
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    random.seed(42)
    start_time = datetime.utcnow() - timedelta(hours=2)

    fieldnames = ["randomized_id", "lat", "lng", "alt", "spd", "azm", "ts"]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i in range(args.rows):
            lat, lng = random_point()
            rid = f"u{random.randint(1, args.users)}"
            # Very rough pseudo values
            alt = random.uniform(300, 360)  # meters
            spd = max(0.0, random.gauss(30, 10))  # km/h
            azm = random.uniform(0, 359)
            ts = start_time + timedelta(seconds=i * 2)
            writer.writerow(
                {
                    "randomized_id": rid,
                    "lat": lat,
                    "lng": lng,
                    "alt": round(alt, 2),
                    "spd": round(spd, 2),
                    "azm": round(azm, 1),
                    "ts": ts.isoformat(),
                }
            )

    print(f"Wrote {args.rows} rows to {args.out}")


if __name__ == "__main__":
    main()
