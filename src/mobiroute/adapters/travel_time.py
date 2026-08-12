"""Travel-time adapter — synthetic matrix now; external engines later."""

from __future__ import annotations

from mobiroute.domain.models import ZoneId
from mobiroute.domain.requests import TravelMatrix


class TravelTimeService:
    def __init__(self, matrix: TravelMatrix):
        self.matrix = matrix

    def minutes(self, origin: ZoneId, destination: ZoneId) -> int:
        return self.matrix.travel(origin, destination)

    def apply_traffic_delay(self, delay_minutes: int) -> TravelMatrix:
        """Uniform additive delay (deterministic disruption model for v0)."""
        if delay_minutes <= 0:
            return self.matrix
        minutes = [
            [0 if i == j else cell + delay_minutes for j, cell in enumerate(row)]
            for i, row in enumerate(self.matrix.minutes)
        ]
        return TravelMatrix(zones=list(self.matrix.zones), minutes=minutes)
