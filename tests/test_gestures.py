import dataclasses
import math

import pytest

from airmouse.config import OpenPalmConfig
from airmouse.gestures import (
    FINGER_SPREAD,
    FINGER_TIPS,
    distance,
    hand_size,
    is_open_palm,
    open_palm_score,
)
from anatomy import synthetic_hand

CONFIG = OpenPalmConfig()
# Views of a Hand facing a camera: tilted a little towards or away from it, rolled in the image.
VIEWS = [(pitch, roll) for pitch in (-20.0, 0.0, 20.0) for roll in (-20.0, 0.0, 20.0)]
OPEN_POSES = ["open together", "open relaxed curl", "open fanned", "open thumb tucked"]
NOT_OPEN_POSES = [
    "fist",
    "pointing",
    "pointing relaxed",
    "pinch fingers curled",
    "pinch others open",
]
MARGIN = 0.1  # a clear margin on both sides of the threshold


def jittered(pose: str, pitch: float, roll: float, seed: int) -> list[tuple[float, float]]:
    return list(synthetic_hand(pose, pitch=pitch, roll=roll, jitter=0.004, seed=seed))


@pytest.mark.parametrize("pose", OPEN_POSES)
@pytest.mark.parametrize(("pitch", "roll"), VIEWS)
def test_a_normal_open_hand_counts_with_a_clear_margin(
    pose: str, pitch: float, roll: float
) -> None:
    for seed in range(5):
        hand = jittered(pose, pitch, roll, seed)

        assert open_palm_score(hand) >= CONFIG.score_threshold + MARGIN
        assert is_open_palm(hand)


@pytest.mark.parametrize("pose", NOT_OPEN_POSES)
@pytest.mark.parametrize(("pitch", "roll"), VIEWS)
def test_a_fist_a_pointing_hand_and_a_pinch_never_count(
    pose: str, pitch: float, roll: float
) -> None:
    for seed in range(5):
        hand = jittered(pose, pitch, roll, seed)

        assert open_palm_score(hand) <= CONFIG.score_threshold - MARGIN
        assert not is_open_palm(hand)


def test_the_close_fingered_open_hand_is_the_one_the_old_spread_rule_missed() -> None:
    hand = synthetic_hand("open together")
    size = hand_size(hand)
    tips = [hand[tip] for tip in FINGER_TIPS]
    gaps = [distance(a, b) / size for a, b in zip(tips, tips[1:], strict=False)]

    assert min(gaps) < FINGER_SPREAD  # the old rule wanted every gap at least this wide
    assert is_open_palm(hand)


def test_a_wide_fan_scores_higher_than_close_fingers_but_both_count() -> None:
    together = open_palm_score(synthetic_hand("open together"))
    fanned = open_palm_score(synthetic_hand("open fanned"))

    assert fanned > together
    assert together >= CONFIG.score_threshold


def test_the_score_falls_as_the_other_fingers_curl_in() -> None:
    open_hand = open_palm_score(synthetic_hand("open together"))
    pointing = open_palm_score(synthetic_hand("pointing"))
    fist = open_palm_score(synthetic_hand("fist"))

    assert open_hand > pointing > fist >= 0.0


def test_a_hand_with_only_the_pointer_out_is_not_close_to_counting() -> None:
    assert open_palm_score(synthetic_hand("pointing")) < CONFIG.score_threshold / 1.5


def test_a_thumb_touching_the_index_tip_is_a_pinch_whatever_the_other_fingers_do() -> None:
    assert open_palm_score(synthetic_hand("pinch others open")) == 0.0


def test_the_score_stays_between_0_and_1() -> None:
    for pose in [*OPEN_POSES, *NOT_OPEN_POSES]:
        for pitch, roll in VIEWS:
            assert 0.0 <= open_palm_score(synthetic_hand(pose, pitch=pitch, roll=roll)) <= 1.0


def test_the_score_reads_the_same_near_or_far_from_the_camera() -> None:
    near = synthetic_hand("open together", size=0.35)
    far = synthetic_hand("open together", size=0.12)

    assert open_palm_score(near) == pytest.approx(open_palm_score(far), abs=1e-6)


def test_a_thumb_tucked_hand_counts_and_the_threshold_comes_from_config() -> None:
    hand = synthetic_hand("open thumb tucked")
    strict = dataclasses.replace(CONFIG, score_threshold=1.0)

    assert is_open_palm(hand, CONFIG)
    assert not is_open_palm(hand, strict)


def test_the_finger_reach_range_comes_from_config() -> None:
    hand = synthetic_hand("open together")
    demanding = dataclasses.replace(CONFIG, finger_curled=1.7, finger_extended=1.9)

    assert open_palm_score(hand, demanding) < open_palm_score(hand, CONFIG)


def test_the_pinch_gap_comes_from_config() -> None:
    hand = synthetic_hand("open relaxed curl", pitch=40.0)
    wide = dataclasses.replace(CONFIG, pinch_gap=1.0)

    assert open_palm_score(hand, CONFIG) > 0.0
    assert open_palm_score(hand, wide) == 0.0


def test_wrong_landmark_counts_and_a_zero_size_hand_are_never_an_open_palm() -> None:
    hand = synthetic_hand("open together")
    collapsed = [hand[0]] * 21

    assert open_palm_score(hand[:20]) == 0.0
    assert open_palm_score([]) == 0.0
    assert open_palm_score(collapsed) == 0.0
    assert not is_open_palm(collapsed)


def test_the_score_is_finite_for_every_fixture() -> None:
    for pose in [*OPEN_POSES, *NOT_OPEN_POSES]:
        assert math.isfinite(open_palm_score(synthetic_hand(pose, jitter=0.01, seed=3)))
