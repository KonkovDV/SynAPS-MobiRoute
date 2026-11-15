"""Fleet indicators: empty kilometres, mileage and load utilisation, duty time."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobiroute.cli import main
from mobiroute.vrp.alns import AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, dc_day, plant_day
from mobiroute.vrp.kpi import kpi_markdown, plan_kpi
from mobiroute.vrp.model import Instance, Node, Request, VehicleType, single_profile
from mobiroute.vrp.realtime import simulate
from mobiroute.vrp.sheets import route_sheets, sheets_markdown
from mobiroute.vrp.solution import Route, Solution
from mobiroute.vrp.verify import verify

ROOT = Path(__file__).resolve().parents[1]


def _square() -> Instance:
    """Depot 0; customers 1 and 2 get depot deliveries; 3 -> 4 is a transfer.

    Distances (km) are given directly, so every indicator can be summed by hand.
    """
    d = [
        [0.0, 10.0, 14.0, 6.0, 9.0],
        [10.0, 0.0, 4.0, 8.0, 7.0],
        [14.0, 4.0, 0.0, 11.0, 5.0],
        [6.0, 8.0, 11.0, 0.0, 3.0],
        [9.0, 7.0, 5.0, 3.0, 0.0],
    ]
    matrix = tuple(tuple(row) for row in d)
    nodes = tuple(Node(k, 0.0, 1000.0, 5.0 if k else 0.0) for k in range(5))
    requests = (
        Request("A", None, 1, (2.0,)),
        Request("B", None, 2, (3.0,)),
        Request("T", 3, 4, (4.0,)),
    )
    return Instance(
        "square",
        nodes,
        requests,
        (VehicleType("truck", (10.0,), count=2),),
        single_profile(matrix),
        dimensions=("t",),
    )


def test_empty_and_loaded_kilometres_by_hand() -> None:
    inst = _square()
    # Route 1: depot -> 1 -> 2 -> depot. Leaves with 5 t, drops 2 at 1, 3 at 2.
    # Loaded: 0->1 (10 km, 5 t), 1->2 (4 km, 3 t); empty: 2->0 (14 km).
    # Route 2: depot -> 3 -> 4 -> depot. Empty 0->3 (6), loaded 3->4 (3 km, 4 t), empty 4->0 (9).
    plan = Solution([Route(0, [1, 2]), Route(0, [3, 4])], set())
    verdict = verify(inst, plan)
    assert verdict.feasible
    kpi = plan_kpi(inst, plan, verdict)
    first, second = kpi.routes
    assert first.distance == pytest.approx(28.0) and first.loaded_distance == pytest.approx(14.0)
    assert first.empty_distance == pytest.approx(14.0)
    assert first.mileage_utilisation == pytest.approx(0.5)
    assert first.load_distance == pytest.approx((5.0 * 10.0 + 3.0 * 4.0,))
    # Dynamic load utilisation over loaded kilometres: 62 t-km of 10 t x 14 km.
    assert first.load_utilisation[0] == pytest.approx(62.0 / (10.0 * 14.0))
    assert second.empty_distance == pytest.approx(15.0)
    assert second.mileage_utilisation == pytest.approx(3.0 / 18.0)
    assert kpi.distance == pytest.approx(verdict.cost.distance)
    assert kpi.empty_distance == pytest.approx(29.0)
    assert kpi.mileage_utilisation == pytest.approx(17.0 / 46.0)
    assert kpi.load_distance == pytest.approx((62.0 + 12.0,))
    assert second.load_utilisation[0] == pytest.approx(12.0 / (10.0 * 3.0))
    assert kpi.load_utilisation[0] == pytest.approx(74.0 / (10.0 * 17.0))
    # beta * gamma: the share of the possible work over the whole mileage.
    beta, gamma = kpi.mileage_utilisation, kpi.load_utilisation[0]
    assert beta is not None and gamma is not None
    assert beta * gamma == pytest.approx(74.0 / (10.0 * 46.0))
    assert kpi.served == 3 and kpi.unserved == 0 and kpi.vehicles == 2
    assert kpi.km_per_order == pytest.approx(46.0 / 3.0)
    # Time on duty adds up: driving + service + rest + waiting.
    for r in kpi.routes:
        assert r.duty == pytest.approx(r.driving + r.service + r.rest + r.waiting, abs=1e-6)
    # The route sheet tells the driver the same empty kilometres.
    sheets = route_sheets(inst, plan, verdict)
    assert [s.empty_distance for s in sheets] == pytest.approx([14.0, 15.0])
    assert "из них порожних 14,0" in sheets_markdown(sheets, inst.dimensions)


def test_indicators_follow_the_plan_on_generated_days() -> None:
    for inst in (cargo_day(3, n_orders=40), dc_day(2, n_stores=30, trips=2)):
        result = solve(inst, AlnsConfig(iterations=150, seed=1))
        assert result.verdict.feasible
        kpi = plan_kpi(inst, result.solution, result.verdict)
        assert kpi.distance == pytest.approx(result.verdict.cost.distance, rel=1e-9)
        assert 0.0 <= kpi.empty_distance <= kpi.distance
        beta = kpi.mileage_utilisation
        assert beta is not None and 0.0 < beta <= 1.0
        assert all(g is None or 0.0 <= g <= 1.0 + 1e-9 for g in kpi.load_utilisation)
        assert kpi.served == len(result.verdict.served)
        assert sum(r.orders for r in kpi.routes) == kpi.served
        # Depot deliveries come back empty: every route has an empty last leg.
        assert all(r.empty_distance > 0.0 for r in kpi.routes)
        data = kpi.as_dict()
        assert data["vehicles"] == kpi.vehicles and len(data["routes"]) == kpi.vehicles  # type: ignore[arg-type]
        text_ru, text_en = kpi_markdown(kpi), kpi_markdown(kpi, lang="en")
        assert "коэффициент использования пробега" in text_ru
        assert "mileage utilisation" in text_en


def test_infeasible_plan_has_no_indicators() -> None:
    inst = _square()
    plan = Solution([Route(0, [4, 3])], {0, 1})  # delivery before its pickup
    verdict = verify(inst, plan)
    assert not verdict.feasible
    with pytest.raises(ValueError, match="SHEETS_NEED_A_FEASIBLE_PLAN"):
        plan_kpi(inst, plan, verdict)


def test_dispatch_reports_empty_running() -> None:
    report = simulate(plant_day(5, n_moves=40))
    k = report.kpi
    assert report.verified
    assert 0.0 < k["empty_km"] < k["distance"]
    assert k["mileage_utilisation"] == pytest.approx(1.0 - k["empty_km"] / k["distance"], abs=1e-3)


def test_cli_writes_indicators_and_uses_the_whole_time_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "chelny"
    code = main(
        [
            "vrp-solve",
            "--geo",
            str(ROOT / "examples" / "chelny-day.geo.json"),
            "--iterations",
            "200",
            "--out-dir",
            str(out),
        ]
    )
    assert code == 0
    report = json.loads((out / "verdict.json").read_text(encoding="utf-8"))
    kpi = report["kpi"]
    assert kpi["distance_km"] == pytest.approx(report["distance"], abs=1e-3)
    assert 0.0 < kpi["empty_km"] < kpi["distance_km"]
    assert (out / "kpi.md").read_text(encoding="utf-8").startswith("# Показатели работы парка")
    assert "empty km" in capsys.readouterr().out

    # --time-limit alone lifts the iteration cap; --iterations still sets one.
    import mobiroute.vrp.alns as alns_module

    seen: list[AlnsConfig] = []
    real = alns_module.solve

    def spy(inst: Instance, config: AlnsConfig | None = None, initial: object = None) -> object:
        assert config is not None
        seen.append(config)
        return real(inst, AlnsConfig(iterations=20, seed=config.seed))

    monkeypatch.setattr(alns_module, "solve", spy)
    base = ["vrp-solve", "--generate", "cargo", "--orders", "20", "--out-dir"]
    assert main([*base, str(tmp_path / "a"), "--time-limit", "5"]) == 0
    assert main([*base, str(tmp_path / "b")]) == 0
    assert main([*base, str(tmp_path / "c"), "--time-limit", "5", "--iterations", "7"]) == 0
    assert [c.iterations for c in seen] == [10**9, 5000, 7]
    assert seen[0].time_limit == 5.0
