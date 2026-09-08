"""Linked-trip policy independent of solver timing and native scoring."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence, Set

from mobiroute.domain.models import StopType
from mobiroute.domain.requests import Stop, TripRequest


def linked_parents(trip: TripRequest) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            p for p in (trip.same_vehicle_as, trip.insert_immediately_after) if p is not None
        )
    )


def interested_trip_ids(trips: Mapping[str, TripRequest]) -> set[str]:
    return {tid for tid, t in trips.items() if linked_parents(t)} | {
        parent for t in trips.values() for parent in linked_parents(t)
    }


def dependency_order(ordered: Sequence[TripRequest]) -> list[TripRequest]:
    """Prefer parents first; equality cycles do not imply temporal cycles."""
    todo = list(ordered)
    pending = {t.id for t in todo}
    result: list[TripRequest] = []
    while todo:
        ready = next(
            (
                i
                for i, t in enumerate(todo)
                if (t.same_vehicle_as == t.id or t.same_vehicle_as not in pending)
                and t.insert_immediately_after not in pending
            ),
            None,
        )
        if ready is None:
            # A same-vehicle parent can follow its child; an immediate parent cannot.
            ready = next(
                (i for i, t in enumerate(todo) if t.insert_immediately_after not in pending), 0
            )
        trip = todo.pop(ready)
        pending.remove(trip.id)
        result.append(trip)
    return result


def _layout(
    routes: Mapping[str, Sequence[Stop]],
) -> tuple[dict[str, str], dict[str, tuple[str, int]], dict[str, tuple[str, int]]]:
    owners: dict[str, str] = {}
    pickups: dict[str, tuple[str, int]] = {}
    drops: dict[str, tuple[str, int]] = {}
    kinds = {StopType.PICKUP, StopType.VIA, StopType.DROPOFF}
    for vid, stops in routes.items():
        for i, stop in enumerate(s for s in stops if s.stop_type in kinds):
            if stop.trip_id is None:
                continue
            if stop.stop_type == StopType.PICKUP:
                owners[stop.trip_id] = vid
                pickups[stop.trip_id] = (vid, i)
            elif stop.stop_type == StopType.DROPOFF:
                drops[stop.trip_id] = (vid, i)
    return owners, pickups, drops


def link_issues(
    trips: Mapping[str, TripRequest],
    routes: Mapping[str, Sequence[Stop]],
    *,
    require_parents: bool = True,
) -> list[tuple[str, str]]:
    """Return (child id, violation), counting VIA as an intervening service stop."""
    owners, pickups, drops = _layout(routes)
    issues: list[tuple[str, str]] = []
    for tid, vid in owners.items():
        trip = trips.get(tid)
        if trip is None:
            continue
        for parent in linked_parents(trip):
            if parent not in owners:
                if require_parents:
                    issues.append((tid, f"LINK_PARENT_MISSING:{tid}:{parent}"))
            elif owners[parent] != vid:
                issues.append((tid, f"LINKED_VEHICLE:{tid}:{parent}"))
        after = trip.insert_immediately_after
        if after is not None and after in owners:
            dropped = drops.get(after)
            if dropped is None or pickups[tid] != (dropped[0], dropped[1] + 1):
                issues.append((tid, f"IMMEDIATE_AFTER:{tid}:{after}"))
    return sorted(set(issues))


def dependent_ids(trips: Iterable[TripRequest], roots: Set[str]) -> set[str]:
    children: dict[str, set[str]] = {}
    for trip in trips:
        for parent in linked_parents(trip):
            children.setdefault(parent, set()).add(trip.id)
    found = set(roots)
    todo = list(roots)
    while todo:
        for child in children.get(todo.pop(), ()):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def prune_linked_stops(trips: Mapping[str, TripRequest], routes: dict[str, list[Stop]]) -> set[str]:
    """Drop broken children and both kinds of descendants, not unrelated roots."""
    broken = {tid for tid, _code in link_issues(trips, routes)}
    if not broken:
        return set()
    drop = dependent_ids(trips.values(), broken)
    present = {s.trip_id for stops in routes.values() for s in stops if s.trip_id is not None}
    for vid, stops in routes.items():
        routes[vid] = [s for s in stops if s.trip_id not in drop]
    return drop & present


def allowed_vehicles(
    trip: TripRequest,
    trips: Mapping[str, TripRequest],
    routes: Mapping[str, Sequence[Stop]],
    *,
    pending: Set[str] = frozenset(),
) -> set[str] | None:
    """Intersect forward and already-served reverse links; None means unrestricted."""
    owners, _pickups, _drops = _layout(routes)
    anchors: set[str] = set()
    for parent in linked_parents(trip):
        if parent == trip.id and trip.insert_immediately_after != trip.id:
            continue
        if parent not in owners:
            if (
                parent == trip.same_vehicle_as
                and parent != trip.insert_immediately_after
                and parent in pending
            ):
                continue
            return set()
        anchors.add(owners[parent])
    for child in trips.values():
        if child.id in owners and trip.id in linked_parents(child):
            anchors.add(owners[child.id])
    if not anchors:
        return None
    return anchors if len(anchors) == 1 else set()
