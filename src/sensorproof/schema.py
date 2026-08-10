"""Strict, bounded schema parsing for SensorProof scenarios."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

MAX_SCENARIO_BYTES: Final = 256 * 1024
MAX_STEPS: Final = 2_000
MAX_SENSORS: Final = 16
MAX_FAULTS: Final = 64
_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


class ScenarioError(ValueError):
    """Raised when an input scenario violates the bounded schema."""


@dataclass(frozen=True, slots=True)
class Motion:
    start: int
    end: int
    ax_mm_s2: int
    ay_mm_s2: int


@dataclass(frozen=True, slots=True)
class Sensor:
    sensor_id: str
    kind: str
    noise_units: int
    gate_sigma_milli: int
    alpha_milli: int
    beta_milli: int


@dataclass(frozen=True, slots=True)
class Fault:
    sensor_id: str
    start: int
    end: int
    fault_type: str
    bias_x: int
    bias_y: int


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    seed: int
    dt_ms: int
    steps: int
    initial_state: tuple[int, int, int, int]
    motion: tuple[Motion, ...]
    sensors: tuple[Sensor, ...]
    faults: tuple[Fault, ...]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ScenarioError(f"non-finite JSON number is not allowed: {value}")


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ScenarioError(f"{label} keys mismatch; missing={missing}, extra={extra}")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ScenarioError(f"{label} must be an array")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise ScenarioError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ScenarioError(f"{label} must be between {minimum} and {maximum}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ScenarioError(f"{label} must match {_ID.pattern}")
    return value


def parse_scenario_bytes(raw: bytes) -> Scenario:
    """Parse a scenario from strict UTF-8 JSON after enforcing the size budget."""
    if len(raw) > MAX_SCENARIO_BYTES:
        raise ScenarioError(f"scenario exceeds {MAX_SCENARIO_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ScenarioError("scenario must be strict UTF-8") from exc
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    root = _mapping(document, "scenario")
    _exact_keys(
        root,
        {
            "schema_version",
            "name",
            "seed",
            "dt_ms",
            "steps",
            "initial_state",
            "motion",
            "sensors",
            "faults",
        },
        "scenario",
    )
    if _integer(root["schema_version"], "schema_version", 1, 1) != 1:
        raise AssertionError("unreachable")

    name = root["name"]
    if not isinstance(name, str) or not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
        raise ScenarioError("name must contain 1..80 printable characters")
    seed = _integer(root["seed"], "seed", 0, 2**63 - 1)
    dt_ms = _integer(root["dt_ms"], "dt_ms", 10, 10_000)
    steps = _integer(root["steps"], "steps", 2, MAX_STEPS)

    initial = _mapping(root["initial_state"], "initial_state")
    initial_keys = {"x_mm", "y_mm", "vx_mm_s", "vy_mm_s"}
    _exact_keys(initial, initial_keys, "initial_state")
    initial_state = tuple(
        _integer(initial[key], f"initial_state.{key}", -(10**9), 10**9)
        for key in ("x_mm", "y_mm", "vx_mm_s", "vy_mm_s")
    )

    motion_items = _list(root["motion"], "motion")
    if len(motion_items) > 64:
        raise ScenarioError("motion contains more than 64 segments")
    motion: list[Motion] = []
    occupied: set[int] = set()
    for index, item in enumerate(motion_items):
        value = _mapping(item, f"motion[{index}]")
        _exact_keys(value, {"start", "end", "ax_mm_s2", "ay_mm_s2"}, f"motion[{index}]")
        start = _integer(value["start"], f"motion[{index}].start", 0, steps - 1)
        end = _integer(value["end"], f"motion[{index}].end", start + 1, steps)
        covered = set(range(start, end))
        if occupied & covered:
            raise ScenarioError("motion segments must not overlap")
        occupied |= covered
        motion.append(
            Motion(
                start,
                end,
                _integer(value["ax_mm_s2"], f"motion[{index}].ax_mm_s2", -100_000, 100_000),
                _integer(value["ay_mm_s2"], f"motion[{index}].ay_mm_s2", -100_000, 100_000),
            )
        )

    sensor_items = _list(root["sensors"], "sensors")
    if not 1 <= len(sensor_items) <= MAX_SENSORS:
        raise ScenarioError(f"sensors must contain 1..{MAX_SENSORS} entries")
    sensors: list[Sensor] = []
    sensor_ids: set[str] = set()
    for index, item in enumerate(sensor_items):
        value = _mapping(item, f"sensors[{index}]")
        _exact_keys(
            value,
            {
                "id",
                "kind",
                "noise_units",
                "gate_sigma_milli",
                "alpha_milli",
                "beta_milli",
            },
            f"sensors[{index}]",
        )
        sensor_id = _identifier(value["id"], f"sensors[{index}].id")
        if sensor_id in sensor_ids:
            raise ScenarioError(f"duplicate sensor id: {sensor_id}")
        sensor_ids.add(sensor_id)
        kind = value["kind"]
        if kind not in {"position", "velocity"}:
            raise ScenarioError(f"sensors[{index}].kind must be position or velocity")
        sensors.append(
            Sensor(
                sensor_id,
                kind,
                _integer(value["noise_units"], f"sensors[{index}].noise_units", 1, 1_000_000),
                _integer(
                    value["gate_sigma_milli"],
                    f"sensors[{index}].gate_sigma_milli",
                    1_000,
                    20_000,
                ),
                _integer(value["alpha_milli"], f"sensors[{index}].alpha_milli", 1, 1_000),
                _integer(value["beta_milli"], f"sensors[{index}].beta_milli", 0, 1_000),
            )
        )

    fault_items = _list(root["faults"], "faults")
    if len(fault_items) > MAX_FAULTS:
        raise ScenarioError(f"faults contains more than {MAX_FAULTS} entries")
    faults: list[Fault] = []
    for index, item in enumerate(fault_items):
        value = _mapping(item, f"faults[{index}]")
        _exact_keys(
            value,
            {"sensor", "start", "end", "type", "bias_x", "bias_y"},
            f"faults[{index}]",
        )
        sensor_id = _identifier(value["sensor"], f"faults[{index}].sensor")
        if sensor_id not in sensor_ids:
            raise ScenarioError(f"faults[{index}] references unknown sensor {sensor_id}")
        start = _integer(value["start"], f"faults[{index}].start", 0, steps - 1)
        end = _integer(value["end"], f"faults[{index}].end", start + 1, steps)
        fault_type = value["type"]
        if fault_type not in {"bias_step", "bias_ramp"}:
            raise ScenarioError(f"faults[{index}].type must be bias_step or bias_ramp")
        faults.append(
            Fault(
                sensor_id,
                start,
                end,
                fault_type,
                _integer(value["bias_x"], f"faults[{index}].bias_x", -(10**9), 10**9),
                _integer(value["bias_y"], f"faults[{index}].bias_y", -(10**9), 10**9),
            )
        )
    return Scenario(
        name,
        seed,
        dt_ms,
        steps,
        initial_state,
        tuple(motion),
        tuple(sensors),
        tuple(faults),
    )


def load_scenario(path: Path) -> Scenario:
    """Load a scenario without following an unbounded stream."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ScenarioError(f"cannot inspect scenario: {exc}") from exc
    if size > MAX_SCENARIO_BYTES:
        raise ScenarioError(f"scenario exceeds {MAX_SCENARIO_BYTES} bytes")
    try:
        return parse_scenario_bytes(path.read_bytes())
    except OSError as exc:
        raise ScenarioError(f"cannot read scenario: {exc}") from exc


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    """Convert the validated scenario back to its canonical public schema."""
    return {
        "schema_version": 1,
        "name": scenario.name,
        "seed": scenario.seed,
        "dt_ms": scenario.dt_ms,
        "steps": scenario.steps,
        "initial_state": dict(
            zip(("x_mm", "y_mm", "vx_mm_s", "vy_mm_s"), scenario.initial_state, strict=True)
        ),
        "motion": [
            {
                "start": item.start,
                "end": item.end,
                "ax_mm_s2": item.ax_mm_s2,
                "ay_mm_s2": item.ay_mm_s2,
            }
            for item in scenario.motion
        ],
        "sensors": [
            {
                "id": item.sensor_id,
                "kind": item.kind,
                "noise_units": item.noise_units,
                "gate_sigma_milli": item.gate_sigma_milli,
                "alpha_milli": item.alpha_milli,
                "beta_milli": item.beta_milli,
            }
            for item in scenario.sensors
        ],
        "faults": [
            {
                "sensor": item.sensor_id,
                "start": item.start,
                "end": item.end,
                "type": item.fault_type,
                "bias_x": item.bias_x,
                "bias_y": item.bias_y,
            }
            for item in scenario.faults
        ],
    }
