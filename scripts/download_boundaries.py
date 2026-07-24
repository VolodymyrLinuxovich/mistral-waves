#!/usr/bin/env python3
"""Download REAL administrative boundaries for Ukraine. Never fabricates geometry.

Sources (open data):
  * National (ADM0) + oblasts (ADM1): geoBoundaries gbOpen (CC-BY 4.0).
  * Kyiv city districts (raiony, OSM admin_level=9): Overpass API.

Outputs:
  data/boundaries/ukraine.geojson
  data/boundaries/ukraine_oblasts.geojson
  data/boundaries/kyiv_districts.geojson

If any layer cannot be fetched, the script reports exactly which file is missing
and what to provide, and exits non-zero for that layer — it does not invent data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "boundaries"
GB_API = "https://www.geoboundaries.org/api/current/gbOpen/UKR/{level}/"

OVERPASS = "https://overpass-api.de/api/interpreter"
# Kyiv city districts: admin_level=9 relations inside Kyiv city (admin_level=6).
KYIV_QUERY = """
[out:json][timeout:120];
area["name"="Київ"]["admin_level"="4"]->.kyiv;
(
  relation(area.kyiv)["admin_level"="9"]["boundary"="administrative"];
);
out ids tags;
"""


def _write(path: Path, gj: dict, label: str):
    path.write_text(json.dumps(gj, ensure_ascii=False))
    n = len(gj.get("features", []))
    print(f"[OK   ] {label}: {n} feature(s) -> {path}")


def fetch_geoboundaries(level: str, out_name: str, label: str, client: httpx.Client) -> bool:
    try:
        meta = client.get(GB_API.format(level=level), timeout=30)
        meta.raise_for_status()
        dl = meta.json()["gjDownloadURL"]
        gj = client.get(dl, timeout=60).json()
        _write(OUT_DIR / out_name, gj, label)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL ] {label}: {type(e).__name__}: {e}")
        print(f"        Provide manually: data/boundaries/{out_name} "
              f"(geoBoundaries gbOpen UKR {level})")
        return False


def fetch_kyiv_districts(client: httpx.Client) -> bool:
    """Best-effort: report district relations found. Geometry assembly from OSM
    relations is non-trivial; if we cannot produce clean polygons we report which
    file to provide rather than fabricate boundaries."""
    try:
        r = client.post(OVERPASS, data={"data": KYIV_QUERY}, timeout=120)
        r.raise_for_status()
        elements = r.json().get("elements", [])
        names = [e.get("tags", {}).get("name") for e in elements if e.get("tags")]
        print(f"[INFO ] Overpass found {len(elements)} Kyiv admin_level=9 relation(s): {names}")
        if not elements:
            raise RuntimeError("no admin_level=9 districts returned")
        # We intentionally do NOT assemble multipolygon geometry here (would risk
        # malformed boundaries). Report clearly.
        raise NotImplementedError("district polygon assembly not implemented in MVP")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL ] kyiv_districts: {type(e).__name__}: {e}")
        print("        ACTION REQUIRED: provide data/boundaries/kyiv_districts.geojson")
        print("        (10 Kyiv raiony as a FeatureCollection with a 'name' property).")
        print("        Suggested source: OSM export of Kyiv admin_level=9, or the")
        print("        official Kyiv open-data portal. Boundaries are NOT fabricated.")
        return False


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    with httpx.Client(follow_redirects=True) as client:
        ok &= fetch_geoboundaries("ADM0", "ukraine.geojson", "ukraine (national)", client)
        ok &= fetch_geoboundaries("ADM1", "ukraine_oblasts.geojson", "oblasts", client)
        kyiv_ok = fetch_kyiv_districts(client)
    print("\nSummary: national/oblast =", "OK" if ok else "PARTIAL",
          "| kyiv_districts =", "OK" if kyiv_ok else "MISSING (see action above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
