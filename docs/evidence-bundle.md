# Evidence bundle: what ships with every published number

**Status:** normative for this repository since 0.2.7 · **Owner:** MobiRoute core · **Last updated:** 2026-09-10

A green CI badge is not a benchmark result. This document defines the minimum
artifact set that must accompany any number we publish in a deck, an
application form, a README or a paper. If a number cannot be shipped with its
bundle, the number does not get published.

## 1. Why

An external review of this project (2026-09-08) found that the repository
mixed three different things under one green checkmark:

1. lint/type/test success (what CI actually proves),
2. feasibility of a produced plan (what the plan notary proves),
3. comparability with published literature results (what nothing proved).

The fix is mechanical: separate the three, and attach provenance to each.

## 2. Required fields

Every benchmark or demo run publishes `BenchmarkEvidence`
(`src/mobiroute/benchmarks/academic.py`):

| Field | Why a reviewer needs it |
| --- | --- |
| `mobiroute_version`, `synaps_commit` | pins the code and the SynAPS kernel contract |
| `python_version`, `platform` | interpreter and OS differences change timings and tie-breaks |
| `native_available`, `insertion_backend` | states whether the Rust insertion kernel was actually used |
| `instance_path`, `instance_sha256` | proves which bytes were solved |
| `solver`, `seed` | makes the run repeatable |
| `input_hash`, `config_hash` | detects silent input or policy drift |
| `plan_id` | links the number to the exact emitted plan |
| `wall_clock_seconds` | timing claims are meaningless without it |
| `notary_feasible`, `notary_violations` | separates "produced" from "verified feasible" |
| `exit_code` | records aborted and failed runs instead of hiding them |

A published set of runs must also disclose **failed and aborted runs**. Reporting
only the successful subset is selection bias, not a benchmark.

## 3. Claim gate

`build_academic_report` computes `gap_percent` only when *all* of the following
hold; otherwise the gap is `None` and the reasons are listed in
`gap_blockers`:

| Gate | Blocker code when it fails |
| --- | --- |
| Run used the literature profile (no operator policy) | `PROFILE_NOT_LITERATURE` |
| Cost algebra reproduces the reference algebra | `ALGEBRA_NOT_COMPARABLE` |
| Plan is notary-verified feasible | `PLAN_NOT_VERIFIED` |
| Status is `OPTIMAL`, `FEASIBLE` or `HEURISTIC_FEASIBLE` | `STATUS_NOT_COMPARABLE` |
| Every request in the instance is served | `SERVICE_INCOMPLETE` |
| Served and rejected sets cover the instance | `ACCOUNTING_INCOMPLETE` |
| A positive reference objective is supplied | `NO_REFERENCE_OBJECTIVE` |

Today `ALGEBRA_NOT_COMPARABLE` is permanently set for Cordeau instances: the
vendored loader rounds Euclidean travel to integer minutes and adds curb dwell,
which the published tables do not. Removing that blocker requires a loader that
reproduces the reference algebra, not a configuration flag.

## 4. How to produce a bundle

```bash
mobiroute academic-benchmark \
  --instance benchmark/instances/cordeau/a2-16.txt \
  --solver greedy \
  --out-dir out/a2-16
```

Outputs `out/a2-16/academic_benchmark.json` with two objects: `report`
(claim gate) and `evidence` (reproducibility stamp). Publish the file, not a
screenshot of a number from it.

## 5. What a green CI badge does and does not prove

| Green job | Proves | Does not prove |
| --- | --- | --- |
| `lint` | style and import order | correctness |
| `typecheck` | mypy strict passes | runtime feasibility |
| `test` | asserted invariants hold on the pinned instance and synthetic days | performance, comparability, real-world validity |
| `synaps-pin` | the SynAPS commit pin matches | that the pinned kernel is correct |
| `native-accelerator` | the Rust extension builds and matches Python results | any speed claim |

## 6. Publication rules

1. No gap without an empty `gap_blockers` list.
2. No timing claim without `wall_clock_seconds`, machine description and repeat count.
3. No "verified" without `notary_feasible == true`.
4. No aggregate over runs without disclosing the failed runs in the same table.
5. Any number older than the current `mobiroute_version` is re-run or labelled with its version.
