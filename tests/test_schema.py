"""Tests for strict and bounded scenario parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sensorproof.schema import (
    MAX_SCENARIO_BYTES,
    ScenarioError,
    load_scenario,
    parse_scenario_bytes,
    scenario_to_dict,
)


def test_example_round_trips_canonically(scenario_path: Path) -> None:
    scenario = load_scenario(scenario_path)
    value = scenario_to_dict(scenario)
    assert value["steps"] == 96
    assert len(value["sensors"]) == 3
    assert parse_scenario_bytes(json.dumps(value).encode()) == scenario


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b'{"schema_version":1,"schema_version":1}', "duplicate JSON key"),
        (b'{"schema_version":NaN}', "non-finite"),
        (b"\xff", "strict UTF-8"),
        (b"[]", "scenario must be an object"),
    ],
)
def test_rejects_ambiguous_json(raw: bytes, message: str) -> None:
    with pytest.raises(ScenarioError, match=message):
        parse_scenario_bytes(raw)


def test_rejects_unknown_root_key(scenario_path: Path) -> None:
    value = json.loads(scenario_path.read_text())
    value["surprise"] = True
    with pytest.raises(ScenarioError, match="keys mismatch"):
        parse_scenario_bytes(json.dumps(value).encode())


def test_rejects_boolean_where_integer_is_required(scenario_path: Path) -> None:
    value = json.loads(scenario_path.read_text())
    value["steps"] = True
    with pytest.raises(ScenarioError, match="must be an integer"):
        parse_scenario_bytes(json.dumps(value).encode())


def test_rejects_overlapping_motion(scenario_path: Path) -> None:
    value = json.loads(scenario_path.read_text())
    value["motion"][1]["start"] = 19
    with pytest.raises(ScenarioError, match="must not overlap"):
        parse_scenario_bytes(json.dumps(value).encode())


def test_rejects_unknown_fault_sensor(scenario_path: Path) -> None:
    value = json.loads(scenario_path.read_text())
    value["faults"][0]["sensor"] = "missing"
    with pytest.raises(ScenarioError, match="unknown sensor"):
        parse_scenario_bytes(json.dumps(value).encode())


def test_size_budget_applies_before_parsing() -> None:
    with pytest.raises(ScenarioError, match="exceeds"):
        parse_scenario_bytes(b" " * (MAX_SCENARIO_BYTES + 1))
