"""Stress-day generator shape. Full 200-vehicle solve is a benchmark, not CI."""

from __future__ import annotations

from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.adapters.stress_day import N_REQUESTS, N_VEHICLES, generate_stress_day, inventory
from mobiroute.adapters.synthetic_data import MODES, generate_day


def test_stress_200_in_modes() -> None:
    assert "stress_200" in MODES


def test_stress_200_shape_and_determinism() -> None:
    p = generate_day("stress_200", seed=42)
    q = generate_stress_day(42)
    assert len(p.vehicles) == N_VEHICLES == 200
    assert len(p.requests) == N_REQUESTS == 3200
    assert all(v.depot_id in p.travel.zones for v in p.vehicles)
    assert all(t.pickup_zone in p.travel.zones for t in p.requests)
    inv = inventory(p)
    assert inv["via_trips"] > 0
    assert inv["wait_return"] > 0
    assert inv["quota"] > 0
    assert inv["wav_vehicles"] > 0
    assert inv["dead_vehicles"] > 0
    assert inv["shop_unavail"] > 0
    assert inv["restricted_area"] > 0
    assert inv["untrained_drivers"] > 0
    assert inv["unavailable_drivers"] > 0
    assert inv["cancelled"] > 0
    assert inv["no_show"] > 0
    assert inv["stretcher"] > 0
    assert inv["scooter"] > 0
    assert inv["medical"] > 0
    assert fingerprint(p.model_dump(mode="json")) == fingerprint(q.model_dump(mode="json"))
    other = generate_stress_day(43)
    assert fingerprint(p.model_dump(mode="json")) != fingerprint(other.model_dump(mode="json"))
