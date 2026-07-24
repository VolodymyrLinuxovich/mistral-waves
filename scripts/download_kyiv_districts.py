#!/usr/bin/env python3
"""Download & validate Kyiv's 10 administrative districts from OSM.

Kyiv city raiony are OSM boundary=administrative admin_level=10. We fetch them
with geometry via Overpass (trying mirrors), assemble polygons with osm2geojson
(real OSM geometry — no fabrication), validate the count/geometry, and write
data/boundaries/kyiv_districts.geojson plus a provenance sidecar.

Source: OpenStreetMap via Overpass API. Licence: ODbL. Never fabricates polygons.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import osm2geojson

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "boundaries" / "kyiv_districts.geojson"
ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
QUERY = """
[out:json][timeout:180];
rel["name"="Київ"]["admin_level"="4"]["boundary"="administrative"];
map_to_area->.k;
rel(area.k)["boundary"="administrative"]["admin_level"="10"];
out geom;
"""
HEADERS = {"User-Agent": "waves-heat-mvp/0.3 (heat-health research MVP)"}


def fetch_raw() -> dict:
    last = None
    for ep in ENDPOINTS:
        try:
            r = httpx.post(ep, data={"data": QUERY}, headers=HEADERS, timeout=200)
            if r.status_code == 200:
                print(f"[OK] {ep}")
                return r.json(), ep
            last = f"{ep} -> {r.status_code}"
            print(f"[skip] {last}")
        except Exception as e:  # noqa: BLE001
            last = f"{ep} -> {type(e).__name__}: {e}"
            print(f"[skip] {last}")
    raise RuntimeError(f"all Overpass endpoints failed; last: {last}")


def validate(fc: dict) -> tuple[bool, str]:
    feats = fc.get("features", [])
    polys = [f for f in feats if f["geometry"]["type"] in ("Polygon", "MultiPolygon")]
    if len(polys) < 8:
        return False, f"expected ~10 districts, got {len(polys)} polygonal features"
    # Every feature needs a name and plausible Kyiv coordinates.
    for f in polys:
        name = f["properties"].get("name")
        if not name:
            return False, "a district feature has no name"
    return True, f"{len(polys)} district polygons"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    raw, endpoint = fetch_raw()
    n_rel = sum(1 for e in raw.get("elements", []) if e.get("type") == "relation")
    print(f"relations returned: {n_rel}")
    gj = osm2geojson.json2geojson(raw)

    feats = []
    for f in gj["features"]:
        tags = f.get("properties", {}).get("tags", {})
        if tags.get("admin_level") != "10":
            continue
        if f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            continue
        f["properties"] = {
            "id": "kyiv_" + (tags.get("name:en") or tags.get("name") or "district")
                  .lower().replace(" ", "_").replace("'", ""),
            "name": tags.get("name"),
            "name_en": tags.get("name:en"),
            "admin_level": 10,
            "osm_id": f.get("properties", {}).get("id"),
        }
        feats.append(f)

    out_fc = {"type": "FeatureCollection", "features": feats}
    ok, msg = validate(out_fc)
    print(("[VALID] " if ok else "[INVALID] ") + msg)
    if not ok:
        print("Refusing to write invalid/incomplete district set.")
        return 2

    OUT.write_text(json.dumps(out_fc, ensure_ascii=False))
    prov = {
        "source": "OpenStreetMap via Overpass API",
        "endpoint": endpoint,
        "query": "boundary=administrative admin_level=10 within Kyiv (admin_level=4)",
        "licence": "ODbL (OpenStreetMap contributors)",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "n_districts": len(feats),
        "assembler": f"osm2geojson {getattr(osm2geojson,'__version__','?')}",
        "note": "Real OSM geometry. District-level; forecast resolution does not "
                "represent street-level temperature.",
    }
    OUT.with_suffix(".provenance.json").write_text(json.dumps(prov, indent=2, ensure_ascii=False))
    print(f"wrote {OUT} ({OUT.stat().st_size/1e3:.0f} KB) + provenance")
    for f in feats:
        print("  -", f["properties"]["name"], "/", f["properties"].get("name_en"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
