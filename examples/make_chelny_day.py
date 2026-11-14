"""Write ``chelny-day.geo.json``: a synthetic delivery day in Naberezhnye Chelny.

Every place is a random point inside the city's rough bounding box; the
names say "условн." (conventional) on purpose. Nothing here describes a real
company, its customers or its orders. The day: one warehouse, three
suppliers, 45 orders (deliveries from the warehouse and supplier-to-customer
transfers) in morning, midday and afternoon slots; own and hired vans and
trucks; the 4.5 h / 45 min rest rule; vans may run two trips.

Usage:
  python examples/make_chelny_day.py [--seed 1] [--orders 45]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BOX = ((55.690, 55.785), (52.270, 52.540))  # lat, lon


def point(rng: random.Random) -> dict[str, float]:
    (lat0, lat1), (lon0, lon1) = BOX
    return {"lat": round(rng.uniform(lat0, lat1), 5), "lon": round(rng.uniform(lon0, lon1), 5)}


def day(seed: int, n_orders: int) -> dict[str, Any]:
    rng = random.Random(seed)
    suppliers = [{**point(rng), "name": f"Поставщик {k} (условн.)"} for k in (1, 2, 3)]
    slots = [("08:00", "11:00"), ("11:00", "14:00"), ("14:00", "18:00"), ("08:00", "18:00")]
    orders = []
    for k in range(1, n_orders + 1):
        kg = round(rng.uniform(60, 1400), 1)
        demand = [kg, round(kg / rng.uniform(220, 320), 2), float(max(1, math.ceil(kg / 500)))]
        skills = []
        if rng.random() < 0.15:
            skills.append("cold")
        if kg < 900 and rng.random() < 0.2:
            skills.append("tail_lift")
        lo, hi = rng.choice(slots)
        delivery = {**point(rng), "from": lo, "to": hi, "service_min": round(10 + 4 * demand[2])}
        delivery["name"] = f"Клиент {k} (условн.)"
        order: dict[str, Any] = {"id": f"Z{k:03d}", "delivery": delivery, "demand": demand}
        if skills:
            order["skills"] = skills
        if rng.random() < 0.3:
            sup = rng.choice(suppliers)
            order["pickup"] = {
                "lat": sup["lat"],
                "lon": sup["lon"],
                "from": "07:30",
                "to": "12:00",
                "service_min": 15,
                "name": sup["name"],
            }
            # Shift the drop-off slot so it can follow the pickup.
            delivery["from"], delivery["to"] = "10:00", "18:00"
        orders.append(order)
    return {
        "format": "mobiroute.vrp.geo.v1",
        "name": f"chelny-day-{seed}",
        "currency": "RUB",
        "dimensions": ["kg", "m3", "pallets"],
        "depots": [
            {"id": "WH", "lat": 55.7585, "lon": 52.4512, "open": "06:30", "close": "21:00",
             "name": "Склад (условн.)"}
        ],
        "orders": orders,
        "vehicle_types": [
            {"id": "van", "count": 4, "capacity": [1500, 9, 4], "depot": "WH",
             "shift": ["07:00", "20:00"], "max_duration_min": 600, "fixed_cost": 0,
             "cost_per_km": 18, "cost_per_hour": 450, "skills": ["tail_lift"], "profile": "van",
             "rests": {"max_driving_min": 270, "duration_min": 45},
             "trips": {"max": 2, "reload_min": 25}},
            {"id": "van-hired", "count": 3, "capacity": [1500, 9, 4], "depot": "WH",
             "shift": ["07:00", "20:00"], "max_duration_min": 600, "fixed_cost": 2500,
             "cost_per_km": 24, "cost_per_hour": 600, "skills": ["tail_lift"], "profile": "van",
             "hired": True, "rests": {"max_driving_min": 270, "duration_min": 45}},
            {"id": "truck", "count": 2, "capacity": [5000, 30, 12], "depot": "WH",
             "shift": ["07:00", "20:00"], "max_duration_min": 600, "fixed_cost": 0,
             "cost_per_km": 26, "cost_per_hour": 600, "skills": ["tail_lift", "cold"],
             "profile": "truck", "rests": {"max_driving_min": 270, "duration_min": 45}},
            {"id": "truck-hired", "count": 2, "capacity": [5000, 30, 12], "depot": "WH",
             "shift": ["07:00", "20:00"], "max_duration_min": 600, "fixed_cost": 4200,
             "cost_per_km": 35, "cost_per_hour": 810, "skills": ["tail_lift", "cold"],
             "profile": "truck", "hired": True,
             "rests": {"max_driving_min": 270, "duration_min": 45}},
        ],
        "profiles": {
            "van": {"speed_kmh": 30, "detour": 1.35},
            "truck": {"speed_kmh": 25, "detour": 1.35, "osrm_time_factor": 1.2},
        },
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--orders", type=int, default=45)
    ap.add_argument("--out", type=Path, default=HERE / "chelny-day.geo.json")
    args = ap.parse_args()
    args.out.write_text(
        json.dumps(day(args.seed, args.orders), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
