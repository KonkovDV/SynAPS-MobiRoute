"""Versioned laboratory operator policy, separate from solver capability.

This is not operator approval, legal pooling permission, billing, or a driver
command channel. Missing approval stays explicit. Laboratory generators may
allow pooling as an evaluation mode; that does not import another jurisdiction.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from mobiroute.domain.models import StrictModel


class PoolingMode(StrEnum):
    """Whether passengers may share a vehicle at the same time."""

    FORBIDDEN = "FORBIDDEN"
    OPT_IN = "OPT_IN"
    ALLOWED = "ALLOWED"


class ChainMode(StrEnum):
    """All-or-none groups are independent of same-vehicle/adjacency links."""

    ADVISORY = "ADVISORY"
    MANDATORY = "MANDATORY"


class QuotaDebitBasis(StrEnum):
    """How passenger-day entitlement is charged, distinct from ride clocks."""

    RIDE_DURATION = "RIDE_DURATION"
    BILLABLE_SERVICE = "BILLABLE_SERVICE"


class DispatchAuthority(StrEnum):
    """This kernel never issues driver commands or automatic refusals."""

    NONE = "NONE"
    SHADOW = "SHADOW"


class OperatorPolicy(StrictModel):
    policy_id: str = "laboratory.implicit"
    policy_version: str = "1"
    provenance: str = "laboratory:implicit_default"
    approved_by: str | None = None
    pooling_mode: PoolingMode = PoolingMode.ALLOWED
    chain_mode: ChainMode = ChainMode.ADVISORY
    quota_debit_basis: QuotaDebitBasis = QuotaDebitBasis.RIDE_DURATION
    dispatch_authority: DispatchAuthority = DispatchAuthority.NONE

    def fingerprint_tuple(self) -> tuple[object, ...]:
        return (
            self.policy_id,
            self.policy_version,
            self.provenance,
            self.approved_by,
            self.pooling_mode.value,
            self.chain_mode.value,
            self.quota_debit_basis.value,
            self.dispatch_authority.value,
        )


def laboratory_policy(**updates: object) -> OperatorPolicy:
    return OperatorPolicy.model_validate(updates) if updates else OperatorPolicy()


class TimeAccounting(StrictModel):
    ride_duration: int = Field(ge=0, strict=True)
    quota_debit: int = Field(ge=0, strict=True)
    billable_service: int = Field(ge=0, strict=True)
