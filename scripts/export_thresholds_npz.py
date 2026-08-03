#!/usr/bin/env python3
"""Export a processed thresholds NetCDF to a compact numpy .npz + meta sidecar.

The Vercel/serverless build reads the .npz with numpy only (no netCDF4/xarray/
pandas), which keeps the function bundle small. Run offline whenever the
processed .nc changes.

Usage:
    python scripts/export_thresholds_npz.py [path/to/thresholds.nc]
    # default: both provisional and full processed files if present
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import xarray as xr

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
META_KEYS = ["baseline_status", "baseline_years", "baseline_year_count",
             "expected_baseline", "expected_year_count", "threshold_version",
             "provisional", "tn90_status", "source_dataset", "created_utc",
             "WARNING_partial_baseline"]


def export(nc_path: Path) -> Path:
    ds = xr.open_dataset(nc_path)
    npz = nc_path.with_suffix(".npz")
    np.savez_compressed(
        npz,
        tx90=ds["tx90"].values.astype("float32"),
        tx95=ds["tx95"].values.astype("float32"),
        tx99=ds["tx99"].values.astype("float32"),
        tn90=ds["tn90"].values.astype("float32"),
        lat=ds["lat"].values.astype("float32"),
        lon=ds["lon"].values.astype("float32"),
        dayofyear=ds["dayofyear"].values.astype("int16"),
    )
    meta = {k: str(ds.attrs[k]) for k in META_KEYS if k in ds.attrs}
    npz.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    ds.close()
    print(f"wrote {npz} ({npz.stat().st_size/1e6:.2f} MB) + meta")
    return npz


def main() -> int:
    if len(sys.argv) > 1:
        export(Path(sys.argv[1]))
        return 0
    found = False
    for name in ("ukraine_heat_thresholds_1991_2020.nc",
                 "ukraine_heat_thresholds_2020_provisional.nc"):
        p = PROCESSED / name
        if p.exists():
            export(p)
            found = True
    if not found:
        print("no processed .nc files found in", PROCESSED)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
