"""Passenger, vehicle, driver, trip, stop, and plan entities."""

from __future__ import annotations

from pydantic import Field

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


class Vehicle(StrictModel):
    id: str
    vehicle_type: str
    passenger_capacity: int = Field(ge=1)
    wheelchair_capacity: int = Field(default=0, ge=0)
    lift_available: bool = False
    ramp_available: bool = False
    accessible_features: list[str] = Field(default_factory=list)
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
    data_provenance: DataProvenance = DataProvenance.SYNTHETIC
    # Coordinates only allowed in protected/private mode — omit in open synthetic.
    pickup_coordinates: tuple[float, float] | None = None
    dropoff_coordinates: tuple[float, float] | None = None


class Stop(StrictModel):
    id: str
    trip_id: str | None
    stop_type: StopType
    location: ZoneId
    service_duration: TimeMin = 0
    time_window: TimeWindow | None = None
    load_delta: int = 0
    wheelchair_load_delta: int = 0


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


class RejectedTrip(StrictModel):
    trip_id: str
    reason_code: str
    detail: str = ""


class FairnessMetrics(StrictModel):
    acceptance_rate_by_zone: dict[str, float] = Field(default_factory=dict)
    acceptance_rate_by_eligibility: dict[str, float] = Field(default_factory=dict)
    medical_on_time_rate: float | None = None
    mean_wait_by_group: dict[str, float] = Field(default_factory=dict)
    wait_dispersion: float | None = None
    worst_group_wait: float | None = None
    cancel_share: float | None = None
    unexplained_reject_share: float | None = None
    jain_index: float | None = None
    max_disparity: float | None = None


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
    # minutes[i][j] between zones[i] and zones[j]
    minutes: list[list[TimeMin]]

    def travel(self, a: ZoneId, b: ZoneId) -> TimeMin:
        i = self.zones.index(a)
        j = self.zones.index(b)
        return self.minutes[i][j]


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
