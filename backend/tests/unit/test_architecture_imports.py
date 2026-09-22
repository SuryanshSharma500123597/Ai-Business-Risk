"""Architecture rule R3 (frozen: docs/01_architecture/architecture.md §2).

The deterministic core (risk_engine, simulation, ml_engine, data_engine,
guardrails) must never import LLM/application layers (agents, llm, app,
services). Enforced by AST scan so violations are caught without executing
the offending module. Packages that do not exist yet (later phases) are
skipped; the rule activates automatically as each package is created.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

FORBIDDEN_ROOTS = {"agents", "llm", "app", "services"}
DETERMINISTIC_PACKAGES = (
    "risk_engine",
    "simulation",
    "ml_engine",
    "data_engine",
    "guardrails",
)


def _import_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_deterministic_core_never_imports_llm_or_application_layers() -> None:
    violations: list[str] = []
    for package in DETERMINISTIC_PACKAGES:
        package_dir = BACKEND_DIR / package
        if not package_dir.is_dir():
            continue
        for py_file in package_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            bad = _import_roots(tree) & FORBIDDEN_ROOTS
            if bad:
                violations.append(f"{py_file.relative_to(BACKEND_DIR.parent)}: {sorted(bad)}")
    assert not violations, "R3 violations:\n" + "\n".join(violations)
