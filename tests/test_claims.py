"""What the README, the docs and the site may say, checked against the repository.

The rule comes from the claims registry of SynAPS-ProgramPlan: a promise the
evidence does not back never appears in a published text, and a number the
site states is recomputed from the files it describes. The verifier is
"independent" only while it shares no code with the search, so that is
checked here too, on the import graph.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Phrases that would claim more than synthetic days and public benchmarks show.
BANNED = (
    "гарантирует оптимальн",
    "гарантированно оптимальн",
    "доказано на данных заказчика",
    "в промышленной эксплуатации",
    "внедрено в",
    "экономия до ",
    "guaranteed optimal",
    "guarantees optimal",
    "production-ready",
    "production ready",
    "saves up to",
    "deployed at",
    "used in production",
    "proven on customer data",
)


def _published() -> list[Path]:
    files = [*ROOT.glob("*.md"), ROOT / "CITATION.cff", ROOT / "site" / "index.html"]
    files += sorted((ROOT / "docs").rglob("*.md"))
    return [path for path in files if path.is_file()]


@pytest.mark.parametrize("path", _published(), ids=lambda p: str(p.relative_to(ROOT)))
def test_published_texts_make_no_overclaims(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    found = [phrase for phrase in BANNED if phrase in text]
    assert not found, f"{path.relative_to(ROOT)}: {found}"


def test_the_instance_count_on_the_site_is_the_number_of_vendored_files() -> None:
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    stated = {int(n) for n in re.findall(r"(\d+) (?:открытых эталонов|public instances)", html)}
    folders = ("cordeau", "solomon", "lilim", "sartori-buriol/n100")
    files = [
        path
        for folder in folders
        for path in (ROOT / "benchmark" / "instances" / folder).iterdir()
        if path.name != "SHA256SUMS.txt"
    ]
    assert stated == {len(files)}


def _module_file(name: str) -> Path | None:
    base = ROOT / "src" / Path(*name.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def _runtime_imports(path: Path) -> set[str]:
    """``mobiroute`` modules imported at run time (``TYPE_CHECKING`` blocks skipped)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    typing_only = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and getattr(node.test, "id", "") == "TYPE_CHECKING"
        for stmt in node.body
        for inner in ast.walk(stmt)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in typing_only:
            continue
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if _module_file(f"{node.module}.{alias.name}") is not None
            )
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return {name for name in found if name.startswith("mobiroute.")}


def test_the_verifier_shares_no_code_with_the_search() -> None:
    """Everything ``verify`` runs: the model, the schedule, the cost, travel times."""
    seen: set[str] = set()
    todo = ["mobiroute.vrp.verify"]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        path = _module_file(name)
        if path is not None and path.name != "__init__.py":
            todo.extend(_runtime_imports(path))
    assert seen == {
        "mobiroute.vrp.verify",
        "mobiroute.vrp.model",
        "mobiroute.vrp.schedule",
        "mobiroute.vrp.solution",
        "mobiroute.vrp.traffic",
    }
