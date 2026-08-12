# Privacy and security

## Contours

| Contour | Allowed content |
| --- | --- |
| OPEN | Synthetic zones, synthetic trips, public facility categories |
| PRIVATE | Real IDs, eligibility, medical details, addresses, GPS |
| CUSTOMER | Bookings, fleet, shifts, KPIs under contract |

## Rules

- Pseudonymous passenger id ≠ trip id  
- No FIO, phones, diagnoses, card numbers, real addresses in git  
- Coordinates only in protected mode; stripped by `redact_problem_for_open`  
- No PII in logs (`log_safe`)  
- Tenant isolation is an integration requirement (not fully implemented as multi-tenant SaaS)  
- Encryption / retention / access audit: operator responsibility for PRIVATE data  

## Certification

**MobiRoute is not a certified personal-data protection system** unless and until
a separate certification is obtained and documented. Absence of certification is
intentional at prototype stage.
