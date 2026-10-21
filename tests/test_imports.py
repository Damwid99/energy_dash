import ast
import importlib
import pkgutil
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
INTERNAL_TOP_PACKAGES = {
    "app",
    "common",
    "config",
    "energy_dash",
    "etl",
    "ml",
    "models_db",
    "schemas",
    "scripts",
}


def test_import_all_src_modules():
    """Iteruje po wszystkich modułach w src/ i weryfikuje, że dają się zaimportować."""
    failed_modules: dict[str, str] = {}

    for info in pkgutil.walk_packages([str(SRC_DIR)], prefix="src."):
        if "src.app.pages" in info.name or info.name == "src.app.main":
            continue

        try:
            importlib.import_module(info.name)
        except Exception as e:
            failed_modules[info.name] = f"{type(e).__name__}: {e}"

    assert not failed_modules, "Nie udało się zaimportować modułów:\n" + "\n".join(
        f" - {mod}: {err}" for mod, err in failed_modules.items()
    )


def test_no_unprefixed_internal_imports_in_ast():
    """
    Skanuje drzewo AST wszystkich plików .py w src/ (w tym leniwe importy wewnątrz funkcji
    oraz bloki if __name__ == '__main__'), sprawdzając czy żaden import nie pomija prefiksu 'src.'.
    """
    violations: list[str] = []

    for py_file in sorted(SRC_DIR.rglob("*.py")):
        rel_path = py_file.relative_to(SRC_DIR.parent)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top_pkg = node.module.split(".")[0]
                if top_pkg in INTERNAL_TOP_PACKAGES:
                    violations.append(
                        f"{rel_path}:{node.lineno} -> 'from {node.module} import ...' "
                        f"(powinno być: 'from src.{node.module} import ...')"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    if top_pkg in INTERNAL_TOP_PACKAGES:
                        violations.append(
                            f"{rel_path}:{node.lineno} -> 'import {alias.name}' "
                            f"(powinno być: 'import src.{alias.name}')"
                        )

    assert not violations, (
        "Znaleziono wewnętrzne importy bez prefiksu 'src.' (mogą wybuchnąć w runtime):\n"
        + "\n".join(f" - {v}" for v in violations)
    )
