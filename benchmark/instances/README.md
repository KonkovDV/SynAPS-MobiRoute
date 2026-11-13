# Vendored benchmark instances

Public academic instances, kept byte for byte (`.gitattributes` marks the
folder `-text`, so line endings are never rewritten). Every folder has a
`SHA256SUMS.txt`; readers and benchmark scripts hash the bytes they solve, and
a published reference applies only to those exact bytes.

| Folder | Problem | Files | Source of the files | Reference values |
| --- | --- | ---: | --- | --- |
| `cordeau/` | DARP: paired requests, ride limit, route duration | 48 (sets a, b) | Cordeau's DARP page, HEC Montréal (`neumann.hec.ca/chairedistributique/data/darp/branch-and-cut/`) | optima of Ropke, Cordeau & Laporte (2007) as compiled by Ho et al. (2018) — `../references/cordeau.json` |
| `solomon/` | VRPTW, 100 customers | 56 | mirror in `iRB-Lab/py-ga-vrptw` (`data/text/`); C101 is byte-identical in a second mirror (`reinterpretcat/vrp`) | SINTEF TOP best known (vehicles, then distance), cross-checked row by row with Czech & Czarnas' 5-decimal table — `../references/solomon.json` |
| `lilim/` | PDPTW, 106 tasks | 1 (LC101) | mirror in `reinterpretcat/vrp` | 10 vehicles / 828.94 (SINTEF TOP) |
| `sartori-buriol/n100/` | PDPTW on real road networks (OSRM minutes, Barcelona, Berlin, New York, Porto Alegre) | 25 | Mendeley Data `wr2ct4r22f` v2, `n100.zip` (SHA-256 `b8c6a9ae…92d` as published by Mendeley) | best known from `cssartori/pdptw-instances` (retrieved 2026-11-13) — `../references/sartori-buriol-n100.json` |

`cordeau/a2-16.txt` keeps the CRLF line endings it was first vendored with;
the other Cordeau files are LF exactly as served. The content of a2-16 is
identical to the original modulo line endings.

## Citations

* J.-F. Cordeau (2006). A branch-and-cut algorithm for the dial-a-ride problem.
  *Operations Research* 54(3):573–586.
* S. Ropke, J.-F. Cordeau, G. Laporte (2007). Models and branch-and-cut
  algorithms for pickup and delivery problems with time windows. *Networks*
  49(4):258–272.
* S.C. Ho et al. (2018). A survey of dial-a-ride problems: literature review and
  recent developments. *Transportation Research Part B* 111:395–421.
* M.M. Solomon (1987). Algorithms for the vehicle routing and scheduling
  problems with time window constraints. *Operations Research* 35(2):254–265.
* H. Li, A. Lim (2001). A metaheuristic for the pickup and delivery problem with
  time windows. *Proc. 13th IEEE ICTAI*, 160–167.
* C.S. Sartori, L.S. Buriol (2020). A study on the pickup and delivery problem
  with time windows: matheuristics and new instances. *Computers & Operations
  Research* 124:105065.

Larger Sartori–Buriol groups (200 to 5000 locations, up to 500 MB) are not
vendored; they can be downloaded from the same Mendeley dataset and read with
`mobiroute.vrp.io.parse_sartori_buriol`.
