#!/usr/bin/env python3
"""Moscow-zone synthetic generator entrypoint (project-brief name)."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("generate_day.py")), run_name="__main__")
