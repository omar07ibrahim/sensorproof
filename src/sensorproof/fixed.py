"""Exact integer helpers used by the simulator and fusion engine."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def round_div(numerator: int, denominator: int) -> int:
    """Divide integers with symmetric half-away-from-zero rounding."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    sign = -1 if numerator < 0 else 1
    magnitude = abs(numerator)
    return sign * ((magnitude + denominator // 2) // denominator)


def integer_rmse(squared_errors: list[int]) -> int:
    """Return the floor of the root mean squared error without floating point."""
    if not squared_errors:
        raise ValueError("at least one error is required")
    return math.isqrt(sum(squared_errors) // len(squared_errors))


def canonical_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value into one canonical byte representation."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    """Hash a JSON-compatible value after canonical serialization."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def deterministic_noise(seed: int, step: int, sensor_id: str, axis: int, scale: int) -> int:
    """Generate bounded, hash-derived Irwin-Hall-like noise using integers only."""
    payload = f"{seed}|{step}|{sensor_id}|{axis}".encode()
    digest = hashlib.sha256(payload).digest()
    samples = [int.from_bytes(digest[index : index + 2], "big") for index in range(0, 12, 2)]
    centered_twice = 2 * sum(samples) - 6 * 65_535
    return round_div(centered_twice * scale, 6 * 65_535)
