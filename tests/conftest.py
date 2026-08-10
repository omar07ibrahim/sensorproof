"""Shared fixtures for the SensorProof test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from sensorproof.schema import Scenario, load_scenario


@pytest.fixture
def scenario_path() -> Path:
    return Path(__file__).parents[1] / "scenarios" / "urban-canyon.json"


@pytest.fixture
def scenario(scenario_path: Path) -> Scenario:
    return load_scenario(scenario_path)
