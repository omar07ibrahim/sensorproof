"""Tests for simulation and robust fusion behavior."""

from __future__ import annotations

from sensorproof.engine import run_experiment
from sensorproof.schema import Scenario
from sensorproof.simulate import simulate


def test_simulation_is_repeatable(scenario: Scenario) -> None:
    assert simulate(scenario) == simulate(scenario)


def test_simulation_has_bounded_expected_shape(scenario: Scenario) -> None:
    frames = simulate(scenario)
    assert len(frames) == scenario.steps
    assert all(len(frame["truth"]) == 4 for frame in frames)
    assert all(len(frame["observations"]) == len(scenario.sensors) for frame in frames)
    active = [
        observation
        for frame in frames
        for observation in frame["observations"]
        if observation["fault_active"]
    ]
    assert active
    assert {item["sensor"] for item in active} == {"gnss"}


def test_robust_run_beats_identical_ungated_baseline(scenario: Scenario) -> None:
    artifact = run_experiment(scenario)
    robust = artifact["runs"]["robust"]["summary"]
    baseline = artifact["runs"]["baseline"]["summary"]
    assert artifact["comparison"] == {
        "rmse_reduction_basis_points": 9818,
        "winner": "robust",
    }
    assert robust["position_rmse_mm"] == 160
    assert baseline["position_rmse_mm"] == 8792
    assert robust["isolated_fault_observations"] == 38
    assert robust["healthy_rejections"] == 2
    assert baseline["rejected_observations"] == 0
    assert baseline["quarantined_observations"] == 0


def test_artifact_is_byte_deterministic(scenario: Scenario) -> None:
    assert run_experiment(scenario) == run_experiment(scenario)


def test_certificate_contains_distinct_trace_digests(scenario: Scenario) -> None:
    certificate = run_experiment(scenario)["certificate"]
    assert len(certificate["payload_sha256"]) == 64
    assert certificate["robust_trace_sha256"] != certificate["baseline_trace_sha256"]
