import pytest

from airmouse.filter import OneEuroFilter


def test_the_first_sample_passes_through() -> None:
    assert OneEuroFilter(1.0, 0.0)(0.0, 42.0) == 42.0


def test_a_constant_input_stays_constant() -> None:
    f = OneEuroFilter(1.0, 0.5)

    assert [f(step / 30, 7.0) for step in range(30)] == [7.0] * 30


def test_a_lower_min_cutoff_smooths_more() -> None:
    smooth, loose = OneEuroFilter(0.5, 0.0), OneEuroFilter(5.0, 0.0)
    smooth(0.0, 0.0)
    loose(0.0, 0.0)

    assert smooth(1 / 30, 10.0) < loose(1 / 30, 10.0)


def test_a_higher_beta_follows_a_fast_move_more_closely() -> None:
    steady, quick = OneEuroFilter(1.0, 0.0), OneEuroFilter(1.0, 0.1)
    for f in (steady, quick):
        f(0.0, 0.0)
        for step in range(1, 5):
            f(step / 30, 100.0 * step)

    assert quick(5 / 30, 500.0) > steady(5 / 30, 500.0)


def test_reset_makes_the_next_sample_pass_through() -> None:
    f = OneEuroFilter(1.0, 0.0)
    f(0.0, 0.0)
    f(0.1, 10.0)
    f.reset()

    assert f(0.2, 500.0) == 500.0


def test_a_repeated_timestamp_does_not_divide_by_zero() -> None:
    f = OneEuroFilter(1.0, 0.0)
    f(1.0, 0.0)

    assert f(1.0, 9.0) == 0.0


def test_a_zero_cutoff_holds_the_output() -> None:
    f = OneEuroFilter(0.0, 0.0)
    f(0.0, 3.0)

    assert f(0.1, 9.0) == pytest.approx(3.0)
