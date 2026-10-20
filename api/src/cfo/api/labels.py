"""Show pseudonym tokens as the names the owner gave them, in the cockpit only.

The chat agent and every model request see the tokens, never the labels, because a label such as
"Rahul (landlord)" could itself be a name.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"\[([A-Z_]+):([0-9a-f]{4})\]")


def _show(match: re.Match[str], labels: dict[str, str]) -> str:
    label = labels.get(match.group(0))
    if label:
        return label
    kind, short = match.group(1), match.group(2)
    return {"ID": f"#{short}", "VPA": f"@{short}"}.get(
        kind, f"{kind.title().replace('_', ' ')} {short}"
    )


def apply_labels(value: Any, labels: dict[str, str]) -> Any:
    """Replace every token in a JSON-like value with its label, or a short readable stand-in."""
    if isinstance(value, str):
        return _TOKEN.sub(lambda m: _show(m, labels), value)
    if isinstance(value, dict):
        return {k: apply_labels(v, labels) for k, v in value.items()}
    if isinstance(value, list):
        return [apply_labels(v, labels) for v in value]
    return value
