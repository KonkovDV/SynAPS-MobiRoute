# Security

## Supported versions

| Version | Supported |
| --- | --- |
| 0.5.x | yes |
| < 0.5 | no |

## Reporting a vulnerability

Use a private GitHub security advisory:
https://github.com/KonkovDV/SynAPS-MobiRoute/security/advisories/new

Please do not open a public issue for a vulnerability.

## Data

The repository contains public benchmark instances and synthetic data only.
Do not commit, attach or paste real addresses, phone numbers, personal or
medical data, or GPS tracks — in code, issues or pull requests.

## Network

The library makes no network calls unless asked to. The only one is
`mobiroute.vrp.geo.osrm_source` (`vrp-solve --osrm URL`): it sends the
coordinates of every depot and stop to that URL to get road matrices. Point it
at a server you run yourself if the coordinates are not public. Responses are
parsed as JSON and checked (`GEO_OSRM_*` errors); nothing else is fetched.

Dependencies are audited on every push and weekly: `pip-audit` for Python
packages and `cargo audit` for the Rust crate (`.github/workflows/security.yml`).
