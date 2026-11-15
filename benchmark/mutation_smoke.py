"""Do the tests have teeth? Plant one bug at a time and see whether they notice.

Each mutant is one textual change in a source file (the verifier forgetting
capacity, insertion allowing a minute of lateness, a rest row missing from a
route sheet, ...). The relevant test modules run against it on the Python
reference; the file is restored from git afterwards, whatever happens. A
mutant that survives points at a check no test exercises.

Usage:
  python benchmark/mutation_smoke.py   (needs a clean git checkout of src/)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

MUTANTS = [
    (
        "verifier ignores capacity",
        "src/mobiroute/vrp/verify.py",
        "if value > cap + LOAD_EPS:",
        "if value > cap + 1e9:",
        ["tests/test_vrp_engine.py", "tests/test_vrp_insertion.py", "tests/test_vrp_rules.py"],
    ),
    (
        "verifier ignores precedence",
        "src/mobiroute/vrp/verify.py",
        "if position[req.pickup] > position[req.delivery]:",
        "if False:",
        ["tests/test_vrp_engine.py", "tests/test_vrp_kpi.py", "tests/test_vrp_insertion.py"],
    ),
    (
        "ride limit forgets the pickup service",
        "src/mobiroute/vrp/schedule.py",
        "limit = req.max_ride + inst.nodes[node].service",
        "limit = req.max_ride",
        ["tests/test_vrp_insertion.py", "tests/test_vrp_engine.py", "tests/test_cordeau_a2_16.py"],
    ),
    (
        "insertion allows 1 min late",
        "src/mobiroute/vrp/insertion.py",
        "if bu > lu + EPS or bu + su + tu[b] > late[i + 1] + EPS:",
        "if bu > lu + 1.0 or bu + su + tu[b] > late[i + 1] + 1.0:",
        ["tests/test_vrp_insertion.py", "tests/test_vrp_native.py"],
    ),
    (
        "shortest shift back to the first rest place",
        "src/mobiroute/vrp/schedule.py",
        "        if best.min_duration <= floor + TIME_EPS:\n            break",
        "        break",
        ["tests/test_vrp_robustness.py"],
    ),
    (
        "model accepts NaN demand",
        "src/mobiroute/vrp/model.py",
        "if len(req.demand) != dims or not all(_amount(q) for q in req.demand):",
        "if len(req.demand) != dims:",
        ["tests/test_vrp_robustness.py"],
    ),
    (
        "verifier skips unknown types without a violation",
        "src/mobiroute/vrp/verify.py",
        '            violations.append(f"UNKNOWN_VEHICLE_TYPE:{r_idx}")\n',
        "",
        ["tests/test_vrp_robustness.py"],
    ),
    (
        "empty legs counted as loaded",
        "src/mobiroute/vrp/kpi.py",
        "if any(q > LOADED_EPS for q in on_board):",
        "if True:",
        ["tests/test_vrp_kpi.py"],
    ),
    (
        "traffic arrival off by the boundary",
        "src/mobiroute/vrp/traffic.py",
        "        if room >= rest:\n            return x + rest / f",
        "        if room > rest + 1.0:\n            return x + rest / f",
        ["tests/test_vrp_rules.py", "tests/test_vrp_native.py"],
    ),
    (
        "OR-Tools serves optional orders",
        "src/mobiroute/vrp/ortools_baseline.py",
        "price = round(req.penalty * scale) if x == 0 else 0",
        "price = must_serve",
        ["tests/test_vrp_robustness.py"],
    ),
    (
        "split break never tried",
        "src/mobiroute/vrp/insertion.py",
        "    split = c.brk_split[t]\n    if split is not None:",
        "    split = c.brk_split[t]\n    if False:",
        ["tests/test_vrp_rules.py"],
    ),
    (
        "sheets drop the rest row",
        "src/mobiroute/vrp/sheets.py",
        "            if k == gap and rest_first:",
        "            if False:",
        ["tests/test_vrp_geo_sheets.py", "tests/test_vrp_rules.py"],
    ),
]


def main() -> int:
    survived = []
    for name, path, old, new, tests in MUTANTS:
        file = ROOT / path
        text = file.read_text()
        if text.count(old) != 1:
            print(f"SKIP {name}: pattern found {text.count(old)} times")
            continue
        file.write_text(text.replace(old, new))
        try:
            run = subprocess.run(
                [PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *tests],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "MOBIROUTE_DISABLE_NATIVE": "1"},
                timeout=1200,
            )
            killed = run.returncode != 0
        finally:
            subprocess.run(["git", "checkout", "--", path], cwd=ROOT, check=True)
        print(f"{'KILLED  ' if killed else 'SURVIVED'} {name}")
        if not killed:
            survived.append(name)
    print(f"{len(MUTANTS) - len(survived)} of {len(MUTANTS)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
