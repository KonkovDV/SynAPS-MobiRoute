"""Optional SynAPS adapter — documents mapping boundaries; no FJSP pollution."""

from __future__ import annotations

from mobiroute import SYNAPS_COMMIT


def synaps_pin() -> str:
    return SYNAPS_COMMIT


def adapter_status() -> dict[str, object]:
    """
    MobiRoute v0 uses native DARP solvers.
    Compiling DARP → SynAPS ScheduleProblem is EXPERIMENTAL / NOT enabled by default.
    """
    return {
        "synaps_commit": SYNAPS_COMMIT,
        "native_darp": True,
        "fjssp_compile": "NOT_ENABLED",
        "claim": "SynAPS provides determinism/portfolio patterns; DARP domain is separate.",
    }
