import importlib
import pkgutil
from pathlib import Path


def test_import_all_src_modules():
    """Iterates through all modules inside src/ and verifies they can be imported."""
    src_path = Path(__file__).resolve().parent.parent / "src"

    failed_modules: dict[str, str] = {}

    for info in pkgutil.walk_packages([str(src_path)], prefix="src."):
        if "src.app.pages" in info.name:
            continue

        try:
            importlib.import_module(info.name)
        except Exception as e:
            failed_modules[info.name] = str(e)

    assert not failed_modules, "Nie udało się zaimportować modułów:\n" + "\n".join(
        f" - {mod}: {err}" for mod, err in failed_modules.items()
    )
