#!/usr/bin/env python3
"""CLI wrapper for synthetic day generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobiroute.adapters.synthetic_data import generate_day


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="tiny")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    day = generate_day(mode=args.mode, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(day.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(args.out)


if __name__ == "__main__":
    main()
