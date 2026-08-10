"""Adversarial tests for independent artifact replay."""

from __future__ import annotations

from copy import deepcopy

import pytest

from sensorproof.artifact import ArtifactError
from sensorproof.engine import run_experiment
from sensorproof.schema import Scenario
from sensorproof.verify import verify_artifact


def test_verifies_complete_artifact(scenario: Scenario) -> None:
    artifact = run_experiment(scenario)
    result = verify_artifact(artifact)
    assert result.steps == 96
    assert result.observations == 288
    assert result.robust_rmse_mm < result.baseline_rmse_mm


@pytest.mark.parametrize(
    "mutation",
    [
        "observation",
        "residual",
        "decision",
        "summary",
        "certificate",
        "comparison",
    ],
)
def test_tampering_is_detected(scenario: Scenario, mutation: str) -> None:
    artifact = deepcopy(run_experiment(scenario))
    if mutation == "observation":
        artifact["observations"][0]["observations"][0]["values"][0] += 1
    elif mutation == "residual":
        artifact["runs"]["robust"]["trace"][0]["decisions"][0]["residual"][0] += 1
    elif mutation == "decision":
        decision = next(
            item
            for frame in artifact["runs"]["robust"]["trace"]
            for item in frame["decisions"]
            if item["status"] != "accepted"
        )
        decision["status"] = "accepted"
    elif mutation == "summary":
        artifact["runs"]["robust"]["summary"]["position_rmse_mm"] += 1
    elif mutation == "certificate":
        artifact["certificate"]["payload_sha256"] = "0" * 64
    else:
        winner = artifact["comparison"]["winner"]
        artifact["comparison"]["winner"] = "baseline" if winner == "robust" else "robust"
    with pytest.raises(ArtifactError):
        verify_artifact(artifact)


def test_unknown_artifact_key_is_rejected(scenario: Scenario) -> None:
    artifact = run_experiment(scenario)
    artifact["untrusted"] = True
    with pytest.raises(ArtifactError, match="root keys"):
        verify_artifact(artifact)
