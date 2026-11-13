"""Literature-exact Cordeau lane: parser, difference-constraint notary, CP-SAT, gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from mobiroute.benchmarks.cordeau_exact import (
    CORDEAU_A2_16_SHA256,
    REFERENCES,
    build_literature_report,
    load_cordeau_bytes,
    parse_cordeau_instance,
    solve_exact_cpsat,
    verify_routes,
)

_ROOT = Path(__file__).resolve().parents[1]
_A2_16 = _ROOT / "benchmark" / "instances" / "cordeau" / "a2-16.txt"
_SUMS = _ROOT / "benchmark" / "instances" / "cordeau" / "SHA256SUMS.txt"

# K n T Q L, then id x y service load earliest latest. Everything on one line
# (x = 0), so every distance is exact: optimum [1, 3, 2, 4] costs 3+1+2+4+10 = 20.
TINY = """1 2 100 1 20
0 0 0 0 0 0 100
1 0 3 1 1 0 100
2 0 6 1 1 0 100
3 0 4 1 -1 0 100
4 0 10 1 -1 0 100
5 0 0 0 0 0 100
"""


def _tiny(**replace: str):
    text = TINY
    for old, new in replace.items():
        text = text.replace(old, new)
    return parse_cordeau_instance(text, instance_id="tiny")


def test_parser_rejects_malformed_files() -> None:
    cases = {
        "1 2 100 1\n": "CORDEAU_HEADER_MUST_BE_K_N_T_Q_L",
        TINY.replace("5 0 0 0 0 0 100\n", ""): "CORDEAU_EXPECTED_2N_PLUS_2_NODES",
        TINY.replace("2 0 6 1 1 0 100", "7 0 6 1 1 0 100"): "CORDEAU_NODE_IDS_MUST_BE_SEQUENTIAL",
        TINY.replace("4 0 10 1 -1 0 100", "4 0 10 1 -2 0 100"): "CORDEAU_PICKUP_DROPOFF_LOADS",
        TINY.replace("1 0 3 1 1 0 100", "1 0 3 1 1 50 10"): "CORDEAU_SERVICE_OR_WINDOW_INVALID",
        TINY.replace("1 0 3 1 1 0 100", "1 0 3 1 1 0"): "CORDEAU_NODE_LINE_MUST_HAVE_7_FIELDS",
    }
    for text, code in cases.items():
        with pytest.raises(ValueError, match=code):
            parse_cordeau_instance(text, instance_id="bad")


def test_verifier_accepts_the_hand_optimum_with_exact_cost() -> None:
    inst = _tiny()
    verdict = verify_routes(inst, [[1, 3, 2, 4]])
    assert verdict.feasible, verdict.violations
    assert verdict.full_service
    assert verdict.cost == pytest.approx(20.0)
    assert verdict.ride_times == {1: pytest.approx(1.0), 2: pytest.approx(4.0)}
    schedule = verdict.routes[0]
    assert schedule.sequence == [0, 1, 3, 2, 4, 5]
    # Earliest feasible service starts, depot departure at 0.
    assert schedule.service_start == pytest.approx([0.0, 3.0, 5.0, 8.0, 13.0, 24.0])


@pytest.mark.parametrize(
    ("routes", "needle"),
    [
        ([[3, 1, 2, 4]], "DROPOFF_BEFORE_PICKUP:1"),
        ([[1, 2, 3, 4]], "CAPACITY:0:2"),
        ([[1, 3, 1, 3, 2, 4]], "DUPLICATE_VISIT:1"),
        ([[1, 3, 2, 4, 7]], "NOT_A_SERVICE_NODE:7"),
        ([[1, 2, 4]], "UNPAIRED_REQUEST:1"),
        ([[1, 3], [2, 4]], "TOO_MANY_ROUTES"),
    ],
)
def test_verifier_names_structural_violations(routes: list[list[int]], needle: str) -> None:
    verdict = verify_routes(_tiny(), routes)
    assert not verdict.feasible
    assert any(v.startswith(needle) for v in verdict.violations), verdict.violations


def test_split_request_is_named_when_two_routes_are_allowed() -> None:
    inst = parse_cordeau_instance(TINY.replace("1 2 100 1 20", "2 2 100 1 20"), instance_id="k2")
    verdict = verify_routes(inst, [[1, 4], [2, 3]])
    assert "SPLIT_REQUEST:1" in verdict.violations
    assert "SPLIT_REQUEST:2" in verdict.violations


def test_infeasible_timing_returns_a_negative_cycle_certificate() -> None:
    # Max ride 3 < direct travel 4 of request 2: no schedule exists.
    verdict = verify_routes(_tiny(**{"1 2 100 1 20": "1 2 100 1 3"}), [[1, 3, 2, 4]])
    assert not verdict.feasible
    (violation,) = verdict.violations
    assert violation.startswith("SCHEDULE_INFEASIBLE:0:")
    assert "RIDE:2" in violation and "TRAVEL:2->4" in violation

    # Dropoff 3 must start by 5; serving request 2 first makes that impossible.
    late = _tiny(**{"3 0 4 1 -1 0 100": "3 0 4 1 -1 0 5"})
    assert verify_routes(late, [[1, 3, 2, 4]]).feasible
    certificate = verify_routes(late, [[2, 4, 1, 3]]).violations[0]
    assert "LATEST:3" in certificate


def test_partial_plan_is_feasible_but_not_full_service() -> None:
    verdict = verify_routes(_tiny(), [[1, 3]])
    assert verdict.feasible
    assert not verdict.full_service
    assert verdict.served_requests == [1]


def test_cpsat_finds_the_hand_optimum() -> None:
    inst = _tiny()
    run = solve_exact_cpsat(inst, time_limit_s=10.0)
    assert run.status == "OPTIMAL"
    assert run.routes == [[1, 3, 2, 4]]
    verdict = verify_routes(inst, run.routes)
    assert verdict.feasible and verdict.full_service
    assert verdict.cost == pytest.approx(20.0)


def test_vendored_bytes_match_sha256sums_and_reference_registry() -> None:
    listed = dict(
        reversed(line.split(None, 1)) for line in _SUMS.read_text().splitlines() if line.strip()
    )
    _inst, digest = load_cordeau_bytes(_A2_16.read_bytes(), instance_id="a2-16")
    assert digest == CORDEAU_A2_16_SHA256 == listed["a2-16.txt"]
    assert REFERENCES[digest].objective == 294.25


def test_a2_16_exact_lane_reproduces_the_published_optimum() -> None:
    inst, digest = load_cordeau_bytes(_A2_16.read_bytes(), instance_id="a2-16")
    run = solve_exact_cpsat(inst, time_limit_s=60.0, workers=1)
    verdict = verify_routes(inst, run.routes)
    assert verdict.feasible, verdict.violations
    assert verdict.full_service
    # No verified plan may beat a proven optimum; the reference is rounded to 0.01.
    assert verdict.cost >= 294.25 - 0.005
    report = build_literature_report(inst, digest, run, verdict)
    if run.status == "OPTIMAL":
        assert abs(verdict.cost - 294.25) <= 0.005
        assert report.gap_blockers == []
        assert report.within_reference_rounding is True
        assert "gap 0.00%" in report.allowed_claim
    # Single-worker search is reproducible.
    again = solve_exact_cpsat(inst, time_limit_s=60.0, workers=1)
    assert again.routes == run.routes


def test_gap_needs_the_exact_reference_bytes() -> None:
    raw = _A2_16.read_bytes().replace(b"402  417", b"401  417")
    inst, digest = load_cordeau_bytes(raw, instance_id="edited")
    assert digest != CORDEAU_A2_16_SHA256
    run = solve_exact_cpsat(inst, time_limit_s=60.0)
    verdict = verify_routes(inst, run.routes)
    report = build_literature_report(inst, digest, run, verdict)
    assert report.gap_percent is None
    assert report.reference_objective is None
    assert "INSTANCE_NOT_REFERENCE" in report.gap_blockers


def test_kernel_plans_are_literature_infeasible_only_through_the_lobby_rule() -> None:
    from mobiroute.adapters.cordeau import cordeau_node_routes, load_cordeau_a2_16
    from mobiroute.solvers.greedy import solve_greedy
    from mobiroute.solvers.native_accel import native_available

    if not native_available():
        pytest.skip("mobiroute_native not built")
    inst, _ = load_cordeau_bytes(_A2_16.read_bytes(), instance_id="a2-16")
    result = solve_greedy(load_cordeau_a2_16())
    routes = cordeau_node_routes(result)
    assert sorted(node for route in routes for node in route) == list(range(1, 33))
    assert not verify_routes(inst, routes).feasible
    relaxed = verify_routes(inst, routes, alight_slack=30)
    assert relaxed.feasible
    # A diagnostic relaxation never counts as a literature verdict.
    run = solve_exact_cpsat(inst, time_limit_s=60.0)
    report = build_literature_report(inst, CORDEAU_A2_16_SHA256, run, relaxed)
    assert report.gap_percent is None
    assert "PLAN_NOT_VERIFIED" in report.gap_blockers
