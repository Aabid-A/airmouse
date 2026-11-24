import hashlib
from importlib.resources import files

ASSETS = files("airmouse").joinpath("assets")
MODEL = "hand_landmarker.task"
# Pinned here as well as in the .sha256 file, so changing the model takes a
# deliberate edit in three places (this test, the checksum file, the note) and ADR 0003.
PINNED_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def recorded_checksum() -> str:
    return ASSETS.joinpath(f"{MODEL}.sha256").read_text().split()[0]


def test_hand_model_matches_its_recorded_checksum() -> None:
    actual = hashlib.sha256(ASSETS.joinpath(MODEL).read_bytes()).hexdigest()

    assert actual == recorded_checksum()


def test_the_recorded_checksum_is_the_pinned_one() -> None:
    assert recorded_checksum() == PINNED_SHA256


def test_the_note_documents_the_same_checksum() -> None:
    note = ASSETS.joinpath("HAND_LANDMARKER.md").read_text()

    assert recorded_checksum() in note


def test_the_apache_licence_text_ships_with_the_model() -> None:
    licence = ASSETS.joinpath("LICENSE-Apache-2.0.txt").read_text()

    assert "Apache License" in licence
    assert "Version 2.0, January 2004" in licence
