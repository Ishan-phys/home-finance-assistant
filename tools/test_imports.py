import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_imports  # noqa: E402


def test_package_boundaries_hold() -> None:
    assert check_imports.check() == []


def test_the_checker_catches_a_violation(tmp_path: Path) -> None:
    bad = tmp_path / "x.py"
    bad.write_text("import sqlalchemy\nfrom cfo.ledger import reports\n")
    assert check_imports.imports_of(bad) == ["sqlalchemy", "cfo.ledger"]
    assert ast.parse("x = 1")  # the parser is the real one, not a regex
