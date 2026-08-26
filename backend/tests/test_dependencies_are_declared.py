"""Every distribution this backend imports is named in its own `pyproject.toml`.

The rule is worth a test rather than a comment because the failure it prevents is
invisible here: a package that arrives transitively imports and runs perfectly in
this repo, and only breaks in the project of a reader who lifted the file. What
they get is an `ImportError` naming a package their own `pyproject.toml` never
mentions, in code that worked when they copied it.

`agent/tools.py` already said so in prose -- "a transitive floor is somebody
else's promise" -- while three of this backend's own imports were relying on
exactly that. So the check reads the source rather than the sentence.

Scope is the whole backend, tests included, and there is deliberately no
allow-list: an exception is how the rule stops being a rule.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import tomllib
from importlib.metadata import packages_distributions

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Packages that live in this repository, so nothing on PyPI supplies them.
LOCAL = {"agent", "board", "demo", "tests"}


def test_every_imported_distribution_is_declared() -> None:
    declared = _declared()
    provided_by = packages_distributions()

    undeclared: dict[str, tuple[str, str]] = {}
    for module, source in sorted(_imported_modules()):
        for distribution in provided_by.get(module, ()):
            if _canonical(distribution) not in declared:
                undeclared[distribution] = (module, source)

    assert not undeclared, "imported directly but not declared in pyproject.toml: " + ", ".join(
        f"{distribution} (`import {module}` in {source})"
        for distribution, (module, source) in sorted(undeclared.items())
    )


def test_the_check_can_see_a_third_party_import() -> None:
    """Guard the guard: a scan that silently found nothing would pass forever."""
    provided_by = packages_distributions()
    modules = {module for module, _ in _imported_modules()}

    assert any(module in provided_by for module in modules)


def _declared() -> set[str]:
    """Every distribution named in `dependencies` or a dependency group."""
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    requirements = list(config["project"]["dependencies"])
    for group in config.get("dependency-groups", {}).values():
        requirements.extend(entry for entry in group if isinstance(entry, str))
    return {_canonical(_name_of(requirement)) for requirement in requirements}


def _name_of(requirement: str) -> str:
    """The distribution out of a PEP 508 string, extras and version dropped."""
    for separator in ("[", ">", "<", "=", "!", "~", ";", " "):
        requirement = requirement.split(separator, 1)[0]
    return requirement.strip()


def _canonical(name: str) -> str:
    """PEP 503 normalisation, so `Django` and `django` are one name."""
    return name.lower().replace("_", "-").replace(".", "-")


def _imported_modules() -> set[tuple[str, str]]:
    """Every top-level module imported anywhere in the backend, with one source."""
    found: set[tuple[str, str]] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts or "migrations" in path.parts:
            continue
        source = str(path.relative_to(BACKEND))
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                if root not in LOCAL and root not in sys.stdlib_module_names:
                    found.add((root, source))
    return found
