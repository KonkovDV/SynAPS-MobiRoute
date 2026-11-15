"""What the README, the docs and the site may say, checked against the repository.

The rule comes from the claims registry of SynAPS-ProgramPlan: a promise the
evidence does not back never appears in a published text, and a number the
site states is recomputed from the files it describes. The verifier is
"independent" only while it shares no code with the search, so that is
checked here too, on the import graph.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

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


#: Strong copyleft (GPL, AGPL, any version); LGPL and MPL are not matched.
COPYLEFT = re.compile(r"(?<![\w-])A?GPL(?:v?\d|-\d|\b)|GNU (?:Affero )?General Public License")


def _dependencies(root: str, extras: tuple[str, ...]) -> dict[str, Distribution]:
    """Installed distributions ``root[extras]`` pulls in, transitively."""
    found: dict[str, Distribution] = {}
    todo = [(root, extras)]
    while todo:
        name, wanted = todo.pop()
        key = canonicalize_name(name)
        if key in found:
            continue
        try:
            found[key] = distribution(name)
        except PackageNotFoundError:
            continue
        for raw in found[key].requires or []:
            req = Requirement(raw)
            envs = [{"extra": extra} for extra in wanted] or [{"extra": ""}]
            if req.marker is None or any(req.marker.evaluate(env) for env in envs):
                todo.append((req.name, tuple(req.extras)))
    return found


def test_no_dependency_is_under_gpl_or_agpl() -> None:
    """Users of this MIT package inherit no copyleft duty from a dependency.

    Runtime and development dependencies, transitively, by their licence
    expression, licence field and licence classifiers. LGPL and MPL pass:
    their terms do not reach code that only imports the library.
    """
    tree = _dependencies("synaps-mobiroute", ("dev",))
    assert "ortools" in tree and "pytest" in tree
    copyleft = {}
    for key, dist in tree.items():
        meta = dist.metadata
        texts = [meta.get("License-Expression") or "", (meta.get("License") or "")[:200]]
        texts += [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        hits = [t for t in texts if COPYLEFT.search(t)]
        if hits:
            copyleft[key] = hits
    assert not copyleft


def test_the_published_test_count_is_the_fast_suite() -> None:
    """README and the site name the number ``pytest`` collects, slow proofs aside."""
    stated = set()
    for path, pattern in (
        (ROOT / "README.md", r"(\d+) тестов"),
        (ROOT / "README.en.md", r"(\d+) tests"),
        (ROOT / "site" / "index.html", r"(\d+) (?:тестов|tests)"),
    ):
        stated.update(int(n) for n in re.findall(pattern, path.read_text(encoding="utf-8")))
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-m",
            "not slow",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    match = re.search(r"(\d+)(?:/\d+)? tests collected", proc.stdout)
    assert match is not None, proc.stdout
    assert stated == {int(match.group(1))}


def test_workflows_pin_every_action_by_commit() -> None:
    """A floating tag can change under a green run; the workflows pin the commit."""
    uses = re.compile(r"^\s*-?\s*uses:\s*(\S+)")
    floating = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = uses.search(line.split("#", 1)[0])
            if found is None:
                continue
            ref = found.group(1).rsplit("@", 1)[-1]
            if re.fullmatch(r"[0-9a-f]{40}", ref) is None:
                floating.append(f"{path.name}:{lineno}: {found.group(1)}")
    assert not floating


def test_the_docs_do_not_leave_traffic_and_split_breaks_on_python() -> None:
    """Since 0.6 the Rust kernel runs both; a leftover sentence would describe 0.5."""
    native = (ROOT / "docs" / "native-acceleration.md").read_text(encoding="utf-8")
    rules = (ROOT / "docs" / "benchmarks" / "rules.md").read_text(encoding="utf-8")
    cargo = (ROOT / "docs" / "cargo-vrp.md").read_text(encoding="utf-8")
    comparison = (ROOT / "docs" / "comparison.md").read_text(encoding="utf-8")
    assert "time-dependent travel always run" not in native
    assert "covers static travel times" not in rules
    assert "эталоне Python" not in cargo
    assert "эталон на Python" not in comparison
    assert "split breaks and traffic in the Rust kernel" not in comparison


def test_the_plant_note_names_the_orders_no_vehicle_can_carry() -> None:
    """docs/industrial-transport.md explains the two orders the plant day leaves out."""
    from mobiroute.vrp.generators import plant_day

    inst = plant_day(11, n_moves=140)
    nobody = {
        req.id
        for req in inst.requests
        if not any(
            req.skills <= vt.skills
            and all(q <= c for q, c in zip(req.demand, vt.capacity, strict=True))
            for vt in inst.vehicle_types
        )
    }
    assert nobody == {"M020", "M120"}
    text = (ROOT / "docs" / "industrial-transport.md").read_text(encoding="utf-8")
    assert all(order in text for order in nobody)
