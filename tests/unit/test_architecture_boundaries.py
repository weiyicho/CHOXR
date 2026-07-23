import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_engine_never_imports_outer_layers() -> None:
    forbidden = {"adapters", "strategies", "app", "legacy"}
    violations: list[str] = []

    for path in sorted((REPOSITORY_ROOT / "engine").rglob("*.py")):
        found = imported_roots(path) & forbidden
        if found:
            violations.append(f"{path.relative_to(REPOSITORY_ROOT)}: {sorted(found)}")

    assert violations == []


def test_active_python_never_imports_legacy() -> None:
    violations: list[str] = []
    for package in ("engine", "adapters", "strategies", "app"):
        for path in sorted((REPOSITORY_ROOT / package).rglob("*.py")):
            if "legacy" in imported_roots(path):
                violations.append(str(path.relative_to(REPOSITORY_ROOT)))

    assert violations == []
