"""CLI, schema, fairness, privacy, generator determinism."""

from __future__ import annotations

import json
from pathlib import Path

from mobiroute.adapters.fingerprint import fingerprint
from mobiroute.adapters.synthetic_data import MODES, generate_day
from mobiroute.cli import main
from mobiroute.domain.fairness import compute_fairness
from mobiroute.domain.requests import DayProblem
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.validation.privacy import assert_no_pii_fields, log_safe, redact_problem_for_open


def test_cli_generate_solve_exit_zero(tmp_path: Path) -> None:
    out = tmp_path / "p.json"
    assert main(["generate", "--mode", "tiny", "--seed", "1", "--out", str(out)]) == 0
    dest = tmp_path / "run"
    assert main(["solve", "--problem", str(out), "--solver", "fifo", "--out-dir", str(dest)]) == 0
    assert (dest / "result.json").exists()


def test_cli_unknown_mode_exit_two(tmp_path: Path) -> None:
    assert main(["generate", "--mode", "not-a-mode", "--out", str(tmp_path / "x.json")]) == 2


def test_cli_ops_benchmark_exit_zero(tmp_path: Path) -> None:
    dest = tmp_path / "ops"
    assert main(["ops-benchmark", "--seed", "42", "--out-dir", str(dest)]) == 0
    summary = json.loads((dest / "ops_summary.json").read_text(encoding="utf-8"))
    assert summary["claim_level"] == "synthetic_benchmark"
    assert (dest / "ops_summary.csv").exists()
    greedy = [r for r in summary["rows"] if r["algorithm"] == "GREEDY"]
    assert greedy
    assert all(r["optimal_claimed"] is False for r in greedy)


def test_generator_modes_exist() -> None:
    for mode in (
        "tiny",
        "driver_unavailable",
        "vehicle_breakdown",
        "pooled_rides",
        "infeasible",
        "ops_wait_return",
    ):
        assert mode in MODES
        day = generate_day(mode, seed=1)
        assert day.requests
        assert fingerprint(day.model_dump(mode="json")) == fingerprint(
            generate_day(mode, seed=1).model_dump(mode="json")
        )


def test_schema_examples_and_new_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "examples" / "tiny_day.json").read_text(encoding="utf-8"))
    DayProblem.model_validate(data)


def test_fairness_multi_metric() -> None:
    p = generate_day("fairness_stress", seed=2)
    res = solve_greedy(p)
    fm = compute_fairness(p, res)
    assert fm.fair_by_single_metric is False
    assert fm.service_coverage is not None
    assert fm.rejected_rate is not None


def test_privacy_open_synthetic() -> None:
    p = generate_day("tiny", seed=6)
    t0 = p.requests[0].model_copy(
        update={"pickup_coordinates": (55.75, 37.61), "dropoff_coordinates": (55.76, 37.62)}
    )
    p = p.model_copy(update={"requests": [t0, *p.requests[1:]]})
    open_p = redact_problem_for_open(p)
    assert open_p.requests[0].pickup_coordinates is None
    assert open_p.passengers[0].privacy_class.value in {"OPEN_SYNTHETIC", "PUBLIC_SYNTHETIC"}
    assert "[REDACTED_PHONE]" in log_safe("call +7 495 129-03-30")
    assert assert_no_pii_fields({"id": "x", "phone": "1"}) == ["phone"]
