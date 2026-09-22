"""Enforces the one architectural rule that actually matters over three years
of edits: yfinance is an unofficial scraper that will eventually break, and
when it does, the blast radius must be limited to providers/yfinance_provider.py.
This is a ~15-line grep-test, and it's the only thing standing between that
promise and someone adding `import yfinance` to screen.py six months from now.
"""
import ast
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent
ALLOWED_YFINANCE_IMPORTER = "providers/yfinance_provider.py"
FORBIDDEN_PROVIDER_IMPORTERS = {"store.py", "screen.py", "score.py", "criteria.py", "config.py", "sector_rules.py"}


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_only_yfinance_provider_imports_yfinance():
    offenders = []
    for path in PACKAGE_DIR.rglob("*.py"):
        rel = path.relative_to(PACKAGE_DIR).as_posix()
        if rel == ALLOWED_YFINANCE_IMPORTER or "/tests/" in f"/{rel}":
            continue
        if "yfinance" in _imported_names(path):
            offenders.append(rel)
    assert offenders == [], f"Only {ALLOWED_YFINANCE_IMPORTER} may import yfinance; also found in: {offenders}"


def test_core_modules_do_not_import_providers_package():
    offenders = []
    for name in FORBIDDEN_PROVIDER_IMPORTERS:
        path = PACKAGE_DIR / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "providers" in node.module:
                offenders.append(name)
            if isinstance(node, ast.ImportFrom) and node.level > 0 and node.module is None:
                # `from . import providers` style — check the names imported
                for alias in node.names:
                    if alias.name == "providers":
                        offenders.append(name)
    assert offenders == [], f"These modules must not import providers/: {offenders}"
