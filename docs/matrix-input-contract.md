# Travel matrix input contract

IMPLEMENTED: `TravelMatrix` is an immutable snapshot. JSON still uses arrays;
Python callers may supply lists or tuples. Validated storage uses tuples.

- Zone IDs are nonempty and unique; the matrix is square with a zero diagonal.
- Edge minutes are strict integers in `[0, 10**9]`; booleans are not minutes.
- `10**9` is the existing unreachable-edge sentinel. Empty graphs are valid.
- Floyd–Warshall runs once per snapshot, not once per lookup.
- `model_copy(update=...)` validates a fresh snapshot and does not copy graph caches.

Replace the snapshot instead of mutating its rows:

```python
updated = original.model_copy(update={"minutes": [[0, 30], [30, 0]]})
```

Supply the complete replacement matrix, with dimensions matching the zones.
This contract does not validate an entire planning problem or certify pilot readiness.
