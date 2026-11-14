# Examples

Every file here is synthetic. None of them describes a real company, its
customers, passengers or orders.

## Cargo VRP in coordinates

| File | What |
| --- | --- |
| [chelny-day.geo.json](chelny-day.geo.json) | a delivery day in Naberezhnye Chelny, format `mobiroute.vrp.geo.v1`: one warehouse, three suppliers, 45 orders (deliveries from the warehouse and supplier-to-customer transfers) in morning, midday and afternoon slots; own and hired vans and trucks, the 4.5 h / 45 min rest rule, two trips for own vans |
| [make_chelny_day.py](make_chelny_day.py) | the generator of that file: points uniformly at random inside the city's bounding box, names marked "условн." (conventional), seed 1 |

```bash
python examples/make_chelny_day.py --seed 1 --orders 45     # rewrites chelny-day.geo.json
mobiroute vrp-solve --geo examples/chelny-day.geo.json --sheets --out-dir out-chelny
mobiroute vrp-solve --geo examples/chelny-day.geo.json --osrm http://localhost:5000 --sheets --out-dir out-osrm
```

The format is described in [docs/cargo-vrp.md](../docs/cargo-vrp.md) and in
the docstring of `mobiroute.vrp.geo`. A test checks that the file is exactly
what the generator writes, so edit the generator, not the JSON.

To try it on real roads, start an OSRM server on an OpenStreetMap extract of
the region (see the [OSRM backend documentation](https://github.com/Project-OSRM/osrm-backend))
and pass its URL with `--osrm`. The coordinates of the orders are then sent to
that server and nowhere else.

## Paratransit kernel

Fixtures of the DARP kernel ([docs/darp-kernel.md](../docs/darp-kernel.md)),
schema `mobiroute.problem.v1`, synthetic Moscow-zone days with seed 42:

| File | Scenario |
| --- | --- |
| [tiny_day.json](tiny_day.json) | 20 requests, 5 vehicles |
| [wheelchair_day.json](wheelchair_day.json) | 40 requests, a high share of wheelchair users |
| [medical_priority_day.json](medical_priority_day.json) | 30 requests with medical priorities |
| [disruption_day.json](disruption_day.json) | 20 requests and a mid-day disruption |
| [fairness_stress_day.json](fairness_stress_day.json) | 40 requests that stress the fairness metrics |

They were written by an earlier version of `mobiroute generate` and are kept
as fixed inputs for the tests; `mobiroute generate --mode <mode> --seed 42`
writes current days of the same kinds.
