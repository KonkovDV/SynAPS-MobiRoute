#!/usr/bin/env python3
"""CLI wrapper for the synthetic ops benchmark suite."""

from __future__ import annotations

import argparse
from pathlib import Path

from mobiroute.reporting.ops_benchmark import run_suite, write_suite


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    rows = run_suite(args.seed)
    write_suite(rows, args.out_dir, seed=args.seed)
    print(args.out_dir / "ops_summary.csv")


if __name__ == "__main__":
    main()
