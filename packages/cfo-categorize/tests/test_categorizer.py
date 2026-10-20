import json

from cfo.categorize.categorizer import (
    BATCH_SIZE,
    AnthropicClient,
    categorize,
)
from cfo.categorize.port import OWN_MOVE_LABEL, Item, Label
from cfo.core.types import MappingSource

DINING = Label("Expenses:Food:Dining", "Dining", "Restaurants", "debit")
REWARDS = Label("Income:Rewards", "Rewards", "Cashback", "credit")
LABELS = [DINING, REWARDS, OWN_MOVE_LABEL]


def items(descs: list[str], way: str = "debit") -> list[Item]:
    return [Item(d, way) for d in descs]  # type: ignore[arg-type]


class Scripted:
    """A fake model: `reply(batch_descriptions)` returns the raw text for each request."""

    def __init__(self, reply):  # type: ignore[no-untyped-def]
        self.reply, self.calls = reply, []

    def complete(self, system: str, user: str) -> str:
        batch = [line.split(". ", 1)[1].split(" ", 1)[1] for line in user.splitlines()]
        self.calls.append(batch)
        return self.reply(batch)


def ok(batch: list[str], category: str = "Expenses:Food:Dining") -> str:
    return json.dumps(
        {
            "items": [
                {"id": i, "merchant": f"M{i}", "category": category}
                for i in range(1, len(batch) + 1)
            ]
        }
    )


def test_batches_of_fifty_and_distinct() -> None:
    descs = [f"D{i}" for i in range(120)] + ["D0", "D1", ""]  # duplicates and blanks dropped
    fake = Scripted(ok)
    result = categorize(items(descs), LABELS, fake)
    assert [len(c) for c in fake.calls] == [BATCH_SIZE, BATCH_SIZE, 20]
    assert len(result.mappings) == 120 and result.unresolved == () and result.warnings == ()
    m = result.mappings["D0"]
    assert (m.label, m.source, m.clean_merchant) == (DINING.key, MappingSource.MODEL, "M1")


def test_malformed_json_leaves_that_batch_uncategorized() -> None:
    state = {"n": 0}

    def reply(batch: list[str]) -> str:
        state["n"] += 1
        return "not json at all" if state["n"] == 1 else ok(batch)

    result = categorize(items([f"D{i}" for i in range(60)]), LABELS, Scripted(reply))
    assert len(result.mappings) == 10 and len(result.unresolved) == 50
    assert any("not valid JSON" in w for w in result.warnings)


def test_unknown_missing_and_forbidden_categories_are_left_alone() -> None:
    def reply(batch: list[str]) -> str:
        return json.dumps(
            {
                "items": [
                    {"id": 1, "merchant": "Good", "category": "Expenses:Food:Dining"},
                    {"id": 2, "merchant": "Bad", "category": "Expenses:Entertainment"},  # unknown
                    {"id": 3, "merchant": "Paid", "category": "Income:Rewards"},  # wrong direction
                    {"id": 4, "merchant": "Nope", "category": "Expenses:Uncategorized"},
                    {
                        "id": 99,
                        "merchant": "Ghost",
                        "category": "Expenses:Food:Dining",
                    },  # not in the batch
                    {
                        "id": 5,
                        "merchant": "  ",
                        "category": "Expenses:Food:Dining",
                    },  # blank merchant
                    # id 6 missing entirely
                ]
            }
        )

    result = categorize(items(["a", "b", "c", "d", "e", "f"]), LABELS, Scripted(reply))
    assert set(result.mappings) == {"a"}
    assert set(result.unresolved) == {"b", "c", "d", "e", "f"}


def test_code_fenced_reply_is_accepted() -> None:
    reply = Scripted(lambda b: "```json\n" + ok(b, "Income:Rewards") + "\n```")
    result = categorize(items(["x"], "credit"), LABELS, reply)
    assert result.mappings["x"].label == REWARDS.key


def test_unreachable_model_skips_everything_without_raising() -> None:
    def boom(batch: list[str]) -> str:
        raise ConnectionError("down")

    fake = Scripted(boom)
    result = categorize(items([f"D{i}" for i in range(120)]), LABELS, fake)
    assert len(fake.calls) == 1  # stops asking once it is clear the model is gone
    assert result.mappings == {} and len(result.unresolved) == 120
    assert result.warnings == ("categorization skipped: the model could not be reached",)


def test_the_claude_client_keeps_the_model_it_is_given() -> None:
    assert AnthropicClient("claude-haiku-4-5-20251001").model == "claude-haiku-4-5-20251001"


def test_the_prompt_lists_the_ledgers_labels_and_each_lines_direction() -> None:
    seen: dict[str, str] = {}

    class Spy:
        def complete(self, system: str, user: str) -> str:
            seen.update(system=system, user=user)
            return ok(["x"])

    categorize(items(["x"]), LABELS, Spy())
    assert "Expenses:Food:Dining: Dining — Restaurants" in seen["system"]
    assert seen["user"] == "1. (debit) x"


def test_generative_requests_mask_custom_label_names_and_keys() -> None:
    class Masker:
        def narration(self, text: str) -> str:
            return text.replace("Tara Nair", "[PERSON:aa11]")

    seen: dict[str, str] = {}

    class Spy:
        def complete(self, system: str, user: str) -> str:
            seen.update(system=system, user=user)
            return json.dumps({"items": [{"id": 1, "merchant": "Rent", "category": "category_1"}]})

    label = Label("Expenses:Tara-Nair-Rent", "Tara Nair rent", "paid to Tara Nair", "debit")
    result = categorize(items(["UPI Tara Nair"]), [label], Spy(), Masker())
    assert "tara" not in (seen["system"] + seen["user"]).lower()
    assert result.mappings["UPI Tara Nair"].label == label.key
