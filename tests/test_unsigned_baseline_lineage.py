"""A parent without a plan id is chained as unsigned, not as an identity."""

from __future__ import annotations

import pytest

from mobiroute.dispatch.online_insertion import _base_plan_id, online_insert
from mobiroute.solvers.greedy import solve_greedy
from mobiroute.solvers.native_accel import native_available
from tests.factories import driver, problem, trip, vehicle


def _day():
    return problem(
        [vehicle("v1")],
        [driver("d1")],
        [trip("t1", "Z_NORTH", "Z_SOUTH")],
    )


def test_an_unsigned_parent_is_named_unsigned_and_stays_deterministic() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    signed = solve_greedy(_day())
    assert _base_plan_id(signed) == signed.plan_id
    unsigned = signed.model_copy(update={"plan_id": ""})
    reference = _base_plan_id(unsigned)
    assert reference.startswith("unsigned:")
    assert _base_plan_id(unsigned.model_copy(deep=True)) == reference
    # A different unsigned plan cannot borrow the same parent reference.
    other = unsigned.model_copy(update={"solution_type": "OTHER"})
    assert _base_plan_id(other) != reference


def test_the_child_of_an_unsigned_parent_publishes_the_unsigned_reference() -> None:
    if not native_available():
        pytest.skip("mobiroute_native not built")
    day = _day()
    signed = solve_greedy(day)
    newcomer = trip("t2", "Z_EAST", "Z_WEST")
    _u, child, _d = online_insert(
        day,
        signed.model_copy(update={"plan_id": ""}),
        newcomer,
        protect_frozen=False,
    )
    assert child.base_plan_id is not None
    assert child.base_plan_id.startswith("unsigned:")
    assert child.plan_id and not child.plan_id.startswith("unsigned:")
    _u2, signed_child, _d2 = online_insert(day, signed, newcomer, protect_frozen=False)
    assert signed_child.base_plan_id == signed.plan_id
