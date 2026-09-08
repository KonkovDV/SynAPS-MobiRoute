# Privacy and security

## Contours

| Contour | Allowed content |
| --- | --- |
| OPEN_SYNTHETIC | Synthetic zones, synthetic trips, public facility categories |
| ANONYMIZED | Pseudonymous IDs, no FIO/phone/address |
| AGGREGATED | Zone-level rates, no individual traces |
| CUSTOMER_PRIVATE | Bookings, fleet, shifts under contract |
| MEDICAL_SENSITIVE | Eligibility/medical details — never in the open repo |

Identity and trip payloads are separate fields (`pseudonymous_passenger_id` vs `trip.id`).
Coordinates are omitted in open synthetic mode (`redact_problem_for_open`).
A provenance label is not proof of anonymization; pseudonymous IDs may remain personal data.

## Rules

- Pseudonymous passenger id ≠ trip id
- No FIO, phones, diagnoses, card numbers, real addresses in git
- **IMPLEMENTED:** `redact_problem_for_open` / `redact_trip_for_open` accept only synthetic
  input, rejecting non-synthetic or mixed problem/trip/passenger provenance and restricted
  passenger privacy classes with `ValueError`. Coordinates are stripped without changing provenance.
- These helpers prepare synthetic fixtures; they do not anonymize customer or medical data.
  Callers remain responsible for truthful labels and safe contents, including free-text fields.
- Do not put PII in logs. `log_safe` masks common email/phone patterns only; it is not a
  general PII detector. `assert_no_pii_fields` checks nested field names, not their contents.
- Retention / access audit: operator responsibility for CUSTOMER_PRIVATE and MEDICAL_SENSITIVE
- Encryption at rest: operator contour, not claimed as a MobiRoute certification

## Certification

**MobiRoute is not a certified personal-data protection system** and does **not** claim
152-FZ compliance unless and until a separate legal and technical assessment is documented.
