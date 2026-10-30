import stat

import pytest
from cfo.vault import FernetVault, generate_key, load_vault


def test_round_trip_and_ciphertext_hides_the_text() -> None:
    v = FernetVault(generate_key())
    blob = v.seal("UPI-VIKRAM KAPOOR-vikram@okhdfcbank-RENT")
    assert b"VIKRAM" not in blob and v.open(blob) == "UPI-VIKRAM KAPOOR-vikram@okhdfcbank-RENT"


def test_wrong_key_opens_nothing_and_does_not_raise() -> None:
    blob = FernetVault(generate_key()).seal("secret")
    assert FernetVault(generate_key()).open(blob) is None
    assert FernetVault(generate_key()).open(b"not a token") is None


def test_invalid_key_is_refused_with_a_clear_error() -> None:
    with pytest.raises(ValueError, match="narration key"):
        FernetVault("short")


def test_no_configuration_means_no_vault() -> None:
    assert load_vault({}) is None


def test_key_from_env_wins_over_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    key = generate_key()
    v = load_vault({"NARRATION_KEY": key, "NARRATION_KEY_FILE": str(tmp_path / "k")})
    assert v is not None and not (tmp_path / "k").exists()
    assert FernetVault(key).open(v.seal("x")) == "x"


def test_key_file_is_created_private_and_then_reused(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "keys" / "narration.key"
    first = load_vault({"NARRATION_KEY_FILE": str(path)})
    assert first is not None and stat.S_IMODE(path.stat().st_mode) == 0o600
    blob = first.seal("again")
    second = load_vault({"NARRATION_KEY_FILE": str(path)})
    assert second is not None and second.open(blob) == "again"
