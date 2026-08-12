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

## Rules

- Pseudonymous passenger id ≠ trip id
- No FIO, phones, diagnoses, card numbers, real addresses in git
- Coordinates only in protected mode; stripped by `redact_problem_for_open`
- No PII in logs (`log_safe`)
- Retention / access audit: operator responsibility for CUSTOMER_PRIVATE and MEDICAL_SENSITIVE
- Encryption at rest: operator contour, not claimed as a MobiRoute certification

## Certification

**MobiRoute is not a certified personal-data protection system** and does **not** claim
152-FZ compliance unless and until a separate legal and technical assessment is documented.
