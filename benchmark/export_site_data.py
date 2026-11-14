"""Regenerate the figures and data the README and the site show.

Solves Cordeau a2-16 with the exact CP-SAT model, verifies the plan with the
independent verifier and writes:

* ``site/data/a2-16.json``: instance, verified optimal routes, service starts;
* ``docs/img`` and ``site/assets``: route map and timeline SVGs.

Usage:
  python benchmark/export_site_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

from mobiroute.benchmarks.cordeau_exact import (
    REFERENCES,
    load_cordeau_bytes,
    solve_exact_cpsat,
    verify_routes,
)
from mobiroute.reporting.svg import route_map_svg, timeline_svg

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = ROOT / "benchmark" / "instances" / "cordeau" / "a2-16.txt"


def main() -> None:
    instance, digest = load_cordeau_bytes(INSTANCE.read_bytes(), instance_id="a2-16")
    run = solve_exact_cpsat(instance, time_limit_s=60.0, workers=1)
    verdict = verify_routes(instance, run.routes)
    if not (verdict.feasible and verdict.full_service):
        raise SystemExit(f"plan not verified: {verdict.violations}")
    reference = REFERENCES[digest]
    payload = {
        "id": instance.instance_id,
        "sha256": digest,
        "published": reference.objective,
        "n": instance.n_requests,
        "vehicles": instance.n_vehicles,
        "capacity": instance.capacity,
        "maxRide": instance.max_ride_time,
        "maxDuration": instance.max_route_duration,
        "nodes": [
            {
                "x": node.x,
                "y": node.y,
                "service": node.service,
                "load": node.load,
                "earliest": node.earliest,
                "latest": node.latest,
            }
            for node in instance.nodes
        ],
        "routes": run.routes,
        "starts": [schedule.service_start for schedule in verdict.routes],
        "cost": verdict.cost,
        "solver": {"status": run.status, "seconds": run.wall_clock_seconds},
    }
    data = ROOT / "site" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "a2-16.json").write_text(
        json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    title = f"Cordeau a2-16: verified optimal plan, cost {verdict.cost:.2f}"
    routes_svg = route_map_svg(instance, verdict, title=title)
    timeline = timeline_svg(instance, verdict, title="Cordeau a2-16: when each request is served")
    for folder in (ROOT / "docs" / "img", ROOT / "site" / "assets"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a2-16-routes.svg").write_text(routes_svg, encoding="utf-8")
        (folder / "a2-16-timeline.svg").write_text(timeline, encoding="utf-8")
    print(f"a2-16: cost {verdict.cost:.5f}, status {run.status}, sha256 {digest[:12]}")


if __name__ == "__main__":
    main()
