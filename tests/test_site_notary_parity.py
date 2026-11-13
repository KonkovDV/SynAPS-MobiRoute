"""The in-browser notary (site/assets/notary.mjs) must agree with the Python one.

Every single-stop move inside both optimal a2-16 routes is verified by both
implementations: same verdict, same cost, same missing minutes, same conflict.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mobiroute.benchmarks.cordeau_exact import load_cordeau_bytes, verify_routes

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "site" / "data" / "a2-16.json"
_NOTARY = _ROOT / "site" / "assets" / "notary.mjs"

_SCRIPT = """
import { readFileSync } from "node:fs";
const { verifyRoute } = await import(process.argv.at(-2));
const inst = JSON.parse(readFileSync(process.argv.at(-1), "utf8"));
const cases = JSON.parse(readFileSync(0, "utf8"));
const out = cases.map((route) => {
  const v = verifyRoute(inst, route);
  return {
    feasible: v.feasible,
    violations: v.violations.filter((x) => x !== "SCHEDULE_INFEASIBLE").sort(),
    cost: v.cost,
    shortBy: v.certificate ? v.certificate.shortBy : null,
    constraints: v.certificate ? [...v.certificate.constraints].sort() : [],
  };
});
process.stdout.write(JSON.stringify(out));
"""


def _moves(route: list[int]) -> list[list[int]]:
    cases = [list(route)]
    for i in range(len(route)):
        for j in range(len(route)):
            if i != j:
                moved = list(route)
                moved.insert(j, moved.pop(i))
                cases.append(moved)
    return cases


def test_browser_notary_matches_python_on_every_single_move() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    raw = (_ROOT / "benchmark" / "instances" / "cordeau" / "a2-16.txt").read_bytes()
    instance, digest = load_cordeau_bytes(raw, instance_id="a2-16")
    assert data["sha256"] == digest
    cases = [case for route in data["routes"] for case in _moves(route)]
    assert len(cases) > 500

    done = subprocess.run(
        [node, "--input-type=module", "-e", _SCRIPT, _NOTARY.as_uri(), str(_DATA)],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    browser = json.loads(done.stdout)
    assert len(browser) == len(cases)

    infeasible = 0
    for route, js in zip(cases, browser, strict=True):
        verdict = verify_routes(instance, [route])
        structural = sorted(
            v.replace(":0:", ":", 1) for v in verdict.violations if not v.startswith("SCHEDULE")
        )
        assert js["violations"] == structural, route
        assert js["feasible"] == verdict.feasible, route
        assert js["cost"] == pytest.approx(verdict.cost, abs=1e-5)
        if verdict.certificates:
            infeasible += 1
            (cert,) = verdict.certificates
            assert js["shortBy"] == pytest.approx(cert.short_by, abs=1e-5)
            assert js["constraints"] == sorted(cert.constraints)
        else:
            assert js["shortBy"] is None
    assert infeasible > 100
