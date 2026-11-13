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
| `solvers` | FIFO, nearest, greedy pooling insertion (Rust `mobiroute_native`), beam, CP-SAT tiny, adaptive ALNS, rolling horizon; LBBD stub |
| `validation` | Feasibility, accessibility, privacy |
| `dispatch` | Online insertion, cancel/no-show, disruption |
| `reporting` | JSON / MD / CSV |
| `cli` | `generate` / `solve` / `demo` |

## Modes

- **Day-ahead:** full known request set (greedy pooling, ALNS, RHC windows, or CP-SAT tiny).
- **Continuous:** insert into **existing** routes; cancel / traffic / breakdown → new plan version + diff + churn.
- Frozen trips are not moved by online insert; if insert would move them, the new request is rejected with a reason code.

## Determinism

- Single-thread CP-SAT workers = 1.
- SHA-256 fingerprints (no `hash()`).
- Stable UUID5 synthetic IDs.

## Literature lane and reporting (0.3.0)

| Module | Role |
| --- | --- |
| `benchmarks/cordeau_exact.py` | Cordeau parser, exact CP-SAT model, compact two-index MIP (SCIP / HiGHS / CBC), LP bound, difference-constraint verifier with why-not certificates, gated literature report |
| `adapters/cordeau.py` | operator-algebra adapter of the same instance and `cordeau_node_routes` for the literature cross-check |
| `reporting/svg.py` | dependency-free route map and timeline of a verified plan |
| `benchmark/solver_lab.py` | one instance through every lane, one verifier; writes JSON and a Markdown table |
| `site/` | static GitHub Pages presentation fed by committed solver-lab and plan data |

The verifier is a separate implementation from every solver: CP-SAT and the MIP
propose routes, Bellman–Ford on the route's constraint graph decides.
