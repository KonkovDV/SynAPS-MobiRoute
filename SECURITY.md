# Security

## Supported versions

| Version | Supported |
| --- | --- |
| 0.4.x | yes |
| < 0.4 | no |

## Reporting a vulnerability

Use a private GitHub security advisory:
https://github.com/KonkovDV/SynAPS-MobiRoute/security/advisories/new

Please do not open a public issue for a vulnerability.

## Data

The repository contains public benchmark instances and synthetic data only.
Do not commit, attach or paste real addresses, phone numbers, personal or
medical data, or GPS tracks — in code, issues or pull requests.

Dependencies are audited on every push and weekly: `pip-audit` for Python
packages and `cargo audit` for the Rust crate (`.github/workflows/security.yml`).
