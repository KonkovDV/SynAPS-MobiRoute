# Problem input contract

## Implemented validation primitives

- Minute values, capacities, companion counts, quotas and seeds use integer inputs, not Boolean or string coercions. Signed output metrics and negative remaining entitlement are still representable.
- Numeric model fields reject NaN and infinity. Detour ratios must also remain finite after multiplication by 1000.
- `validate_problem(problem)` returns a new canonical `DayProblem`. **Use that returned object**, never validate a reconstruction and then execute the original unchecked copy.
- Reconstruction covers nested dictionaries, raw enum strings and list mutations. Matrix graph caches are rebuilt on the returned snapshot, not copied from the source.
- IDs are nonblank and unique within each entity kind. Depots, service areas and trip locations reference matrix zones. Passenger profiles remain optional metadata.
- Pickup windows, shifts and unavailable intervals are ordered. Zero-length shifts and unavailable intervals remain valid inputs; a closed vehicle may simply be unable to serve demand.
- Input times and packed capacities fit signed i32. Data-dependent bounds additionally cover arrival plus service, VIA direct travel, total seats and accumulated waiting scores. This is a native representation envelope, not a transport-policy limit.
- Appointment start retains its lobby-window meaning; it is not blindly required to precede appointment end. Demands exceeding available capacity or time can be valid but infeasible.

Malformed inputs raise `ValueError`. Well-formed but infeasible requests still need explicit solver rejection reasons.

Entry-point integration and execution regressions are part of the same draft PR. This validation does not establish pilot readiness, legal eligibility or production certification.
