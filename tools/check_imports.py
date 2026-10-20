"""Enforce the package boundaries of spec section 4.3.

Run directly (`python tools/check_imports.py`) or through the test in tools/test_imports.py.
Each workspace package may import only the `cfo.*` packages it declares, and the extractable
libraries may import none of the forbidden third-party modules (a database driver, the web
framework, the model SDKs where they do not belong).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# package directory -> (cfo namespace it owns, cfo namespaces it may import)
RULES: dict[str, tuple[str, set[str]]] = {
    "packages/cfo-core": ("core", set()),
    "packages/cfo-doc": ("doc", set()),
    "packages/cfo-redact": ("redact", {"doc"}),
    "packages/cfo-parse": ("parse", {"core", "doc"}),
    "packages/cfo-categorize": ("categorize", {"core"}),
    "packages/cfo-metrics": ("metrics", {"core"}),
    "packages/cfo-ledger": ("ledger", {"core", "metrics"}),
    "packages/cfo-ingest": ("ingest", {"core", "parse", "doc", "redact", "categorize", "ledger"}),
    "packages/cfo-agent": ("agent", {"core", "metrics", "ledger", "redact"}),
    "api": (
        "api",
        {"core", "metrics", "ledger", "ingest", "parse", "redact", "categorize", "agent"},
    ),
}

# third-party modules the extractable and pure packages must never import
FORBIDDEN = {
    "packages/cfo-core": {"sqlalchemy", "psycopg", "fastapi", "litellm", "openai", "pdfplumber"},
    "packages/cfo-doc": {"sqlalchemy", "psycopg", "fastapi", "litellm", "openai"},
    "packages/cfo-redact": {"sqlalchemy", "psycopg", "fastapi", "litellm", "openai"},
    "packages/cfo-parse": {"sqlalchemy", "psycopg", "fastapi", "litellm", "openai", "google"},
    "packages/cfo-categorize": {"sqlalchemy", "psycopg", "fastapi", "pdfplumber", "google"},
    "packages/cfo-metrics": {
        "sqlalchemy",
        "psycopg",
        "fastapi",
        "litellm",
        "openai",
        "pdfplumber",
        "httpx",
        "requests",
        "google",
        "alembic",
    },
}


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


def check() -> list[str]:
    problems: list[str] = []
    for pkg, (own, allowed) in RULES.items():
        for path in sorted((ROOT / pkg / "src").rglob("*.py")):
            for module in imports_of(path):
                parts = module.split(".")
                if parts[0] == "cfo" and len(parts) > 1:
                    target = parts[1]
                    if target != own and target not in allowed:
                        problems.append(
                            f"{path.relative_to(ROOT)}: imports cfo.{target}, "
                            f"which {pkg} does not declare"
                        )
                elif parts[0] in FORBIDDEN.get(pkg, set()):
                    problems.append(
                        f"{path.relative_to(ROOT)}: imports {parts[0]}, forbidden in {pkg}"
                    )
    return problems


if __name__ == "__main__":
    issues = check()
    for line in issues:
        print(line, file=sys.stderr)
    print("import boundaries: " + ("FAILED" if issues else "ok"))
    sys.exit(1 if issues else 0)
