#!/usr/bin/env python3
"""Robust, resumable ERA5-Land daily 2 m temperature download for Ukraine.

Design (per the hardening requirements):
  * One independent request per (year, daily_statistic).
  * Files saved as tmax_YYYY.nc / tmin_YYYY.nc, written atomically.
  * Every file is VALIDATED (see era5_common.validate_netcdf) before it counts
    as complete; already-valid files are skipped so the run is resumable.
  * Bounded retries: 8 attempts per request with exponential backoff.
  * The cdsapi client's own retry loop is kept short so failures surface to our
    backoff quickly (no blind 500-retry).
  * A manifest (data/raw/era5_land/manifest.json) records status/size/checksum/
    dims/coverage/units/timestamp/error for every request.
  * A failed year is recorded and the run continues with the other years.

Usage:
    python scripts/download_era5_land.py                 # 1991-2020, tmax+tmin
    python scripts/download_era5_land.py --years 1991-1995
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from era5_common import (
    RAW_DIR,
    load_manifest,
    record,
    save_manifest,
    sha256_of,
    validate_netcdf,
)

DATASET = "derived-era5-land-daily-statistics"
VARIABLE = "2m_temperature"
AREA = [53, 22, 44, 41]  # N, W, S, E
ALL_MONTHS = [f"{m:02d}" for m in range(1, 13)]
ALL_DAYS = [f"{d:02d}" for d in range(1, 32)]
STATS = ["daily_maximum", "daily_minimum"]
MAX_ATTEMPTS = 8
BACKOFF_BASE = 10   # seconds
BACKOFF_CAP = 300


def parse_years(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def tag_for(stat: str) -> str:
    return "tmax" if stat == "daily_maximum" else "tmin"


def target_path(year: int, stat: str) -> Path:
    return RAW_DIR / f"{tag_for(stat)}_{year}.nc"


def build_request(year: int, stat: str) -> dict:
    return {
        "variable": [VARIABLE],
        "year": str(year),
        "month": ALL_MONTHS,
        "day": ALL_DAYS,
        "daily_statistic": stat,
        "time_zone": "utc+00:00",
        "frequency": "1_hourly",
        "area": AREA,
        "data_format": "netcdf",
    }


def make_client():
    import cdsapi
    # Keep the client's internal retries short; our outer loop owns backoff.
    try:
        return cdsapi.Client(retry_max=2, sleep_max=20, timeout=600, quiet=True)
    except TypeError:
        # Older/newer signature fallback.
        return cdsapi.Client()


def fetch_one(client, year: int, stat: str, man: dict) -> str:
    """Return 'cached' | 'downloaded' | 'failed' and update the manifest."""
    out = target_path(year, stat)
    label = f"{tag_for(stat)}_{year}"

    # Skip if an already-valid file exists.
    if out.exists():
        ok, info = validate_netcdf(out, year)
        if ok:
            info["checksum_sha256"] = man["entries"].get(label, {}).get("checksum_sha256")
            record(man, year, stat, "complete", info)
            return "cached"

    last_err = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tmp = out.with_suffix(".nc.part")
        try:
            client.retrieve(DATASET, build_request(year, stat), str(tmp))
            ok, info = validate_netcdf(tmp, year)
            if not ok:
                last_err = info.get("error", "validation failed")
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"validation: {last_err}")
            info["checksum_sha256"] = sha256_of(tmp)
            tmp.replace(out)          # atomic: only a validated file gets the name
            info["path"] = str(out)
            record(man, year, stat, "complete", info)
            save_manifest(man)
            return "downloaded"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            Path(str(out) + ".part").unlink(missing_ok=True)
            if attempt < MAX_ATTEMPTS:
                delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
                print(f"[RETRY] {label}: attempt {attempt}/{MAX_ATTEMPTS} failed "
                      f"({last_err}); backoff {delay}s", flush=True)
                time.sleep(delay)

    record(man, year, stat, "failed", {"path": str(out)}, error=last_err)
    save_manifest(man)
    return "failed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1991-2020")
    ap.add_argument("--stats", default=",".join(STATS))
    args = ap.parse_args()

    years = parse_years(args.years)
    stats = [s.strip() for s in args.stats.split(",") if s.strip()]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    man = load_manifest()
    client = make_client()

    counts = {"downloaded": 0, "cached": 0, "failed": 0}
    failed_years = []
    for year in years:
        for stat in stats:
            label = f"{tag_for(stat)}_{year}"
            status = fetch_one(client, year, stat, man)
            counts[status] += 1
            if status == "failed":
                failed_years.append(label)
                print(f"[FAIL ] {label}: giving up after {MAX_ATTEMPTS} attempts", flush=True)
            else:
                e = man["entries"][label]
                print(f"[{status.upper():9s}] {label}: "
                      f"{(e.get('file_size') or 0)/1e6:.2f} MB "
                      f"coverage={e.get('date_coverage')}", flush=True)
    save_manifest(man)
    print(f"\nSummary: downloaded={counts['downloaded']} cached={counts['cached']} "
          f"failed={counts['failed']}")
    if failed_years:
        print("Failed:", ", ".join(failed_years))
    return 0


if __name__ == "__main__":
    sys.exit(main())
