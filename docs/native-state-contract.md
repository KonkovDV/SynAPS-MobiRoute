# Native state lifetime

The native engine and fleet tables remain persistent **within one solve**. Explicit forks and the Rust insertion algorithm are unchanged.

Cross-solve lookup by `event_id`, `plan_id` or `input_hash` is disabled. These are mutable plan metadata, not proof that the current problem and supplied routes match a stored native world. The compatibility hooks neither retain kernels nor return cached kernels.

Online insertion follows its existing cold path: build the engine from the current validated problem, seed the supplied route stop sequences and drivers, then append the validated new request. This removes unbounded global kernel retention and stale matrix/capacity reuse without trusting identifiers or adding a hidden validation bypass.

Regression tests use real Rust engines, unchanged baseline identifiers with changed travel/capacity, and weak references to check that the compatibility hooks do not retain kernels.

## Trade-offs and limits

- Rebuilding adds work per online insertion. Benchmark representative workloads before rollout; this change does not claim a latency SLA.
- Current problem validation and immutable matrix snapshots still apply. Cache isolation does not prove that arbitrary supplied baseline routes are well formed or physically feasible.
- Linked-trip policies, full-plan notary coverage, plan fingerprints and raw-native input safety are separate contracts, not established by removing this cache.
