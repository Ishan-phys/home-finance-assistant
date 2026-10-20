"""Shared test support for the workspace (development only; never shipped)."""

from pathlib import Path


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "fixtures" / "build_fixtures.py").exists():
            return parent
    raise RuntimeError("cannot find the repository root from cfo.testing")


REPO_ROOT = _find_root()
FIXTURE_DIR = REPO_ROOT / "fixtures"
LEDGER_PACKAGE = REPO_ROOT / "packages" / "cfo-ledger"


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "SeedClient":
        from cfo.testing.seed import SeedClient

        return SeedClient
    raise AttributeError(name)
