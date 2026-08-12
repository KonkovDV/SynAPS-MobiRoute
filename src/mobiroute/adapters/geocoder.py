"""Geocoder stub — open mode uses zones only; never persist real addresses in git."""

from __future__ import annotations

from mobiroute.domain.models import StrictModel


class ZoneRef(StrictModel):
    zone_id: str
    label: str
    kind: str  # hospital | rehab | social | depot | residential_synth


def zone_catalog() -> list[ZoneRef]:
    return [
        ZoneRef(zone_id="Z_NORTH", label="Synthetic North", kind="residential_synth"),
        ZoneRef(zone_id="Z_SOUTH", label="Synthetic South", kind="residential_synth"),
        ZoneRef(zone_id="Z_EAST", label="Synthetic East", kind="residential_synth"),
        ZoneRef(zone_id="Z_WEST", label="Synthetic West", kind="residential_synth"),
        ZoneRef(zone_id="Z_CENTER", label="Synthetic Center", kind="residential_synth"),
        ZoneRef(zone_id="Z_HOSP_A", label="Synthetic Hospital A", kind="hospital"),
        ZoneRef(zone_id="Z_HOSP_B", label="Synthetic Hospital B", kind="hospital"),
        ZoneRef(zone_id="Z_REHAB", label="Synthetic Rehab", kind="rehab"),
        ZoneRef(zone_id="Z_SOCIAL", label="Synthetic Social Facility", kind="social"),
        ZoneRef(zone_id="Z_DEPOT_1", label="Synthetic Depot 1", kind="depot"),
        ZoneRef(zone_id="Z_DEPOT_2", label="Synthetic Depot 2", kind="depot"),
        ZoneRef(zone_id="Z_DEPOT_3", label="Synthetic Depot 3", kind="depot"),
    ]


def geocode_address_forbidden_in_open_repo(address: str) -> None:
    raise RuntimeError(
        "Real address geocoding must not run in OPEN repo mode; "
        "use zone ids or a PRIVATE customer contour."
    )
