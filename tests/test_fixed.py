"""Tests for deterministic integer primitives."""

from sensorproof.fixed import canonical_bytes, deterministic_noise, integer_rmse, round_div


def test_round_div_is_symmetric_and_half_away_from_zero() -> None:
    assert round_div(5, 2) == 3
    assert round_div(-5, 2) == -3
    assert round_div(4, 2) == 2
    assert round_div(-4, 2) == -2


def test_round_div_rejects_nonpositive_denominator() -> None:
    try:
        round_div(1, 0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("zero denominator was accepted")


def test_integer_rmse_uses_integer_arithmetic() -> None:
    assert integer_rmse([9, 16]) == 3


def test_canonical_bytes_ignore_mapping_insertion_order() -> None:
    assert canonical_bytes({"b": 2, "a": 1}) == canonical_bytes({"a": 1, "b": 2})


def test_hash_noise_is_stable_and_bounded() -> None:
    first = deterministic_noise(4, 9, "gnss", 0, 700)
    assert first == deterministic_noise(4, 9, "gnss", 0, 700)
    assert -700 <= first <= 700
    assert first != deterministic_noise(4, 9, "gnss", 1, 700)
