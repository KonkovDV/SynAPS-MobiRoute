"""Passenger, vehicle, driver, trip, stop, and plan entities."""

from __future__ import annotations

from pydantic import Field, PrivateAttr

from mobiroute.domain.models import (
    BookingStatus,
    DataProvenance,
    EligibilityClass,
    PrivacyClass,
    ServicePriority,
    StopType,
    StrictModel,
    TimeMin,
    WheelchairType,
    ZoneId,
)
from mobiroute.domain.travel_graph import floyd_warshall, reconstruct_path


class AccessibilityRequirements(StrictModel):
    needs_lift: bool = False
    needs_ramp: bool = False
    needs_boarding_assistance: bool = False
    wheelchair_type: WheelchairType = WheelchairType.NONE
    companion_count: int = Field(default=0, ge=0)


class PassengerProfile(StrictModel):
    pseudonymous_id: str
    eligibility_class: EligibilityClass = EligibilityClass.STANDARD
    accessibility_requirements: AccessibilityRequirements = Field(
        default_factory=AccessibilityRequirements
    )
    wheelchair_type: WheelchairType = WheelchairType.NONE
    companion_count: int = Field(default=0, ge=0)
    medical_priority: bool = False
    privacy_class: PrivacyClass = PrivacyClass.PUBLIC_SYNTHETIC
    data_provenance: DataProvenance = DataProvenance.SYNTHETIC
    # Remaining entitlement minutes for this planning day. None = unlimited.
    quota_minutes_remaining: int | None = None


class Vehicle(StrictModel):
    id: str
    vehicle_type: str
    passenger_capacity: int = Field(ge=1)
    wheelchair_capacity: int = Field(default=0, ge=0)
    lift_available: bool = False
    ramp_available: bool = False
    accessible_features: list[str] = Field(default_factory=list)
    # Empty → MANUAL and POWER only (not SCOOTER/STRETCHER).
    compatible_wheelchair_types: list[WheelchairType] = Field(default_factory=list)
    depot_id: str
    shift_start: TimeMin
    shift_end: TimeMin
    service_area: list[ZoneId] = Field(default_factory=list)
    unavailable_intervals: list[tuple[TimeMin, TimeMin]] = Field(default_factory=list)


class Driver(StrictModel):
    id: str
    qualifications: list[str] = Field(default_factory=list)
    shift_start: TimeMin
    shift_end: TimeMin
    depot_id: str
    language_capabilities: list[str] = Field(default_factory=list)
    accessibility_training: bool = False
    availability: bool = True
    # Empty → any vehicle_type at the same depot.
    qualified_vehicle_types: list[str] = Field(default_factory=list)


class DriverAssignment(StrictModel):
    driver_id: str
    vehicle_id: str
    shift_start: TimeMin
    shift_end: TimeMin
    qualification_match: bool = True
    accessibility_training: bool = False
    assignment_status: str = "ASSIGNED"


class TimeWindow(StrictModel):
    earliest: TimeMin
    latest: TimeMin


class TripRequest(StrictModel):
    id: str
    pseudonymous_passenger_id: str
    pickup_zone: ZoneId
    dropoff_zone: ZoneId
    requested_at: TimeMin
    earliest_pickup: TimeMin
    latest_pickup: TimeMin
    appointment_start: TimeMin | None = None
    appointment_end: TimeMin | None = None
    max_ride_time: TimeMin
    max_wait_time: TimeMin
    wheelchair_requirement: WheelchairType = WheelchairType.NONE
    companion_count: int = Field(default=0, ge=0)
    service_priority: ServicePriority = ServicePriority.STANDARD
    eligibility_class: EligibilityClass = EligibilityClass.STANDARD
    booking_status: BookingStatus = BookingStatus.REQUESTED
    boarding_duration: TimeMin = 3
    alighting_duration: TimeMin = 2
    needs_lift: bool = False
    needs_ramp: bool = False
    needs_boarding_assistance: bool = False
    medical_priority: bool = False
    frozen: bool = False
    max_detour_ratio: float = Field(default=3.0, gt=0)
    data_provenance: DataProvenance = DataProvenance.SYNTHETIC
    # Coordinates only allowed in protected/private mode — omit in open synthetic.
    pickup_coordinates: tuple[float, float] | None = None
    dropoff_coordinates: tuple[float, float] | None = None
    # Policy-shaped labels for synthetic ops scenarios (not legal eligibility).
    trip_purpose: str = "OTHER"
    channel: str = "STANDARD"
    same_vehicle_as: str | None = None
    insert_immediately_after: str | None = None
    # Optional third stop (clinic then pharmacy). Passenger stays onboard.
    via_zone: ZoneId | None = None
    via_service_duration: TimeMin = 2
    # Remaining entitlement minutes (door-to-door ride). None = unlimited.
    quota_minutes_remaining: int | None = None


class Stop(StrictModel):
    id: str
    trip_id: str | None
    stop_type: StopType
    location: ZoneId
    service_duration: TimeMin = 0
    time_window: TimeWindow | None = None
    load_delta: int = 0
    wheelchair_load_delta: int = 0


class PassengerItinerary(StrictModel):
    trip_id: str
    vehicle_id: str
    driver_id: str | None = None
    pickup_stop_id: str
    dropoff_stop_id: str
    pickup_time: TimeMin
    dropoff_time: TimeMin
    ride_time: TimeMin
    waiting_time: TimeMin = 0
    appointment_slack: TimeMin | None = None
    travel_path: list[ZoneId] = Field(default_factory=list)


class TripExplanation(StrictModel):
    trip_id: str
    accepted: bool
    vehicle_id: str | None = None
    driver_id: str | None = None
    pickup_stop_id: str | None = None
    dropoff_stop_id: str | None = None
    pickup_time: TimeMin | None = None
    dropoff_time: TimeMin | None = None
    waiting_time: TimeMin | None = None
    ride_time: TimeMin | None = None
    appointment_slack: TimeMin | None = None
    active_constraints: list[str] = Field(default_factory=list)
    why_this_route: str = ""
    alternatives_considered: list[str] = Field(default_factory=list)
    alternatives_rejected: list[str] = Field(default_factory=list)
    reason_code: str = ""


class RoutePlan(StrictModel):
    vehicle_id: str
    driver_id: str | None
    ordered_stops: list[Stop]
    passenger_assignments: list[str]
    arrival_times: dict[str, TimeMin]
    departure_times: dict[str, TimeMin]
    waiting_times: dict[str, TimeMin] = Field(default_factory=dict)
    ride_times: dict[str, TimeMin] = Field(default_factory=dict)
    route_distance: float = 0.0
    route_duration: TimeMin = 0
    passenger_load_after_stop: dict[str, int] = Field(default_factory=dict)
    wheelchair_load_after_stop: dict[str, int] = Field(default_factory=dict)
    deadhead_time: TimeMin = 0
    frozen_stop_ids: list[str] = Field(default_factory=list)
    driver_assignment: DriverAssignment | None = None
    passenger_itineraries: list[PassengerItinerary] = Field(default_factory=list)


class RejectedTrip(StrictModel):
    trip_id: str
    reason_code: str
    detail: str = ""


class FairnessMetrics(StrictModel):
    acceptance_rate_by_zone: dict[str, float] = Field(default_factory=dict)
    acceptance_rate_by_eligibility: dict[str, float] = Field(default_factory=dict)
    medical_on_time_rate: float | None = None
    wheelchair_on_time_rate: float | None = None
    mean_wait_by_group: dict[str, float] = Field(default_factory=dict)
    wait_dispersion: float | None = None
    worst_group_wait: float | None = None
    average_waiting: float | None = None
    p95_waiting: float | None = None
    average_ride_time: float | None = None
    p95_ride_time: float | None = None
    rejected_rate: float | None = None
    cancel_share: float | None = None
    unexplained_reject_share: float | None = None
    jain_index: float | None = None
    max_disparity: float | None = None
    service_coverage: float | None = None
    manual_override_disparity: float | None = None
    fair_by_single_metric: bool = False


class PlanningResult(StrictModel):
    status: str
    solution_type: str
    verified_feasible: bool
    served_requests: list[str]
    rejected_requests: list[RejectedTrip]
    late_requests: list[str] = Field(default_factory=list)
    route_plans: list[RoutePlan]
    objective_values: dict[str, float] = Field(default_factory=dict)
    fairness_metrics: FairnessMetrics = Field(default_factory=FairnessMetrics)
    reason_codes: dict[str, str] = Field(default_factory=dict)
    explanations: list[TripExplanation] = Field(default_factory=list)
    driver_assignments: list[DriverAssignment] = Field(default_factory=list)
    plan_id: str = ""
    base_plan_id: str | None = None
    event_id: str | None = None
    event_type: str = "DAY_AHEAD"
    event_timestamp: TimeMin = 0
    input_hash: str
    config_hash: str
    solver_config: dict[str, object] = Field(default_factory=dict)
    mobiroute_version: str
    synaps_commit: str
    data_provenance: DataProvenance = DataProvenance.SYNTHETIC
    claim_level: str = "synthetic_benchmark"


class PlanDiff(StrictModel):
    baseline_fingerprint: str
    new_fingerprint: str
    added_trips: list[str] = Field(default_factory=list)
    removed_trips: list[str] = Field(default_factory=list)
    moved_trips: list[str] = Field(default_factory=list)
    unchanged_frozen_trips: list[str] = Field(default_factory=list)
    changed_routes: list[str] = Field(default_factory=list)
    changed_vehicle_assignments: list[str] = Field(default_factory=list)
    newly_rejected_trips: list[RejectedTrip] = Field(default_factory=list)
    reason_codes: dict[str, str] = Field(default_factory=dict)
    fairness_delta: dict[str, float] = Field(default_factory=dict)
    objective_delta: dict[str, float] = Field(default_factory=dict)
    plan_churn: dict[str, float] = Field(default_factory=dict)


class DispatchScenario(StrictModel):
    name: str
    baseline: bool = False
    online_request: TripRequest | None = None
    cancellation_trip_id: str | None = None
    no_show_trip_id: str | None = None
    traffic_delay_minutes: TimeMin = 0
    vehicle_unavailable_id: str | None = None
    driver_unavailable_id: str | None = None
    emergency_trip: TripRequest | None = None
    protected_trip_change: bool = False


class TravelMatrix(StrictModel):
    zones: list[ZoneId]
    # Direct edge minutes[i][j] between zones[i] and zones[j].
    minutes: list[list[TimeMin]]
    _hop: list[list[int]] | None = PrivateAttr(default=None)
    _nxt: list[list[int]] | None = PrivateAttr(default=None)

    def _ensure_graph(self) -> tuple[list[list[int]], list[list[int]]]:
        if self._hop is None or self._nxt is None:
            self._hop, self._nxt = floyd_warshall(self.minutes)
        return self._hop, self._nxt

    def travel(self, a: ZoneId, b: ZoneId) -> TimeMin:
        try:
            i = self.zones.index(a)
            j = self.zones.index(b)
        except ValueError as exc:
            raise KeyError(f"UNKNOWN_ZONE:{a}->{b}") from exc
        hop, _nxt = self._ensure_graph()
        return hop[i][j]

    def shortest_path(self, a: ZoneId, b: ZoneId) -> list[ZoneId]:
        try:
            i = self.zones.index(a)
            j = self.zones.index(b)
        except ValueError as exc:
            raise KeyError(f"UNKNOWN_ZONE:{a}->{b}") from exc
        _hop, nxt = self._ensure_graph()
        idx = reconstruct_path(nxt, i, j)
        return [self.zones[k] for k in idx]


class DayProblem(StrictModel):
    problem_id: str
    schema_version: str = "mobiroute.problem.v1"
    seed: int
    passengers: list[PassengerProfile]
    vehicles: list[Vehicle]
    drivers: list[Driver]
    requests: list[TripRequest]
    travel: TravelMatrix
    data_provenance: DataProvenance = DataProvenance.SYNTHETIC
    claim_level: str = "synthetic_benchmark"
