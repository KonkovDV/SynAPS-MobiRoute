"""CLI contracts: claim gates bind to bytes, inputs fail cleanly, modes are valid."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobiroute.adapters.synthetic_data import MODES, generate_day
from mobiroute.cli import main
from mobiroute.solvers.native_accel import native_available
from mobiroute.validation.input import validate_problem

_A2_16 = Path(__file__).resolve().parents[1] / "benchmark" / "instances" / "cordeau" / "a2-16.txt"


def _edited_copy(tmp_path: Path, name: str) -> Path:
    # Same instance family, different bytes: one window shifted by a minute.
    edited = tmp_path / name
    edited.write_bytes(_A2_16.read_bytes().replace(b"402  417", b"401  417"))
    return edited


def test_academic_benchmark_attaches_the_reference_to_the_vendored_bytes(
    tmp_path: Path,
) -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    out = tmp_path / "a2-16"
    assert main(["academic-benchmark", "--instance", str(_A2_16), "--out-dir", str(out)]) == 0
    payload = json.loads((out / "academic_benchmark.json").read_text())
    report = payload["report"]
    assert report["instance_id"] == "cordeau-a2-16"
    assert report["reference_objective"] == 294.25
    assert report["served_count"] == 16
    assert report["gap_blockers"] == ["ALGEBRA_NOT_COMPARABLE"]
    cross = payload["literature_crosscheck"]
    assert cross["kernel_routes_literature_feasible"] is False
    assert cross["feasible_with_operator_lobby_slack_30"] is True


def test_academic_benchmark_never_labels_other_bytes_as_a2_16(tmp_path: Path) -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    edited = _edited_copy(tmp_path, "my-variant.txt")
    out = tmp_path / "variant"
    assert main(["academic-benchmark", "--instance", str(edited), "--out-dir", str(out)]) == 0
    report = json.loads((out / "academic_benchmark.json").read_text())["report"]
    assert report["instance_id"] == "cordeau-my-variant"
    assert report["reference_objective"] is None
    assert "NO_REFERENCE_OBJECTIVE" in report["gap_blockers"]


def test_literature_benchmark_reports_a_gated_gap(tmp_path: Path) -> None:
    out = tmp_path / "lit"
    assert main(["literature-benchmark", "--instance", str(_A2_16), "--out-dir", str(out)]) == 0
    payload = json.loads((out / "literature_benchmark.json").read_text())
    report = payload["report"]
    assert report["verified_feasible"] is True
    assert report["full_service"] is True
    assert report["gap_blockers"] == []
    assert report["within_reference_rounding"] is True
    assert payload["evidence"]["instance_sha256"] == report["instance_sha256"]
    assert payload["evidence"]["exit_code"] == 0

    other = tmp_path / "lit-variant"
    edited = _edited_copy(tmp_path, "variant.txt")
    assert main(["literature-benchmark", "--instance", str(edited), "--out-dir", str(other)]) == 0
    report = json.loads((other / "literature_benchmark.json").read_text())["report"]
    assert report["gap_percent"] is None
    assert "INSTANCE_NOT_REFERENCE" in report["gap_blockers"]


def test_invalid_inputs_exit_2_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"bad": 1}', encoding="utf-8")
    assert main(["solve", "--problem", str(bad), "--out-dir", str(tmp_path / "o")]) == 2
    assert capsys.readouterr().err.startswith("error: ValidationError")
    missing = tmp_path / "missing.json"
    assert main(["solve", "--problem", str(missing), "--out-dir", str(tmp_path / "o")]) == 2
    broken = tmp_path / "broken.txt"
    broken.write_text("1 2 3\n", encoding="utf-8")
    args = ["literature-benchmark", "--instance", str(broken), "--out-dir", str(tmp_path)]
    assert main(args) == 2


@pytest.mark.parametrize("mode", MODES)
def test_every_generator_mode_is_a_valid_problem(mode: str) -> None:
    validate_problem(generate_day(mode, seed=42))
