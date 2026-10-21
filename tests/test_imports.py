import ast
import importlib
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "src" / "energy_dash"

LEGACY_OR_UNPREFIXED_PACKAGES = {
    "src",
    "app",
    "common",
    "config",
    "core",
    "etl",
    "features",
    "ml",
    "models_db",
    "schemas",
    "scripts",
}

PURE_MODULES = [
    PACKAGE_DIR / "core" / "timeutils.py",
    PACKAGE_DIR / "features" / "bess" / "battery.py",
    PACKAGE_DIR / "features" / "bess" / "strategies.py",
    PACKAGE_DIR / "features" / "bess" / "settlement.py",
    PACKAGE_DIR / "features" / "bess" / "prices.py",
    PACKAGE_DIR / "features" / "forecasting" / "features.py",
    PACKAGE_DIR / "features" / "forecasting" / "metrics.py",
]

FORBIDDEN_IN_PURE = {
    "streamlit",
    "mlflow",
    "sqlalchemy",
    "psycopg",
    "psycopg2",
    "litellm",
    "energy_dash.core.settings",
    "energy_dash.core.db",
    "energy_dash.core.llm",
    "energy_dash.core.http",
}


def _file_to_module_name(py_file: Path) -> str:
    rel = py_file.relative_to(PACKAGE_DIR.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def test_import_all_energy_dash_modules():
    """Iteruje po wszystkich modułach w src/energy_dash/ i weryfikuje, że dają się zaimportować."""
    failed_modules: dict[str, str] = {}
    skip_modules = {
        "energy_dash.app.main",
        "energy_dash.etl.__main__",
    }

    for py_file in sorted(PACKAGE_DIR.rglob("*.py")):
        mod_name = _file_to_module_name(py_file)
        if mod_name in skip_modules:
            continue

        try:
            importlib.import_module(mod_name)
        except Exception as e:
            failed_modules[mod_name] = f"{type(e).__name__}: {e}"

    assert not failed_modules, "Nie udało się zaimportować modułów:\n" + "\n".join(
        f" - {mod}: {err}" for mod, err in failed_modules.items()
    )


def test_no_legacy_or_unprefixed_internal_imports_in_ast():
    """
    Skanuje drzewo AST wszystkich plików .py w src/energy_dash/, sprawdzając czy żaden import
    nie używa starego prefiksu 'src.' ani nie pomija prefiksu 'energy_dash.'.
    """
    violations: list[str] = []

    for py_file in sorted(PACKAGE_DIR.rglob("*.py")):
        rel_path = py_file.relative_to(PACKAGE_DIR.parent.parent)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top_pkg = node.module.split(".")[0]
                if top_pkg in LEGACY_OR_UNPREFIXED_PACKAGES:
                    violations.append(
                        f"{rel_path}:{node.lineno} -> 'from {node.module} import ...' "
                        f"(wszystkie wewnętrzne importy muszą zaczynać się od 'energy_dash.')"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    if top_pkg in LEGACY_OR_UNPREFIXED_PACKAGES:
                        violations.append(
                            f"{rel_path}:{node.lineno} -> 'import {alias.name}' "
                            f"(wszystkie wewnętrzne importy muszą zaczynać się od 'energy_dash.')"
                        )

    assert not violations, "Znaleziono stare lub nieprefiksowane importy wewnętrzne:\n" + "\n".join(
        f" - {v}" for v in violations
    )


def test_pure_modules_have_no_forbidden_io_dependencies():
    """
    Pilnuje czystości modułów przeznaczonych do wydzielenia do energy_core (Etap 7):
    brak importów streamlit, mlflow, sqlalchemy, psycopg oraz energy_dash.core.{settings,db,llm,http}.
    """
    violations: list[str] = []

    for py_file in PURE_MODULES:
        assert py_file.exists(), f"Brak oczekiwanego czystego modułu: {py_file}"
        rel_path = py_file.relative_to(PACKAGE_DIR.parent.parent)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel_path))

        for node in ast.walk(tree):
            imported_names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_names.append(node.module)
            elif isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)

            for mod in imported_names:
                top = mod.split(".")[0]
                if top in FORBIDDEN_IN_PURE or mod in FORBIDDEN_IN_PURE:
                    violations.append(
                        f"{rel_path}:{node.lineno} -> niedozwolony import '{mod}'"  # type: ignore[attr-defined]
                    )

    assert not violations, (
        "Czyste moduły importują zależności I/O lub konfiguracyjne:\n"
        + "\n".join(f" - {v}" for v in violations)
    )


def test_queries_modules_do_not_import_streamlit():
    """Pilnuje zasady czystych zapytań: żaden plik features/*/queries.py nie może importować streamlit."""
    violations: list[str] = []

    for py_file in sorted((PACKAGE_DIR / "features").glob("*/queries.py")):
        rel_path = py_file.relative_to(PACKAGE_DIR.parent.parent)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel_path))

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] == "streamlit"
            ):
                violations.append(f"{rel_path}:{node.lineno} -> from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "streamlit":
                        violations.append(f"{rel_path}:{node.lineno} -> import {alias.name}")

    assert not violations, "Moduły queries.py nie mogą zależeć od streamlit:\n" + "\n".join(
        f" - {v}" for v in violations
    )
