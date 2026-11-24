import hashlib
from importlib.resources import files

ASSETS = files("airmouse").joinpath("assets")
MODEL = "hand_landmarker.task"


def recorded_checksum() -> str:
    return ASSETS.joinpath(f"{MODEL}.sha256").read_text().split()[0]


def test_hand_model_matches_its_recorded_checksum() -> None:
    actual = hashlib.sha256(ASSETS.joinpath(MODEL).read_bytes()).hexdigest()

    assert actual == recorded_checksum()


def test_the_note_documents_the_same_checksum() -> None:
    note = ASSETS.joinpath("HAND_LANDMARKER.md").read_text()

    assert recorded_checksum() in note


def test_the_apache_licence_text_ships_with_the_model() -> None:
    licence = ASSETS.joinpath("LICENSE-Apache-2.0.txt").read_text()

    assert "Apache License" in licence
    assert "Version 2.0, January 2004" in licence
