"""Generate the SYNTHETIC test fixtures. Nothing here is real wildfire data.

Every fire is named TEST-something so a fixture can never be mistaken for a real record.
Run once (``python tests/fixtures/make_fixtures.py``); the outputs are committed.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "data"
random.seed(20260920)

STATUSES = ["Out of Control", "Being Held", "Under Control", "Out"]
CAUSES = ["Lightning", "Person", "Undetermined"]
CENTRES = ["1", "2", "3", "4", "5", "6"]


def points() -> dict:
    features = []
    for i in range(40):
        lon = round(random.uniform(-127.5, -116.0), 5)
        lat = round(random.uniform(49.2, 58.5), 5)
        status = random.choices(STATUSES, weights=[3, 4, 5, 8])[0]
        size = round(random.choice([0.01, 0.1, 0.5, 2, 15, 120, 900, 5400, 21000]) * random.uniform(0.5, 1.5), 3)
        number = f"T{40000 + i}"
        features.append({
            "type": "Feature",
            "id": f"PROT_CURRENT_FIRE_PNTS_SP.{i}",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "FIRE_NUMBER": number,
                "FIRE_YEAR": 2026,
                "FIRE_STATUS": status,
                "FIRE_CAUSE": random.choice(CAUSES),
                "FIRE_CENTRE": int(random.choice(CENTRES)),
                "ZONE": random.randint(1, 4),
                "INCIDENT_NAME": f"TEST-{i:02d}" if i % 3 == 0 else number,
                "GEOGRAPHIC_DESCRIPTION": f"Synthetic location {i}",
                "LATITUDE": lat,
                "LONGITUDE": lon,
                "CURRENT_SIZE": size,
                "IGNITION_DATE": f"2026-0{random.randint(6, 8)}-{random.randint(10, 28)}Z",
                "FIRE_URL": f"https://wildfiresituation.nrs.gov.bc.ca/incidents?fireYear=2026&incidentNumber={number}",
                "FIRE_OF_NOTE_IND": "Y" if status == "Out of Control" and size > 5000 else "N",
                "OBJECTID": 1000 + i,
            },
        })
    # One fire with an HTML-looking name, to prove popups escape their content.
    features[1]["properties"]["INCIDENT_NAME"] = "<b>TEST</b> & <script>alert(1)</script>"
    return {"type": "FeatureCollection", "features": features}


def perimeters(pts: dict) -> dict:
    feats = []
    for f in pts["features"]:
        props = f["properties"]
        if props["CURRENT_SIZE"] < 100:
            continue
        lon, lat = f["geometry"]["coordinates"]
        d = min(0.4, 0.03 + props["CURRENT_SIZE"] / 60000)
        ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
        feats.append({
            "type": "Feature", "id": f"PROT_CURRENT_FIRE_POLYS_SP.{props['OBJECTID']}",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"FIRE_NUMBER": props["FIRE_NUMBER"], "FIRE_STATUS": props["FIRE_STATUS"],
                           "FIRE_SIZE_HECTARES": props["CURRENT_SIZE"], "OBJECTID": props["OBJECTID"]},
        })
    return {"type": "FeatureCollection", "features": feats}


def evacuations() -> dict:
    def poly(lon, lat, d=0.25):
        return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d],
                                                    [lon, lat + d], [lon, lat]]]}
    rows = [
        ("Synthetic Area A", "Wildfire", "Order", 120, 310, -122.0, 51.0),
        ("Synthetic Area B", "Wildfire", "Order", 45, 100, -120.5, 50.0),
        ("Synthetic Area C", "Wildfire", "Alert", 300, 800, -124.0, 53.5),
        ("Synthetic Area D", "Wildfire", "Alert", 20, 40, -119.0, 55.0),
        ("Synthetic Area E", "Wildfire", "All Clear", 10, 20, -126.0, 52.0),
        ("Synthetic Area F", "Landslide", "Order", 5, 9, -123.0, 49.5),
    ]
    feats = []
    for i, (name, kind, status, homes, pop, lon, lat) in enumerate(rows, start=1):
        feats.append({
            "type": "Feature", "id": i, "geometry": poly(lon, lat),
            "properties": {
                "EMRG_OAA_SYSID": i, "EVENT_NAME": f"TEST {kind} {i}", "EVENT_NUMBER": None,
                "EVENT_TYPE": kind, "ORDER_ALERT_NAME": name, "ORDER_ALERT_STATUS": status,
                "ISSUING_AGENCY": "Synthetic Regional District", "MULTI_SOURCED_POPULATION": pop,
                "MULTI_SOURCED_HOMES": homes, "DATE_MODIFIED": 1789000000000 + i * 3600000,
                "EVENT_START_DATE": 1788000000000 + i * 86400000, "OBJECTID": i,
            },
        })
    return {"type": "FeatureCollection", "features": feats}


def hotspots() -> dict:
    feats = []
    for i in range(25):
        lon = round(random.uniform(-125.0, -117.0), 5)
        lat = round(random.uniform(50.0, 56.0), 5)
        feats.append({"type": "Feature", "id": f"hotspots_24h.{i}",
                      "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"lat": lat, "lon": lon}})
    return {"type": "FeatureCollection", "features": feats}


def history() -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=14, freq="D")
    rows = []
    active, ha = 60, 90000.0
    for d in dates:
        active = max(10, active + random.randint(-6, 8))
        ha += random.uniform(1500, 9000)
        rows.append({
            "date": d.strftime("%Y-%m-%d"), "fires_season": 1380 + len(rows) * 2, "fires_active": active,
            "fires_out_of_control": max(0, active // 8), "hectares_season": round(ha, 1),
            "evac_orders": random.randint(0, 7), "evac_alerts": random.randint(0, 12),
            "hotspots_bc_24h": random.randint(20, 400),
        })
    return pd.DataFrame(rows)


def write(name: str, obj) -> None:
    (OUT / "live").mkdir(parents=True, exist_ok=True)
    (OUT / "live" / name).write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    pts = points()
    write("bc_fire_points.geojson", pts)
    write("bc_fire_perimeters.geojson", perimeters(pts))
    write("bc_evac_orders.geojson", evacuations())
    write("cwfis_hotspots.geojson", hotspots())
    (OUT / "history").mkdir(parents=True, exist_ok=True)
    history().to_parquet(OUT / "history" / "daily_summary.parquet", index=False)
    print("fixtures written to", OUT)
