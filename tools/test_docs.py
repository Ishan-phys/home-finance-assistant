"""The user documentation stays true: its links resolve, and the exact words it quotes from the
app are still the app's words. A guide that sends a new user to a dead page, or tells them to look
for a message the app no longer shows, is worse than none."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from cfo.agent.prompt import TOOL_USE

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = [ROOT / "README.md", *sorted(DOCS.glob("*.md"))]


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    text = re.sub(r"<[^>]+>", "", heading.strip().lower().replace("`", ""))
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return "".join(c for c in text if c.isalnum() or c in " -_").replace(" ", "-")


def _anchors(page: Path) -> set[str]:
    text, seen, found = page.read_text(), {}, set()
    for m in re.finditer(r"(?m)^#{1,6}\s+(.*)$", text):
        slug = _slug(m.group(1))
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        found.add(slug if n == 0 else f"{slug}-{n}")
    return found | set(re.findall(r'<a id="([^"]+)"', text))


def _links(page: Path) -> list[str]:
    text = re.sub(r"(?s)```.*?```", "", page.read_text())
    found = re.findall(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)', text)
    found += re.findall(r'<img[^>]+src="([^"]+)"', text) + re.findall(r'href="([^"]+)"', text)
    return [link for link in found if not link.startswith(("http://", "https://", "mailto:"))]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_relative_link_image_and_anchor_resolves(page: Path) -> None:
    broken = []
    for link in _links(page):
        target, _, fragment = link.partition("#")
        path = (page.parent / target).resolve() if target else page
        if not path.exists():
            broken.append(f"{link}: no such file")
        elif fragment and path.suffix == ".md" and fragment not in _anchors(path):
            broken.append(f"{link}: no such heading")
    assert not broken, f"{page.name}: " + "; ".join(broken)


def test_every_screenshot_in_the_manual_is_used() -> None:
    pages = "\n".join(p.read_text() for p in PAGES)
    unused = [p.name for p in (DOCS / "images" / "manual").glob("*.png") if p.name not in pages]
    assert not unused, f"unused screenshots: {unused}"


def test_every_assistant_tool_has_its_tag_explained() -> None:
    """The chat shows "checked <tool name>" above each answer. The assistant guide explains each."""
    guide = (DOCS / "assistant.md").read_text()
    for name in TOOL_USE:
        tag = "checked " + name.removeprefix("get_").replace("_", " ")
        assert f"| {tag} |" in guide, f"assistant.md does not explain the tag {tag!r}"


def test_the_upload_messages_the_guide_quotes_still_exist() -> None:
    """Every bold message in the 'When an upload is refused' table comes from friendly.py."""
    guide = (DOCS / "statements.md").read_text()
    table = guide.split("## When an upload is refused", 1)[1].split("\n## ", 1)[0]
    source = (ROOT / "api" / "src" / "cfo" / "api" / "friendly.py").read_text()
    quoted = re.findall(r"(?m)^\| \*\*(.+?)\*\* \|", table)
    assert len(quoted) >= 10
    missing = []
    for message in quoted:
        # "Row N …" and "… statements are PDFs" carry placeholders: check the fixed words.
        for part in re.split(r"…|\bN\b|\(…\)", message):
            fixed = part.strip(" .()")
            # Pieces of an either-or message ("or the other way round") are the guide's words.
            if len(fixed) > 12 and "or the other way round" not in fixed and fixed not in source:
                missing.append(fixed)
    assert not missing, f"not in friendly.py: {missing}"


def test_the_environment_variables_the_guide_lists_are_in_the_template() -> None:
    listed = set(
        re.findall(r"(?m)^\| `([A-Z][A-Z_]+)` \|", (DOCS / "configuration.md").read_text())
    )
    template = set(re.findall(r"(?m)^#?\s*([A-Z][A-Z_]+)=", (ROOT / ".env.example").read_text()))
    assert listed and listed <= template, f"not in .env.example: {sorted(listed - template)}"
    assert template - {"ANTHROPIC_API_KEY"} <= listed | {"OPENAI_API_KEY"}, (
        f"undocumented: {sorted(template - listed)}"
    )
