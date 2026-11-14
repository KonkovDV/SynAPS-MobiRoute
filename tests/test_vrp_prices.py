"""Shadow prices: LP duality on the route pool, against cases solved by hand.

The identities checked here are the ones the documentation states: strong
duality (prices minus rents equal the LP value), dual feasibility (no pool
route is cheaper than the prices of its orders plus the rent of its vehicle
type), prices at or above the removal savings when the plan is LP-optimal,
and a rent that predicts what one more vehicle saves.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mobiroute.cli import main
from mobiroute.vrp.alns import Alns, AlnsConfig, solve
from mobiroute.vrp.generators import cargo_day, random_instance
from mobiroute.vrp.insertion import Compiled
from mobiroute.vrp.model import (
    Instance,
    Node,
    Request,
    VehicleType,
    euclidean_matrix,
    single_profile,
)
from mobiroute.vrp.prices import (
    Prices,
    prices_dict,
    prices_markdown,
    removal_savings,
    shadow_prices,
    solve_with_prices,
)
from mobiroute.vrp.setpart import RoutePool
from mobiroute.vrp.solution import Route, Solution

ROOT = Path(__file__).resolve().parents[1]


def _line(points: list[tuple[float, float]], types: tuple[VehicleType, ...]) -> Instance:
    nodes = tuple(Node(k, 0.0, 1000.0, 0.0, x, y) for k, (x, y) in enumerate(points))
    requests = tuple(Request(f"o{k}", None, k, (1.0,)) for k in range(1, len(points)))
    return Instance("hand", nodes, requests, types, single_profile(euclidean_matrix(points)))


def _prices(inst: Instance, plan: Solution) -> tuple[Prices, RoutePool]:
    pool = RoutePool(Compiled(inst))
    return shadow_prices(pool, plan), pool


def _by_id(prices: Prices) -> dict[str, float | None]:
    return {o.request: o.price for o in prices.orders}


def test_two_orders_in_opposite_directions_split_the_route_evenly() -> None:
    # Depot between A and B: D-A-B-D = 10 + 20 + 10 = 40, and dropping either
    # order saves 20, so the savings already add up to the plan.
    inst = _line([(0.0, 0.0), (10.0, 0.0), (-10.0, 0.0)], (VehicleType("van", (2.0,)),))
    prices, _pool = _prices(inst, Solution([Route(0, [1, 2])], set()))
    assert prices.status == "OPTIMAL" and prices.tight
    assert prices.plan_value == pytest.approx(40.0) and prices.lp_value == pytest.approx(40.0)
    assert _by_id(prices) == {"o1": pytest.approx(20.0), "o2": pytest.approx(20.0)}
    assert [o.saving for o in prices.orders] == [pytest.approx(20.0), pytest.approx(20.0)]
    assert prices.rents == pytest.approx(0.0)


def test_the_rent_of_a_scarce_own_van_is_the_hire_fee_it_would_spare() -> None:
    # One own van that carries one order, hired vans at a fee of 100: the second
    # order rides a hired van, so one more own van would save exactly the fee.
    own = VehicleType("van", (1.0,), count=1)
    hired = VehicleType("van-hired", (1.0,), count=5, fixed_cost=100.0, hired=True)
    inst = _line([(0.0, 0.0), (10.0, 0.0), (-10.0, 0.0)], (own, hired))
    plan = Solution([Route(0, [1]), Route(1, [2])], set())
    prices, _pool = _prices(inst, plan)
    assert prices.tight and prices.plan_value == pytest.approx(140.0)
    # Either order could take the own van, so both are priced at the hired route.
    assert _by_id(prices) == {"o1": pytest.approx(120.0), "o2": pytest.approx(120.0)}
    assert dict(prices.vehicles) == {"van": pytest.approx(100.0), "van-hired": 0.0}
    assert sum(p for p in _by_id(prices).values() if p is not None) - prices.rents == (
        pytest.approx(prices.plan_value)
    )
    # The prediction holds: with a second own van the day costs 100 less.
    more = replace(inst, vehicle_types=(replace(own, count=2), hired))
    assert solve(more, AlnsConfig(iterations=50, seed=1)).objective == pytest.approx(40.0)


def test_an_order_left_out_is_priced_at_most_at_its_penalty() -> None:
    # Serving the far order costs 200 and leaving it out 50, so it stays out.
    inst = _line([(0.0, 0.0), (10.0, 0.0), (100.0, 0.0)], (VehicleType("van", (2.0,)),))
    cheap = replace(inst.requests[1], penalty=50.0)
    inst = replace(inst, requests=(inst.requests[0], cheap))
    res, prices = solve_with_prices(inst, AlnsConfig(iterations=200, seed=1))
    assert res.solution.unassigned == {1}
    far = prices.orders[1]
    assert not far.served and far.saving is None
    assert far.price is not None and far.price <= 50.0 + 1e-6
    assert prices.plan_value == pytest.approx(20.0 + 50.0)


def _check_duality(inst: Instance, prices: Prices, pool: RoutePool) -> None:
    c = pool.c
    price = [o.price for o in prices.orders]
    rent = [value for _vid, value in prices.vehicles]
    assert prices.lp_value is not None
    total = sum(p for p in price if p is not None)
    assert total - prices.rents == pytest.approx(prices.lp_value, rel=1e-6, abs=1e-6)
    assert prices.lp_value <= prices.plan_value + 1e-6 * max(1.0, prices.plan_value)
    assert all(value >= 0.0 for value in rent)
    for (t, requests), (money, _nodes) in pool.columns.items():
        left = sum(price[r] or 0.0 for r in requests) - rent[t]
        assert left <= money + 1e-6 * max(1.0, money)
    for r, req in enumerate(inst.requests):
        if req.penalty is not None and price[r] is not None:
            assert price[r] <= req.penalty + 1e-6
    assert c.inst is inst


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(0, 10_000), types=st.integers(1, 3))
def test_prices_are_dual_feasible_and_add_up_on_random_instances(seed: int, types: int) -> None:
    inst = random_instance(seed, n_requests=7, n_types=types, ride_share=0.3, penalty=1000.0)
    search = Alns(inst, AlnsConfig(iterations=150, seed=1, keep_pool=True))
    res = search.solve()
    assert search.pool is not None
    prices = shadow_prices(search.pool, res.solution)
    assert prices.status == "OPTIMAL"
    _check_duality(inst, prices, search.pool)
    if prices.tight:
        # Complementary slackness with the "one order out" columns in the pool
        # (Lemma 5). "Tight" and the optimal face of the second LP both carry a
        # relative tolerance of 1e-7 of the objective, so the bound holds up to
        # their sum.
        slack = 3e-7 * max(1.0, prices.plan_value)
        for o in prices.orders:
            if o.price is not None and o.saving is not None:
                assert o.price >= o.saving - slack


def test_collecting_the_pool_does_not_change_the_plan() -> None:
    inst = cargo_day(7, n_orders=40)
    config = AlnsConfig(iterations=600, seed=1)
    plain = solve(inst, config)
    res, prices = solve_with_prices(inst, config)
    assert res.solution.as_lists() == plain.solution.as_lists()
    assert res.objective == plain.objective and plain.pool_size == 0 and res.pool_size > 0
    assert prices.plan_value == pytest.approx(res.objective, rel=1e-9)
    assert prices.columns >= res.pool_size


def test_own_vehicles_that_ran_out_carry_a_rent_and_hired_ones_do_not() -> None:
    from mobiroute.vrp import geo

    day = geo.load(str(ROOT / "examples" / "chelny-day.geo.json"))
    res, prices = solve_with_prices(day.instance, AlnsConfig(iterations=800, seed=1))
    assert res.verdict.feasible and res.verdict.complete
    rent = dict(prices.vehicles)
    # Every own van and truck is out, and the day still hires: one more own
    # unit would replace hired kilometres, a hired type has units to spare.
    assert rent["van"] > 0.0 and rent["truck"] > 0.0
    assert rent["van-hired"] == 0.0 and rent["truck-hired"] == 0.0
    assert prices.gap is not None and 0.0 <= prices.gap < 0.2 * prices.plan_value


def test_removal_savings_are_exact_route_differences() -> None:
    inst = _line([(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)], (VehicleType("van", (2.0,)),))
    c = Compiled(inst)
    savings = removal_savings(c, Solution([Route(0, [1, 2])], set()))
    # D-A-B-D = 40; without A it is D-B-D = 40, without B it is D-A-D = 20.
    assert savings[0] == (pytest.approx(0.0), 0, [2])
    assert savings[1] == (pytest.approx(20.0), 0, [1])
    alone = removal_savings(c, Solution([Route(0, [2])], {0}))
    assert alone == {1: (pytest.approx(40.0), 0, [])}


def test_reports_in_both_languages_and_json() -> None:
    inst = _line([(0.0, 0.0), (10.0, 0.0), (-10.0, 0.0)], (VehicleType("van", (2.0,)),))
    prices, _pool = _prices(inst, Solution([Route(0, [1, 2])], set()))
    ru = prices_markdown(prices, currency="₽")
    assert "Стоимость плана: 40,00 ₽." in ru and "| o1 | 20,00 | 20,00 | да |" in ru
    assert "план достигает оценки" in ru and "нет: машин каждого типа хватает" in ru
    en = prices_markdown(prices, lang="en")
    assert "Plan cost: 40.00." in en and "| o2 | 20.00 | 20.00 | yes |" in en
    data = json.loads(json.dumps(prices_dict(prices)))
    assert data["format"] == "mobiroute.vrp.prices.v1" and data["tight"] is True
    assert data["gap"] == 0.0 and [o["price"] for o in data["orders"]] == [20.0, 20.0]
    # A request id may not break the table or inject markup.
    odd = replace(inst, requests=(replace(inst.requests[0], id="a|b<i>"), inst.requests[1]))
    table = prices_markdown(_prices(odd, Solution([Route(0, [1, 2])], set()))[0])
    assert "a\\|b&lt;i&gt;" in table


def test_cli_writes_prices_and_refuses_other_solvers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "day"
    example = ROOT / "examples" / "chelny-day.geo.json"
    args = ["vrp-solve", "--geo", str(example), "--iterations", "300", "--prices"]
    assert main([*args, "--out-dir", str(out)]) == 0
    data = json.loads((out / "prices.json").read_text(encoding="utf-8"))
    assert data["status"] == "OPTIMAL" and len(data["orders"]) == 45
    assert data["lp_value"] <= data["plan_value"] + 1e-6
    text = (out / "prices.md").read_text(encoding="utf-8")
    assert text.startswith("# Цены заказов и машин") and "RUB" in text
    capsys.readouterr()
    refused = main([*args, "--solver", "ortools", "--out-dir", str(tmp_path / "x")])
    assert refused == 2
    assert "PRICES_NEED_THE_ALNS_ROUTE_POOL" in capsys.readouterr().err
