# Contributing

Thanks for interest in SynAPS-MobiRoute.

## Scope

This repository is an **optimization kernel**, not a passenger app or eligibility CRM.
Prefer changes that strengthen:

- correctness and feasibility checking
- determinism / reproducibility
- explainability (reason codes, plan diffs)
- privacy (no PII in open artifacts)
- honest claims (synthetic vs customer evidence)

## Development

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
ruff check src tests benchmark
ruff format src tests benchmark
pytest
mypy
```

Greedy / beam / ALNS require `mobiroute_native`. See `docs/native-acceleration.md`.

## Claims hygiene

- Do not claim Moscow operational improvement without a documented pilot.
- Do not mark GREEDY / NEAREST / ALNS / RHC as `OPTIMAL`.
- Do not commit real passenger addresses, phones, medical data, or GPS tracks.
- Mark new capabilities with IMPLEMENTED / PARTIAL / PLANNED status in docs.

## Pull requests

1. Keep diffs focused.
2. Add or update tests for constraint / adversarial cases.
3. Update `CHANGELOG.md` for user-visible changes.
4. Fill the PR template.

## Security

See `SECURITY.md`. Never open public issues containing personal or medical data.
