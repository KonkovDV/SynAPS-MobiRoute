"""Link to SynAPS, the upstream scheduling engine (manufacturing, FJSP)."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT


def synaps_pin() -> str:
    return SYNAPS_COMMIT


def adapter_status() -> dict[str, object]:
    """The DARP and VRP solvers here are native; compiling a DARP day into a
    SynAPS ScheduleProblem is experimental and off by default."""
    return {
        "synaps_commit": SYNAPS_COMMIT,
        "native_darp": True,
        "fjssp_compile": "NOT_ENABLED",
        "claim": "SynAPS provides determinism/portfolio patterns; DARP domain is separate.",
    }
