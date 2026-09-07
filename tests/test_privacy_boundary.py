"""Public export is not anonymization; no private-to-synthetic relabelling."""

from unittest import TestCase, main

from mobiroute.domain.models import DataProvenance, PrivacyClass
from mobiroute.domain.requests import DayProblem, PassengerProfile, TravelMatrix, TripRequest
from mobiroute.validation.privacy import (
    assert_no_pii_fields,
    log_safe,
    redact_problem_for_open,
    redact_trip_for_open,
)


def problem() -> DayProblem:
    return DayProblem(
        problem_id="synthetic-audit",
        seed=0,
        passengers=[PassengerProfile(pseudonymous_id="synthetic-p")],
        vehicles=[],
        drivers=[],
        requests=[
            TripRequest(
                id="synthetic-t",
                pseudonymous_passenger_id="synthetic-p",
                pickup_zone="A",
                dropoff_zone="B",
                requested_at=0,
                earliest_pickup=0,
                latest_pickup=30,
                max_ride_time=30,
                max_wait_time=30,
                pickup_coordinates=(0.0, 0.0),
            )
        ],
        travel=TravelMatrix(zones=["A", "B"], minutes=[[0, 5], [5, 0]]),
    )


class TestPrivacyBoundary(TestCase):
    def test_nonsynthetic_problem_is_rejected(self):
        for provenance in DataProvenance:
            if provenance != DataProvenance.SYNTHETIC:
                p = problem().model_copy(update={"data_provenance": provenance})
                with self.subTest(provenance=provenance), self.assertRaises(ValueError):
                    redact_problem_for_open(p)

    def test_nonsynthetic_trip_is_rejected(self):
        for provenance in DataProvenance:
            if provenance != DataProvenance.SYNTHETIC:
                t = problem().requests[0].model_copy(update={"data_provenance": provenance})
                with self.subTest(provenance=provenance), self.assertRaises(ValueError):
                    redact_trip_for_open(t)

    def test_mixed_trip_is_rejected(self):
        p = problem()
        p.requests[0].data_provenance = DataProvenance.MEDICAL_SENSITIVE
        with self.assertRaises(ValueError):
            redact_problem_for_open(p)

    def test_restricted_passenger_is_rejected(self):
        for privacy in PrivacyClass:
            if privacy not in {PrivacyClass.OPEN_SYNTHETIC, PrivacyClass.PUBLIC_SYNTHETIC}:
                p = problem()
                p.passengers[0].privacy_class = privacy
                with self.subTest(privacy=privacy), self.assertRaises(ValueError):
                    redact_problem_for_open(p)

    def test_passenger_provenance_is_checked(self):
        p = problem()
        p.passengers[0].data_provenance = DataProvenance.CUSTOMER_PRIVATE
        with self.assertRaises(ValueError):
            redact_problem_for_open(p)

    def test_synthetic_copy_is_redacted_without_mutating_input(self):
        p = problem()
        redacted = redact_problem_for_open(p)
        self.assertIsNone(redacted.requests[0].pickup_coordinates)
        self.assertEqual(p.requests[0].pickup_coordinates, (0.0, 0.0))
        self.assertEqual(redacted.data_provenance, DataProvenance.SYNTHETIC)

    def test_nested_pii_paths(self):
        payload = {"requests": [{"profile": {"Phone": "synthetic"}}, {"diagnosis": "test"}]}
        self.assertEqual(
            assert_no_pii_fields(payload), ["requests[0].profile.Phone", "requests[1].diagnosis"]
        )
        self.assertEqual(assert_no_pii_fields({"phone": "test"}), ["phone"])

    def test_numeric_email_is_fully_redacted(self):
        self.assertEqual(log_safe("1234567890@example.invalid"), "[REDACTED_EMAIL]")


if __name__ == "__main__":
    main()
