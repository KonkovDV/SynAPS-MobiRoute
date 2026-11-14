# Contributing

## Setup

```bash
python -m pip install -e ".[dev]"
python -m pip install maturin
python -m maturin develop --release --manifest-path native/mobiroute_native/Cargo.toml
```

## Before a pull request

```bash
ruff check . && ruff format --check .
mypy && mypy --strict benchmark/*.py examples/*.py
pytest                       # fast suite; exact MIP proofs: pytest -m slow
cargo fmt --manifest-path native/mobiroute_native/Cargo.toml -- --check
cargo clippy --manifest-path native/mobiroute_native/Cargo.toml --release -- -D warnings
```

## Conventions

* **Every plan goes through the verifier.** A new solver or operator is tested
  by checking its output with `mobiroute.vrp.verify.verify` (or `check_plan` in
  the paratransit kernel), not by inspecting its own bookkeeping.
* **Python reference and Rust kernel change together.** `VrpKernel` mirrors
  `vrp/insertion.py` operation for operation. A change to one needs the same
  change in the other in the same commit, and `tests/test_vrp_native.py` must
  stay green: identical plans, identical ALNS trajectories.
* **Numbers come from scripts.** Tables in `docs/benchmarks/` are written by
  the scripts in `benchmark/`; re-run the script instead of editing a table.
  Heuristics never publish `OPTIMAL`.
* **No personal data.** Only public benchmark instances and synthetic days.
  Example inputs are written by a script in `examples/`; change the script and
  re-run it rather than editing the JSON (a test compares the two).
* **Errors are codes.** Raise `ValueError` with a stable code first
  (`GEO_UNKNOWN_DEPOT:van`, `VRP_CAPACITY_INVALID:van`) and test for the code;
  the CLI turns it into one line on stderr and exit status 2.
* **A solver says what it does not model.** A solver that ignores a rule of the
  instance (rests, trips, traffic) refuses it with an error code instead of
  returning a plan that silently breaks the rule.
* **Commits** use a short prefix: `feat`, `fix`, `perf`, `test`, `docs`,
  `bench`, `data`, `build`, `chore`. Keep diffs focused and update
  `CHANGELOG.md` for user-visible changes.
