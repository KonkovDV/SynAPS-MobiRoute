# Architecture

## Separation of concerns

```
Operator stack (CRM, CAD/AVL, apps) ──ingest──► MobiRoute kernel ──plan/diff──► Operator
                                                      │
                                                      ├── native DARP solvers
                                                      └── optional SynAPS pin (patterns / future compile)
```

Manufacturing FJSP models from SynAPS are **not** imported into the DARP domain.

## Packages

| Package | Role |
| --- | --- |
| `domain` | Passengers, vehicles, `DriverAssignment`, route graph, fairness |
| `adapters` | Synthetic data, fingerprints, SynAPS pin |
| `solvers` | FIFO, nearest, greedy pooling insertion (Rust `mobiroute_native`), beam, CP-SAT tiny, adaptive ALNS (Shaw/worst/route/random + SA); LBBD/RHC stubs |
| `validation` | Feasibility, accessibility, privacy |
| `dispatch` | Online insertion, cancel/no-show, disruption |
| `reporting` | JSON / MD / CSV |
| `cli` | `generate` / `solve` / `demo` |

## Modes

- **Day-ahead:** solve full known request set (greedy pooling or CP-SAT tiny).
- **Continuous:** insert into **existing** routes; cancel / traffic / breakdown → new plan version + diff + churn.
- Frozen trips are not moved by online insert; if insert would move them, the new request is rejected with a reason code.

## Determinism

- Single-thread CP-SAT workers = 1.
- SHA-256 fingerprints (no `hash()`).
- Stable UUID5 synthetic IDs.
